# CodeAssist Mini Copilot

A lightweight CLI code assistant that helps developers write, understand, and improve code — directly from the terminal.

No IDE plugin required. Point it at any Python or JS/TS codebase and start asking questions, getting explanations, requesting suggestions, or auto-fixing issues.

---

## Features

| Command | What it does |
|---|---|
| `codeassist index <dir>` | Build a local embedding index of your codebase |
| `codeassist ask "<question>"` | Ask anything — uses the index for context when available |
| `codeassist explain <file>` | Explain a file or a specific function/class |
| `codeassist suggest <file>` | Get concrete improvement suggestions |
| `codeassist fix <file>` | Detect issues, show a diff, optionally apply the fix |

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Best AI/ML ecosystem |
| CLI framework | Typer + Rich | Declarative commands, beautiful terminal output |
| LLM | Anthropic Claude API | Haiku (fast) for default, Sonnet (deep) with `--smart` |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Local, free, offline-capable, 384-dim vectors |
| Vector store | ChromaDB (embedded) | No server, persists to disk, cosine similarity search |
| Code parsing | Python `ast` (stdlib) for `.py`; line-window chunking for JS/TS | Extracts named functions and classes accurately |
| Package management | pip + pyproject.toml | Standard, no extra tooling required |

---

## Project Structure

```
CodeAssistantMiniCopilot/
├── .env.example              # API key template — copy to .env
├── pyproject.toml            # Package metadata, dependencies, CLI entry point
├── Plan/
│   └── plan.txt              # Design decisions and phase milestones
├── tests/
│   ├── test_parser.py        # Parser unit tests (no API needed)
│   └── test_fix.py           # Diff and code-block extraction tests
└── codeassist/
    ├── cli.py                # Typer app — registers all 5 commands
    ├── config.py             # Loads .env, exposes model names and API key
    ├── llm.py                # Anthropic client, streaming helpers
    ├── parser.py             # Python AST + sliding-window chunker for JS/TS
    ├── embeddings.py         # sentence-transformers + ChromaDB index
    ├── errors.py             # handle_errors() context manager for clean API errors
    └── commands/
        ├── ask.py            # codeassist ask
        ├── index.py          # codeassist index
        ├── explain.py        # codeassist explain
        ├── suggest.py        # codeassist suggest
        └── fix.py            # codeassist fix
```

---


### Querying

```
codeassist ask "How does error handling work here?"
```

1. Embeds the question with the same model (in memory only — not stored)
2. Queries ChromaDB for the top-5 most similar code chunks (cosine similarity)
3. Passes the retrieved chunks + question to Claude as context
4. Streams the response token-by-token to the terminal via Rich

### Direct file commands

`explain`, `suggest`, and `fix` skip the index entirely. They read the target
file directly, build a focused prompt, and stream Claude's response. `fix` also:
- Extracts the corrected code block from the response
- Renders a unified diff with syntax highlighting
- Requires explicit confirmation (`y/N`) before writing to disk

### LLM models used

| Flag | Model | Use case |
|---|---|---|
| *(default)* | `claude-haiku-4-5-20251001` | Fast inline responses |
| `--smart` | `claude-sonnet-4-6` | Deeper analysis, complex fixes |

Prompt caching is enabled on file content — repeated questions on the same
file do not re-tokenize the file, reducing cost and latency.

---

## Environment Setup

### Prerequisites

