#!/usr/bin/env python3
"""CLI bridge that calls Jupyter MCP tools — so external agents (Hermes, etc.) can use them.

Usage:
    jupyter-mcp-cli <tool_name> [--arg key=value] [--arg key=value]
    
Examples:
    jupyter-mcp-cli add_cell --arg notebook_path=Untitled1.ipynb --arg cell_type=markdown --arg "content=## Heading"
    jupyter-mcp-cli insert_cell --arg notebook_path=Untitled1.ipynb --arg cell_id=abc123 --arg "content=print('hi')"
    jupyter-mcp-cli get_active_notebook
    jupyter-mcp-cli run_cell --arg notebook_path=Untitled1.ipynb --arg cell_id=abc123
    jupyter-mcp-cli edit_cell --arg notebook_path=Untitled1.ipynb --arg cell_id=abc123 --arg "content=new code"
    jupyter-mcp-cli delete_cell --arg notebook_path=Untitled1.ipynb --arg cell_id=abc123
    jupyter-mcp-cli get_notebook_info --arg file_path=data.ipynb
"""

import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "http://localhost:3001/mcp"


def _extract_text(result):
    """Extract text content from MCP CallToolResult."""
    for block in result.content:
        if hasattr(block, "text"):
            return block.text
    return None


def _normalize_content(content: str) -> str:
    """Normalize cell content from LLM output.
    
    LLMs often output literal escape sequences instead of real characters.
    This converts them to what the user actually intended.
    
    IMPORTANT: Order matters. We process \\ first so that \\\\n (literal backslash + n)
    doesn't become a newline. The sequence \\\\n → \\n (after \\ → \\) then stays as \\n.
    But the far more common case is \\n meaning a real newline, so we do the
    simpler interpretation: \\n → newline, and accept the rare edge case of
    literal backslash-n being lost (extremely uncommon in notebook cells).
    """
    # Unescape quotes that got double-escaped by the shell
    content = content.replace('\\"', '"').replace("\\'", "'")
    # Convert literal \n to real newlines (most common issue)
    content = content.replace("\\n", "\n")
    # Convert literal \t to real tabs
    content = content.replace("\\t", "\t")
    return content


def _needs_normalization(tool: str) -> bool:
    """Check if a tool's content argument should be normalized."""
    return tool in ("add_cell", "edit_cell", "insert_cell")


