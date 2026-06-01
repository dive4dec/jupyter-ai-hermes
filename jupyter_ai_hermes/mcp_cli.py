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
"""

import argparse
import asyncio
import json
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


async def call_tool(name: str, args: dict):
    """Call an MCP tool and print the result."""
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