- Python 3.11 or newer
- An [Anthropic API key](https://console.anthropic.com)

### Steps

**1. Clone the repository**

```bash
git clone <repo-url>
cd CodeAssistantMiniCopilot
```

**2. Create and activate a virtual environment**

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

**3. Install the package**

```bash
pip install -e ".[dev]"
```

This installs `codeassist` as an editable package plus all runtime and
development dependencies (pytest, ruff, black).

**4. Configure your API key**

```bash
cp .env.example .env
```

Open `.env` and set your key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

**5. Verify the installation**

```bash
codeassist --help
```

---

## Running the Tool

### Index a codebase

```bash
# Index the whole project
codeassist index .

# Index a specific directory
codeassist index ./src

# Re-index from scratch (clears stale chunks from deleted files)
codeassist index . --reset

# Use a custom DB location
codeassist index ./src --db /tmp/myproject-index
```

### Ask questions

```bash
# Context-aware query (uses index if .codeassist/db exists)
codeassist ask "How does the parser handle syntax errors?"

# Provide a specific file as context instead of the index
codeassist ask "What does this file do?" --file codeassist/llm.py

# Use the smarter model for deeper answers
codeassist ask "Explain the architecture of this project" --smart

# Control how many index chunks are retrieved
codeassist ask "How is ChromaDB used?" --top-k 8
```

### Explain code

```bash
# Explain an entire file
codeassist explain codeassist/embeddings.py

# Explain a specific function or class by name
codeassist explain codeassist/llm.py --fn stream_ask

# Use the smarter model
codeassist explain codeassist/parser.py --fn _parse_python --smart
```

### Suggest improvements

```bash
# Review a whole file
codeassist suggest codeassist/commands/fix.py

# Focus on a specific line region (±25 lines around the target)
codeassist suggest codeassist/commands/index.py --ln 60
```

### Fix issues

```bash
# Analyse and show a diff only (no changes written)
codeassist fix codeassist/parser.py

# Show diff, then ask for confirmation before writing
codeassist fix codeassist/parser.py --apply

# Apply without the confirmation prompt (for scripting)
codeassist fix codeassist/parser.py --apply --yes

# Use the smarter model for complex fixes
codeassist fix codeassist/llm.py --apply --smart
```

### Run the tests

```bash
pytest tests/ -v
```

---

## Deployment / Distribution

### Option 1 — Install from source on any machine

```bash
git clone <repo-url>
cd CodeAssistantMiniCopilot
python -m venv .venv && .venv\Scripts\activate   # or source .venv/bin/activate
pip install -e .
cp .env.example .env   # add ANTHROPIC_API_KEY
codeassist --help
```


### Option 3 — Standalone executable with PyInstaller

```bash
pip install pyinstaller
pyinstaller --onefile --name codeassist \
    --hidden-import codeassist.commands.ask \
    --hidden-import codeassist.commands.index \
    --hidden-import codeassist.commands.explain \
    --hidden-import codeassist.commands.suggest \
    --hidden-import codeassist.commands.fix \
    codeassist/cli.py
```

The resulting `dist/codeassist.exe` (Windows) or `dist/codeassist` (Linux/macOS)
is a single self-contained binary. Copy it anywhere and run it — no Python
installation required on the target machine. The `.env` file (or
`ANTHROPIC_API_KEY` environment variable) must still be present.

### Option 4 — Publish to PyPI

```bash
# Build
python -m build

# Upload (requires a PyPI account and API token)
pip install twine
twine upload dist/*
```

After publishing, anyone can install with:

```bash
pip install codeassist-mini-copilot
```

---

## Interactive Terminal UI (TUI)

In addition to individual CLI commands, CodeAssist includes a full-screen
interactive terminal UI built with [Textual](https://textual.textualize.io/).

### Launch

```bash
codeassist ui

# With a custom index location
codeassist ui --db /path/to/.codeassist/db
```

### Layout

```
┌─ CodeAssist Mini Copilot ──────────────────────────────────────────┐
│ [F1 Ask] [F2 Explain] [F3 Suggest] [F4 Fix] [F5 Index]             │
├─ Sidebar ─────────────────┬─ Output ───────────────────────────────┤
│ Mode: F1 · Ask            │  CodeAssist Mini Copilot               │
│ Input format:             │  F1 Ask · F2 Explain · ...             │
│   Type your question      │  ──────────────────────────────────    │
│                           │                                        │
│ Index: 71 chunks          │  You: How does streaming work?         │
│ db: .codeassist/db        │  Assistant: The stream_ask function... │
│                           │  (live streaming preview below)        │
│ Model: haiku (fast)       │                                        │
│ Ctrl+S to toggle          │                                        │
├───────────────────────────┴────────────────────────────────────────┤
│ > Type your question...                                             │
└─ F1–F5 mode · Ctrl+S smart · Ctrl+L clear · Ctrl+C quit ───────────┘
```

### Keyboard shortcuts

| Key | Action |
|---|---|
| `F1` | Switch to Ask mode |
| `F2` | Switch to Explain mode |
| `F3` | Switch to Suggest mode |
| `F4` | Switch to Fix mode |
| `F5` | Switch to Index mode |
| `Ctrl+S` | Toggle between fast (haiku) and smart (sonnet) model |
| `Ctrl+L` | Clear the output area |
| `Ctrl+C` | Quit |

### Input format per mode

| Mode | What to type |
|---|---|
| **Ask** | Any question — queries the index automatically if built |
| **Explain** | `file.py` &nbsp; or &nbsp; `file.py --fn my_func` |
| **Suggest** | `file.py` &nbsp; or &nbsp; `file.py --ln 42` |
| **Fix** | `file.py` — streams analysis, shows diff, then type `y` to apply or `n` to skip |
| **Index** | `./src` &nbsp; or &nbsp; `. --reset` |

### Sidebar

The left sidebar updates in real time showing:
- Current mode and its input format
- Index status (chunk count, DB path)
- Active model (fast/smart)
- Contextual info for the last command (file name, function, line, fix status)

### Streaming

All LLM responses stream token-by-token into a live preview area at the
bottom of the output panel. When the response is complete it is committed
to the scrollable history above.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Your Anthropic API key |
| `CODEASSIST_FAST_MODEL` | No | `claude-haiku-4-5-20251001` | Model used by default |
| `CODEASSIST_SMART_MODEL` | No | `claude-sonnet-4-6` | Model used with `--smart` |

---

## Notes

- The embedding index (`.codeassist/db/`) is **per-project** — run `codeassist index` from each project root.
- The `all-MiniLM-L6-v2` model (~80 MB) is downloaded from HuggingFace on first use and cached locally.
- No data is sent to external servers except the code/question sent to the Anthropic API.
- The index only needs to be rebuilt when files are deleted or renamed (`--reset`). Editing or adding files can be handled by re-running `codeassist index` without `--reset`.