async def call_tool(name: str, args: dict):
    """Call an MCP tool and print the result."""
    # Normalize content for cell-editing tools
    if _needs_normalization(name) and "content" in args:
        args["content"] = _normalize_content(args["content"])
    
    try:
        async with streamablehttp_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, args)
                text = _extract_text(result)
                if text:
                    print(text)
                else:
                    # Try to serialize structured content
                    for block in result.content:
                        if hasattr(block, "model_dump"):
                            print(json.dumps(block.model_dump(), default=str))
                        elif hasattr(block, "model_dump_json"):
                            print(block.model_dump_json())
                        else:
                            print(str(block))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def get_notebook_info(file_path: str):
    """Get notebook format info, cell count, and Jupytext sync status.
    
    This is a local-only command — no MCP server needed. It inspects the file
    on disk and returns metadata useful for the LLM to know what format
    conventions to follow.
    """
    # Resolve relative paths
    if not os.path.isabs(file_path):
        file_path = os.path.abspath(file_path)
    
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    
    info = {
        "path": file_path,
        "cells": 0,
        "jupytext": False,
    }
    
    # Detect format and count cells
    if file_path.endswith(".ipynb"):
        info["format"] = "ipynb"
        try:
            import nbformat
            with open(file_path, "r") as f:
                nb = nbformat.read(f, as_version=4)
            info["cells"] = len(nb.cells)
            # Check for jupytext metadata
            jupytext_meta = nb.metadata.get("jupytext", {})
            if jupytext_meta:
                info["jupytext"] = True
                info["jupytext_format"] = jupytext_meta.get("text_representation", {}).get("format_name", "unknown")
        except ImportError:
            # nbformat not available — fall back to raw JSON
            with open(file_path, "r") as f:
                nb = json.load(f)
            info["cells"] = len(nb.get("cells", []))
            jupytext_meta = nb.get("metadata", {}).get("jupytext", {})
            if jupytext_meta:
                info["jupytext"] = True
                info["jupytext_format"] = jupytext_meta.get("text_representation", {}).get("format_name", "unknown")
        except Exception as e:
            print(f"Warning: Could not parse notebook: {e}", file=sys.stderr)
    
    elif file_path.endswith(".py"):
        info["format"] = "py:percent"
        # Check for jupytext metadata
        with open(file_path, "r") as f:
            content = f.read()
        if "jupytext:" in content[:500]:
            info["jupytext"] = True
        # Count cells by # %% markers
        info["cells"] = content.count("# %%")
    
    elif file_path.endswith((".md", ".myst.md", ".qmd")):
        info["format"] = "md"
        with open(file_path, "r") as f:
            content = f.read()
        if "jupytext:" in content[:500]:
            info["jupytext"] = True
            info["jupytext_format"] = "myst" if file_path.endswith(".myst.md") else "markdown"
        # Count cells: markdown sections + code blocks
        import re
        code_blocks = len(re.findall(r"^```", content, re.MULTILINE)) // 2
        headers = len(re.findall(r"^#{1,6}\s+", content, re.MULTILINE))
        info["cells"] = code_blocks + headers  # rough estimate
    
    elif file_path.endswith(".Rmd"):
        info["format"] = "Rmarkdown"
        with open(file_path, "r") as f:
            content = f.read()
        if "jupytext:" in content[:500]:
            info["jupytext"] = True
        import re
        info["cells"] = len(re.findall(r"^```[+Rr]", content, re.MULTILINE))
    
    else:
        info["format"] = "unknown"
        print(f"Warning: Unknown file format: {file_path}", file=sys.stderr)
    
    print(json.dumps(info, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Call Jupyter MCP tools from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available tools:
  get_open_documents          List all open documents
  get_active_notebook         Get the currently active notebook path
  get_active_cell_id          Get active cell ID (requires --arg notebook_path=X)
  read_notebook_cells         Read cells (requires --arg notebook_path=X)
  read_cell                   Read single cell (requires --arg notebook_path=X, --arg cell_id=X)
  add_cell                    Add cell above/below (requires --arg notebook_path=X, --arg cell_type=X)
  insert_cell                 Insert cell at position (requires --arg notebook_path=X, --arg cell_id=X)
  edit_cell                   Edit cell content (requires --arg notebook_path=X, --arg cell_id=X, --arg content=X)
  delete_cell                 Delete a cell (requires --arg notebook_path=X, --arg cell_id=X)
  select_cell                 Navigate to cell (requires --arg cell_id=X)
  run_cell                    Execute a cell (requires --arg notebook_path=X, --arg cell_id=X)
  run_all_cells               Execute all cells in a notebook (requires --arg notebook_path=X)
  open_file                   Open a file in JupyterLab (requires --arg file_path=X)
  create_notebook             Create a new notebook (requires --arg file_path=X)

Format-aware tools:
  get_notebook_info           Get notebook format, cell count, Jupytext status (requires --arg file_path=X)

Example:
  jupyter-mcp-cli add_cell --arg notebook_path=data.ipynb --arg cell_type=markdown --arg "content=## Section"
""",
    )
    parser.add_argument("tool", help="MCP tool name to call")
    parser.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Tool argument as key=value (can repeat)",
    )

    args = parser.parse_args()

    # Handle local-only tools
    if args.tool == "get_notebook_info":
        file_path = None
        for arg_str in args.arg:
            if "=" in arg_str:
                key, value = arg_str.split("=", 1)
                if key == "file_path":
                    file_path = value
        if not file_path:
            print("Error: get_notebook_info requires --arg file_path=X", file=sys.stderr)
            sys.exit(1)
        get_notebook_info(file_path)
        return
    
    # Parse arguments
    tool_args = {}
    for arg_str in args.arg:
        if "=" not in arg_str:
            print(f"Error: argument must be key=value, got: {arg_str}", file=sys.stderr)
            sys.exit(1)
        key, value = arg_str.split("=", 1)
        # Try to parse as JSON (for numbers, booleans, lists)
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass
        tool_args[key] = value

    asyncio.run(call_tool(args.tool, tool_args))


if __name__ == "__main__":
    main()
