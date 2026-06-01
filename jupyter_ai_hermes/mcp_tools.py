"""Custom MCP tools for the Hermes Jupyter persona.

Registered via the 'jupyter_server_mcp.tools' entry point so they're available
through the same MCP server that Jupyternaut uses.
"""

# Tool spec list for MCP server discovery
TOOLS = [
    "jupyter_ai_hermes.mcp_tools:set_cell_metadata",
    "jupyter_ai_hermes.mcp_tools:get_cell_metadata",
    "jupyter_ai_hermes.mcp_tools:list_cell_tags",
]

import json
from typing import Any, Dict, Optional, Union

import nbformat
from jupyter_ai_tools.utils import normalize_filepath, get_file_id, get_jupyter_ydoc


async def set_cell_metadata(
    file_path: str,
    cell_id: str,
    metadata: Union[str, Dict[str, Any]],
):
    """Set metadata on a notebook cell.

    Updates the metadata dictionary of a specific cell. Uses the in-memory
    YDoc representation if the notebook is open in JupyterLab; otherwise
    falls back to reading and writing the file directly.

    Args:
        file_path: Path to the notebook file.
        cell_id: UUID of the cell to update, or a numeric index as string.
        metadata: Either a JSON string or a dict of metadata key-value pairs
            to merge into the cell's metadata.

    Returns:
        dict with success message and the updated metadata.

    Example:
        set_cell_metadata(
            file_path="notebook.ipynb",
            cell_id="abc123",
            metadata='{"slideshow": {"slide_type": "slide"}}'
        )
    """
    # Parse metadata input
    if isinstance(metadata, str):
        metadata = json.loads(metadata)

    resolved_path = normalize_filepath(file_path)

    # Resolve cell_id if it's an index
    if cell_id.isdigit():
        with open(resolved_path, "r") as f:
            nb = nbformat.read(f, as_version=4)
        idx = int(cell_id)
        if not (0 <= idx < len(nb.cells)):
            raise ValueError(f"Cell index {idx} out of range")
        cell_id = nb.cells[idx].get("id") or str(idx)

    # Try YDoc first
    try:
        file_id = await get_file_id(file_path)
        ydoc = await get_jupyter_ydoc(file_id)

        if ydoc:
            cell_index, _ = ydoc.find_cell(cell_id)
            if cell_index is not None:
                ycell = ydoc._ycells[cell_index]
                cell_data = ycell.to_py()
                cell_data["metadata"].update(metadata)
                ycell.from_py(cell_data)
                return {
                    "success": True,
                    "file_path": file_path,
                    "cell_id": cell_id,
                    "metadata_updated": metadata,
                    "source": "ydoc",
                }
    except Exception:
        pass

    # Fallback: nbformat direct file read/write
    with open(resolved_path, "r") as f:
        notebook = nbformat.read(f, as_version=4)

    for i, cell in enumerate(notebook.cells):
        if cell.get("id") == cell_id:
            cell.metadata.update(metadata)
            with open(resolved_path, "w") as f:
                nbformat.write(notebook, f)
            return {
                "success": True,
                "file_path": file_path,
                "cell_id": cell_id,
                "metadata_updated": metadata,
                "source": "filesystem",
            }

    raise ValueError(f"Cell with ID {cell_id} not found in {file_path}")


async def get_cell_metadata(
    file_path: str,
    cell_id: str,
):
    """Get metadata for a specific notebook cell.

    Args:
        file_path: Path to the notebook file.
        cell_id: UUID of the cell, or a numeric index as string.

    Returns:
        The cell's metadata as a JSON string.
    """
    resolved_path = normalize_filepath(file_path)
    with open(resolved_path, "r") as f:
        notebook = nbformat.read(f, as_version=4)

    for cell in notebook.cells:
        if cell.get("id") == cell_id:
            return json.dumps(dict(cell.metadata), indent=2)

    raise ValueError(f"Cell with ID {cell_id} not found in {file_path}")


async def list_cell_tags(
    file_path: str,
):
    """List all cells with non-empty tags.

    Args:
        file_path: Path to the notebook file.

    Returns:
        JSON list of objects with cell_id, cell_index, and tags.
    """
    resolved_path = normalize_filepath(file_path)
    with open(resolved_path, "r") as f:
        notebook = nbformat.read(f, as_version=4)

    tagged = []
    for i, cell in enumerate(notebook.cells):
        tags = cell.metadata.get("tags", [])
        if tags:
            tagged.append({
                "cell_id": cell.get("id"),
                "cell_index": i,
                "tags": tags,
            })

    return json.dumps(tagged, indent=2)
