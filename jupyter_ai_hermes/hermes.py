"""Hermes Agent ACP persona with Jupyter notebook context injection.

Hermes gets two things before every message:
  1. Real-time notebook context (active notebook, current cell content)
  2. A list of MCP-based CLI tools it should prefer over raw nbformat
"""

import os
import shutil
from jupyter_ai_persona_manager import PersonaRequirementsUnmet, PersonaDefaults
from jupyter_ai_acp_client.base_acp_persona import BaseAcpPersona
from jupyterlab_chat.models import Message
from .jupyter_context import gather_context

_hermes_path = os.environ.get("HERMES_BIN_PATH") or shutil.which("hermes")

if not _hermes_path or not os.path.exists(_hermes_path):
    raise PersonaRequirementsUnmet(
        "This persona requires Hermes Agent to be installed. "
        "Install Hermes Agent and ensure `hermes` is on PATH, or set "
        "the HERMES_BIN_PATH environment variable to the full path."
    )

_avatar_path = str(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "static", "hermes.svg")
))

# ── Tool documentation injected into every prompt ──────────────────────────

MCP_TOOLS_DOC = """## Available Jupyter MCP Tools

You have access to `jupyter-mcp-cli` — a CLI bridge to Jupyter's built-in MCP tools.
**ALWAYS prefer these over raw `nbformat` scripts** — they handle collaborative editing,
preserve cell metadata/tags, and update the JupyterLab UI instantly.

Usage: `jupyter-mcp-cli <tool> --arg key=value --arg key2=value2`

### Reading context
| Command | Description |
|---------|-------------|
| `jupyter-mcp-cli get_open_documents` | List all open documents |
| `jupyter-mcp-cli get_active_notebook` | Get currently active notebook path |
| `jupyter-mcp-cli get_active_cell_id --arg notebook_path=X` | Get active cell ID |
| `jupyter-mcp-cli read_notebook_cells --arg notebook_path=X` | Read all cells |
| `jupyter-mcp-cli read_notebook_cells --arg notebook_path=X --arg specific_cell_id=X` | Read one cell |

### Editing cells (use `file_path`, not `notebook_path`)
| Command | Description |
|---------|-------------|
| `jupyter-mcp-cli add_cell --arg file_path=X --arg cell_id=X --arg add_above=true --arg cell_type=markdown --arg "content=..."` | Add cell above target |
| `jupyter-mcp-cli add_cell --arg file_path=X --arg cell_id=X --arg cell_type=code --arg "content=..."` | Add cell below target (default) |
| `jupyter-mcp-cli insert_cell --arg file_path=X --arg insert_index=N --arg cell_type=code --arg "content=..."` | Insert cell at index |
| `jupyter-mcp-cli edit_cell --arg file_path=X --arg cell_id=X --arg "content=..."` | Modify cell content |
| `jupyter-mcp-cli delete_cell --arg file_path=X --arg cell_id=X` | Delete a cell |

### Running cells
| Command | Description |
|---------|-------------|
| `jupyter-mcp-cli run_cell --arg cell_id=X` | Execute one cell |
| `jupyter-mcp-cli run_all_cells --arg notebook_path=X` | Execute all cells |

### Cell metadata and tags (use `file_path`)
| Command | Description |
|---------|-------------|
| `jupyter-mcp-cli set_cell_metadata --arg file_path=X --arg cell_id=X --arg 'metadata={"slideshow": {"slide_type": "slide"}}'` | Set cell metadata (e.g., Rise slideshow type) |
| `jupyter-mcp-cli get_cell_metadata --arg file_path=X --arg cell_id=X` | View cell metadata |
| `jupyter-mcp-cli list_cell_tags --arg file_path=X` | List all tagged cells |

### Other
| Command | Description |
|---------|-------------|
| `jupyter-mcp-cli create_notebook --arg file_path=X` | Create new notebook |
| `jupyter-mcp-cli select_cell --arg cell_id=X` | Navigate to a cell |
| `jupyter-mcp-cli open_file --arg file_path=X` | Open file in JupyterLab |

### Cell content formatting rules
- **Split headers into their own cells** — `#`, `##`, `###` should be standalone markdown cells, not mixed with body text
- **Use actual newlines in cell content** — output real line breaks, NOT literal `\n` characters (the CLI normalizes these anyway, but structured output is cleaner)
- **One logical idea per cell** — intro text, code, and output interpretation should be separate cells
- **Keep cells concise** — prefer multiple smaller cells over one dense wall-of-text cell

### Format-aware editing (Jupytext)
Before editing, call `jupyter-mcp-cli get_notebook_info --arg file_path=X` to know the format:
- `.ipynb` — full markdown support, separate cells for everything
- `.py` (percent) — markdown cells use `# |` or are converted to docstrings; prefer `# %%` cell markers
- `.md` / `.myst.md` — code in fenced blocks (```python), markdown is native
- `.Rmd` — code in ` ```{python} ` or ` ```{r} ` blocks

### Important notes
- **add_cell/edit_cell/delete_cell/insert_cell/set_cell_metadata/get_cell_metadata/list_cell_tags** use `file_path` parameter
- **read_notebook_cells/get_active_cell_id/run_all_cells** use `notebook_path` parameter
- For slideshow cell types (Rise): `{"slideshow": {"slide_type": "slide|subslide|fragment|notes|skip"}}`
- For cell tags: `{"tags": ["tag1", "tag2"]}`
- These tools preserve cell tags, metadata, and attachments — unlike raw `nbformat`
- Changes are applied collaboratively via YDoc — the UI updates instantly
"""


class HermesAcpPersona(BaseAcpPersona):
    def __init__(self, *args, **kwargs):
        executable = [_hermes_path, "acp"]
        super().__init__(*args, executable=executable, **kwargs)

    @property
    def defaults(self) -> PersonaDefaults:
        return PersonaDefaults(
            name="Hermes",
            description="Hermes as an ACP coding agent persona with Jupyter MCP tools.",
            avatar_path=_avatar_path,
            system_prompt="unused",
        )

    async def is_authed(self) -> bool:
        return True

    async def process_message(self, message: Message) -> None:
        """Inject notebook context + MCP tool docs before forwarding to Hermes."""

        # 1. Gather live notebook context
        try:
            context = await gather_context()
        except Exception as e:
            self.log.warning("Failed to gather notebook context: %s", e)
            context = "(Unable to gather notebook context)"

        # 2. Build enriched message
        enriched_parts = []

        if context and context not in (
            "(No notebook context available)",
            "(Unable to gather notebook context)",
        ):
            enriched_parts.append("## Jupyter Notebook Context\n" + context)

        enriched_parts.append(MCP_TOOLS_DOC)
        enriched_parts.append("\n---\n\n**User message:**\n" + message.body.strip())

        enriched = "\n".join(enriched_parts)

        # 3. Forward to the ACP subprocess
        await super().process_message(Message(
            id=message.id,
            body=enriched,
            time=message.time,
            sender=message.sender,
            type=message.type,
            attachments=message.attachments,
            mentions=message.mentions,
            raw_time=message.raw_time,
            deleted=message.deleted,
            edited=message.edited,
            metadata=message.metadata,
            mime_model=message.mime_model,
        ))
