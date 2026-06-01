# jupyter-ai-hermes

Hermes Agent as an ACP persona for [Jupyter AI](https://jupyter-ai.readthedocs.io/), with live notebook context injection and custom MCP tools for cell metadata management.

## What it does

- **Injects live notebook context** into every Hermes prompt — active notebook path, current cell ID, and cell content — so Hermes always knows what you're working on.
- **Documents all available MCP CLI tools** so Hermes prefers them over raw `nbformat` scripts.
- **Registers custom MCP tools** (`set_cell_metadata`, `get_cell_metadata`, `list_cell_tags`) for operations the built-in toolkit doesn't cover.

## Requirements

- Python >= 3.12
- [Jupyter AI](https://github.com/jupyter-ai/jupyter-ai) with ACP client support
- [Hermes Agent](https://hermes-agent.nousresearch.com/) installed (the `hermes` binary must be on PATH)

## Installation

```bash
pip install jupyter-ai-hermes
```

Then restart JupyterLab. The "Hermes Agent" persona will appear in the Jupyter AI chat panel.

## MCP Tools

The package registers 3 custom MCP tools alongside the 16 built-in Jupyter AI notebook tools:

| Tool | What it does |
|------|-------------|
| `set_cell_metadata` | Set cell metadata (e.g. Rise slideshow types, custom tags) |
| `get_cell_metadata` | View cell metadata for debugging |
| `list_cell_tags` | List all cells matching specific tags |

All tools are also available via the `jupyter-mcp-cli` command-line bridge:

```bash
# Set a cell as a Rise slideshow slide
jupyter-mcp-cli set_cell_metadata \
  --arg file_path=notebook.ipynb \
  --arg cell_id=cell-abc123 \
  --arg 'metadata={"slideshow":{"slide_type":"slide"}}'

# List all cells tagged with "important"
jupyter-mcp-cli list_cell_tags \
  --arg file_path=notebook.ipynb \
  --arg tags='["important"]'
```

## Entry Points

| Group | Name | Target |
|-------|------|--------|
| `jupyter_ai.personas` | `hermes-acp` | `jupyter_ai_hermes.hermes:HermesAcpPersona` |
| `jupyter_server_mcp.tools` | `hermes_mcp_tools` | `jupyter_ai_hermes.mcp_tools:TOOLS` |
| `console_scripts` | `jupyter-mcp-cli` | `jupyter_ai_hermes.mcp_cli:main` |

## Architecture

```
┌──────────────────────────────────────────────┐
│  JupyterLab                                  │
│  ┌─────────────┐    ┌─────────────────────┐  │
│  │ Notebook UI │    │ Jupyter AI Chat     │  │
│  │ (YDoc)      │◄──►│ ┌─────────────────┐ │  │
│  └─────────────┘    │ │ Hermes Persona  │ │  │
│                     │ │  ├─ gather_ctx  │ │  │
│  ┌─────────────┐    │ │  ├─ MCP docs   │ │  │
│  │ MCP Server  │◄──►│ │  └─ forward ──►│ │  │
│  │ :3001       │    │ └─────────────────┘ │  │
│  └─────────────┘    └─────────────────────┘  │
│                                              │
│  ┌─────────────────────┐                     │
│  │ jupyter-mcp-cli     │                     │
│  │ (CLI bridge)        │                     │
│  └─────────────────────┘                     │
└──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────┐
│  Hermes Agent (ACP)  │
│  ┌────────────────┐  │
│  │ Tool execution │  │
│  │ jupyter-mcp-cli│  │
│  └────────────────┘  │
└──────────────────────┘
```

## Development

```bash
git clone git@github.com:dive4dec/jupyter-ai-hermes.git
cd jupyter-ai-hermes
pip install -e ".[dev]"
pytest
```

## License

MIT
