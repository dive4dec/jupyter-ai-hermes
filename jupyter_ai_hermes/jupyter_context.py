"""Bridge that calls Jupyter MCP tools and returns notebook context for Hermes."""

import asyncio
import json
from typing import Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "http://localhost:3001/mcp"


def _extract_text(result) -> Optional[str]:
    """Extract text from an MCP CallToolResult content block."""
    for block in result.content:
        if hasattr(block, "text") and block.text is not None:
            return block.text
    return None


async def _call_tool(name: str, args: dict) -> Optional[str]:
    """Call a single Jupyter MCP tool and return its text result."""
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            return _extract_text(result)


async def gather_context() -> str:
    """Gather notebook context and return as a formatted string.

    Includes:
    - Open documents
    - Active notebook path
    - Active cell ID
    - Active cell content (source code)
    """
    parts = []

    # 1. Open documents
    docs_raw = await _call_tool("get_open_documents", {})
    if docs_raw:
        try:
            docs = json.loads(docs_raw)
            if docs:
                parts.append("Open documents:")
                for d in docs:
                    parts.append(f"  - {d}")
        except json.JSONDecodeError:
            pass

    # 2. Active notebook
    active_nb = await _call_tool("get_active_notebook", {})
    if not active_nb:
        if parts:
            return "\n".join(parts)
        return "(No notebook context available)"

    parts.append(f"\nActive notebook: {active_nb}")

    # 3. Active cell
    active_cell = await _call_tool("get_active_cell_id", {"notebook_path": active_nb})
    if not active_cell:
        return "\n".join(parts)

    parts.append(f"Active cell ID: {active_cell}")

    # 4. Active cell content
    cell_raw = await _call_tool(
        "read_notebook_cells",
        {"notebook_path": active_nb, "specific_cell_id": active_cell},
    )
    if cell_raw:
        try:
            cells = json.loads(cell_raw)
            if cells and isinstance(cells, list):
                cell = cells[0]
                source = cell.get("source", "")
                cell_type = cell.get("cellType", "code")
                cell_id = cell.get("cell_id", "")
                parts.append(f"\nActive cell ({cell_type}, id={cell_id}):")
                parts.append("```python")
                parts.append(source)
                parts.append("```")
        except (json.JSONDecodeError, TypeError):
            pass

    return "\n".join(parts)
