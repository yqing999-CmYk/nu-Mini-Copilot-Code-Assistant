"""
codeassist/ui.py — Textual TUI for CodeAssist Mini Copilot

Layout:
    ┌─ Header ──────────────────────────────────────────────┐
    │ [F1 Ask] [F2 Explain] [F3 Suggest] [F4 Fix] [F5 Index]│
    ├─ Sidebar ────────┬─ Output ───────────────────────────┤
    │ Mode: Ask        │  (history log)                     │
    │ Index: 71 chunks │  ...                               │
    │ Model: haiku     │  (current stream, updates live)    │
    ├──────────────────┴────────────────────────────────────┤
    │ > input...                                             │
    └── Footer (key hints) ─────────────────────────────────┘
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.markdown import Markdown as RichMarkdown
from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

from codeassist import embeddings as emb
from codeassist import llm
from codeassist.commands.fix import _extract_code_block, _render_diff
from codeassist.config import FAST_MODEL, SMART_MODEL
from codeassist.errors import handle_errors
from codeassist.parser import parse_file

# ── Mode definitions ──────────────────────────────────────────────────────────

MODES: dict[str, dict] = {
    "ask":     {"key": "F1", "label": "Ask",     "hint": "Type your question and press Enter"},
    "explain": {"key": "F2", "label": "Explain", "hint": "file.py  or  file.py --fn my_func"},
    "suggest": {"key": "F3", "label": "Suggest", "hint": "file.py  or  file.py --ln 42"},
    "fix":     {"key": "F4", "label": "Fix",     "hint": "file.py"},
    "index":   {"key": "F5", "label": "Index",   "hint": "path/to/directory"},
}

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
Screen {
    background: $surface;
    layers: base overlay;
}

/* ── Mode bar ── */
#modebar {
    height: 3;
    layout: horizontal;
    background: $panel;
    border-bottom: solid $primary-darken-2;
}

.mode-btn {
    width: 1fr;
    height: 3;
    background: $panel;
    border: none;
    color: $text-muted;
}

.mode-btn:hover {
    background: $panel-lighten-1;
    color: $text;
}

.mode-btn.active {
    background: $primary;
    color: $text;
    text-style: bold;
}

/* ── Main area ── */
#main {
    height: 1fr;
    layout: horizontal;
}

/* ── Sidebar ── */
#sidebar {
    width: 30;
    background: $panel;
    border-right: solid $panel-darken-2;
    padding: 1 2;
    overflow-y: auto;
}

.sidebar-section {
    color: $primary;
    text-style: bold;
    margin-top: 1;
    width: 100%;
}

.sidebar-row {
    color: $text-muted;
    width: 100%;
    margin-bottom: 0;
}

/* ── Output area ── */
#output-scroll {
    width: 1fr;
    background: $surface;
}

#history {
    padding: 0 1;
    background: $surface;
}

#stream {
    padding: 0 1;
    height: auto;
    background: $surface;
}

/* ── Input bar ── */
#prompt {
    dock: bottom;
    height: 3;
    border-top: solid $panel-darken-2;
    background: $panel;
    padding: 0 1;
}
"""

# ── Sidebar widget ─────────────────────────────────────────────────────────────

class Sidebar(Static):
    """Left panel showing mode, context, and settings."""

    def update_content(
        self,
        mode: str,
        smart: bool,
        db_path: str,
        extra: dict,
    ) -> None:
        m = MODES[mode]
        model_name = SMART_MODEL.split("-")[1] if smart else FAST_MODEL.split("-")[1]
        model_label = f"{'sonnet' if smart else 'haiku'} ({'smart' if smart else 'fast'})"

        # Index status
        if emb.db_exists(db_path):
            try:
                import chromadb
                client = chromadb.PersistentClient(path=db_path)
                col = client.get_or_create_collection("codebase")
                count = col.count()
                index_status = f"{count} chunks"
            except Exception:
                index_status = "exists"
        else:
            index_status = "not built"

        lines = [
            f"[bold cyan]Mode[/bold cyan]",
            f"  {m['key']} · {m['label']}",
            "",
            f"[bold cyan]Input format[/bold cyan]",
            f"  {m['hint']}",
            "",
            f"[bold cyan]Index[/bold cyan]",
            f"  {index_status}",
            f"  db: {db_path}",
            "",
            f"[bold cyan]Model[/bold cyan]",
            f"  {model_label}",
            f"  Ctrl+S to toggle",
        ]

        # Extra context (file, fn, ln) set by the user
        if extra:
            lines += ["", "[bold cyan]Context[/bold cyan]"]
            for k, v in extra.items():
                lines.append(f"  {k}: {v}")

        self.update("\n".join(lines))


# ── Main App ──────────────────────────────────────────────────────────────────

class CodeAssistApp(App):
    """Textual TUI for CodeAssist Mini Copilot."""

    CSS = CSS
    TITLE = "CodeAssist Mini Copilot"

    BINDINGS = [
        Binding("f1", "set_mode('ask')",     "Ask",     show=True),
        Binding("f2", "set_mode('explain')", "Explain", show=True),
        Binding("f3", "set_mode('suggest')", "Suggest", show=True),
        Binding("f4", "set_mode('fix')",     "Fix",     show=True),
        Binding("f5", "set_mode('index')",   "Index",   show=True),
        Binding("ctrl+s", "toggle_smart",    "Smart",   show=True),
        Binding("ctrl+l", "clear_output",    "Clear",   show=True),
        Binding("ctrl+c", "quit",            "Quit",    show=True),
    ]

    current_mode: reactive[str] = reactive("ask")
    smart: reactive[bool] = reactive(False)
    db_path: str = ".codeassist/db"

    # State for pending fix confirmation
    _pending_fix: Optional[tuple[Path, str]] = None   # (file, fixed_content)
    _streaming: bool = False
    _stream_buffer: list[str] = []
    _context: dict = {}

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)

        # Mode bar
        with Horizontal(id="modebar"):
            for mode, info in MODES.items():
                label = f"{info['key']} {info['label']}"
                btn = Button(label, id=f"btn-{mode}", classes="mode-btn")
                yield btn

        # Main content
        with Horizontal(id="main"):
            yield Sidebar(id="sidebar")
            with VerticalScroll(id="output-scroll"):
                yield RichLog(id="history", highlight=True, markup=True, wrap=True)
                yield Static("", id="stream", markup=True)

        yield Input(placeholder=MODES["ask"]["hint"], id="prompt")
        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._refresh_sidebar()
        self._mark_active_btn("ask")
        history = self.query_one("#history", RichLog)
        history.write(
            Text.from_markup(
                "[bold green]CodeAssist Mini Copilot[/bold green]\n"
                "F1 Ask · F2 Explain · F3 Suggest · F4 Fix · F5 Index\n"
                "Ctrl+S toggle smart model · Ctrl+L clear · Ctrl+C quit\n"
                "─" * 60
            )
        )
        if emb.db_exists(self.db_path):
            history.write(Text.from_markup("[dim]Index found. Ready.[/dim]"))
        else:
            history.write(
                Text.from_markup("[yellow]No index found. Press F5 and enter a directory to index your codebase.[/yellow]")
            )

    # ── Mode switching ────────────────────────────────────────────────────────

    def action_set_mode(self, mode: str) -> None:
        self.current_mode = mode
        self._context = {}
        self._pending_fix = None
        prompt = self.query_one("#prompt", Input)
        prompt.placeholder = MODES[mode]["hint"]
        prompt.value = ""
        self._mark_active_btn(mode)
        self._refresh_sidebar()

    def _mark_active_btn(self, mode: str) -> None:
        for m in MODES:
            btn = self.query_one(f"#btn-{m}", Button)
            if m == mode:
                btn.add_class("active")
            else:
                btn.remove_class("active")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("btn-"):
            self.action_set_mode(btn_id[4:])

    # ── Smart toggle ──────────────────────────────────────────────────────────

    def action_toggle_smart(self) -> None:
        self.smart = not self.smart
        label = "smart (sonnet)" if self.smart else "fast (haiku)"
        self._write_system(f"Model: {label}")
        self._refresh_sidebar()

    # ── Clear ─────────────────────────────────────────────────────────────────

    def action_clear_output(self) -> None:
        self.query_one("#history", RichLog).clear()
        self.query_one("#stream", Static).update("")
        self._pending_fix = None
        self._context = {}

    # ── Input handling ────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            return
        self.query_one("#prompt", Input).value = ""

        if self._pending_fix is not None:
            self._handle_fix_confirm(value)
            return

        mode = self.current_mode
        if mode == "ask":
            self._run_ask(value)
        elif mode == "explain":
            self._run_explain(value)
        elif mode == "suggest":
            self._run_suggest(value)
        elif mode == "fix":
            self._run_fix(value)
        elif mode == "index":
            self._run_index(value)

    # ── Output helpers ────────────────────────────────────────────────────────

    def _write_user(self, text: str) -> None:
        history = self.query_one("#history", RichLog)
        history.write(Text.from_markup(f"\n[bold yellow]You:[/bold yellow] {text}"))

    def _write_system(self, text: str) -> None:
        history = self.query_one("#history", RichLog)
        history.write(Text.from_markup(f"[dim]{text}[/dim]"))

    def _write_error(self, text: str) -> None:
        history = self.query_one("#history", RichLog)
        history.write(Text.from_markup(f"[bold red]Error:[/bold red] {text}"))

    def _stream_chunk(self, chunk: str) -> None:
        """Append a streamed token and refresh the live preview."""
        self._stream_buffer.append(chunk)
        text = "".join(self._stream_buffer)
        stream_widget = self.query_one("#stream", Static)
        stream_widget.update(RichMarkdown(text))
        self.query_one("#output-scroll", VerticalScroll).scroll_end(animate=False)

    def _stream_done(self) -> None:
        """Move completed stream to history log and clear the preview."""
        final = "".join(self._stream_buffer)
        self._stream_buffer = []
        history = self.query_one("#history", RichLog)
        history.write(Text.from_markup("[bold green]Assistant:[/bold green]"))
        history.write(RichMarkdown(final))
        self.query_one("#stream", Static).update("")
        self._streaming = False
        self.query_one("#output-scroll", VerticalScroll).scroll_end(animate=False)

    def _refresh_sidebar(self) -> None:
        self.query_one("#sidebar", Sidebar).update_content(
            self.current_mode, self.smart, self.db_path, self._context
        )

    # ── Ask ───────────────────────────────────────────────────────────────────

    def _run_ask(self, question: str) -> None:
        self._write_user(question)
        context_chunks = None

        if emb.db_exists(self.db_path):
            results = emb.query_index(question, db_path=self.db_path, top_k=5)
            if results:
                context_chunks = [r["content"] for r in results]
                sources = sorted({r["metadata"]["file_path"] for r in results})
                self._write_system(f"Retrieved {len(results)} chunk(s): {', '.join(sources)}")

        self._stream_buffer = []
        self._streaming = True
        self._do_stream_ask(question, context_chunks)

    @work(thread=True)
    def _do_stream_ask(self, question: str, context_chunks: Optional[list[str]]) -> None:
        try:
            for chunk in llm.stream_ask(question, context_chunks=context_chunks, smart=self.smart):
                self.call_from_thread(self._stream_chunk, chunk)
        except Exception as e:
            self.call_from_thread(self._write_error, str(e))
        finally:
            self.call_from_thread(self._stream_done)

    # ── Explain ───────────────────────────────────────────────────────────────

    def _run_explain(self, value: str) -> None:
        parts = value.split()
        file_path = Path(parts[0])
        fn_name = None

        if "--fn" in parts:
            idx = parts.index("--fn")
            if idx + 1 < len(parts):
                fn_name = parts[idx + 1]

        if not file_path.exists():
            self._write_error(f"File not found: {file_path}")
            return

        source = file_path.read_text(encoding="utf-8")
        file_content = source
        user_text = "Explain this code."

        if fn_name:
            chunks = parse_file(file_path)
            match = next((c for c in chunks if c.name == fn_name), None)
            if match is None:
                self._write_error(f"No function/class named '{fn_name}' in {file_path}")
                return
            file_content = match.content
            user_text = f"Explain the `{fn_name}` {match.kind} in detail."
            self._context = {"file": file_path.name, "fn": fn_name}
        else:
            self._context = {"file": file_path.name}

        self._write_user(f"explain {value}")
        self._refresh_sidebar()
        self._stream_buffer = []
        self._streaming = True
        self._do_stream_response(llm.SYSTEM_PROMPT, user_text, file_content, file_path.name)

    # ── Suggest ───────────────────────────────────────────────────────────────

    SUGGEST_SYSTEM = (
        "You are a concise code reviewer in a developer's terminal. "
        "Suggest concrete, actionable improvements. Focus on correctness, "
        "readability, edge cases, and performance. Reference line numbers where relevant."
    )

    def _run_suggest(self, value: str) -> None:
        parts = value.split()
        file_path = Path(parts[0])
        ln = None

        if "--ln" in parts:
            idx = parts.index("--ln")
            if idx + 1 < len(parts):
                try:
                    ln = int(parts[idx + 1])
                except ValueError:
                    self._write_error("--ln value must be an integer")
                    return

        if not file_path.exists():
            self._write_error(f"File not found: {file_path}")
            return

        lines = file_path.read_text(encoding="utf-8").splitlines()

        if ln is not None:
            start = max(0, ln - 1 - 25)
            end = min(len(lines), ln - 1 + 25)
            snippet = "\n".join(f"{i+1:4d}  {l}" for i, l in enumerate(lines[start:end], start=start))
            file_content = snippet
            user_text = f"Suggest improvements around line {ln}. Line numbers are shown."
            self._context = {"file": file_path.name, "ln": ln}
        else:
            file_content = "\n".join(f"{i+1:4d}  {l}" for i, l in enumerate(lines))
            user_text = "Suggest improvements for this file. Line numbers are shown."
            self._context = {"file": file_path.name}

        self._write_user(f"suggest {value}")
        self._refresh_sidebar()
        self._stream_buffer = []
        self._streaming = True
        self._do_stream_response(self.SUGGEST_SYSTEM, user_text, file_content, file_path.name)

    # ── Fix ───────────────────────────────────────────────────────────────────

    FIX_SYSTEM = (
        "You are a code repair tool in a developer's terminal. "
        "Analyze the code for bugs, errors, type issues, and logic problems. "
        "First, briefly list each issue found (if any). "
        "Then output the COMPLETE corrected file inside a single fenced code block. "
        "If no issues are found, say so and still output the original code in a code block. "
        "IMPORTANT: the code block must contain the full file — not a diff, not a snippet."
    )

    def _run_fix(self, value: str) -> None:
        file_path = Path(value.strip())
        if not file_path.exists():
            self._write_error(f"File not found: {file_path}")
            return

        self._context = {"file": file_path.name, "status": "analysing..."}
        self._write_user(f"fix {value}")
        self._refresh_sidebar()
        self._stream_buffer = []
        self._streaming = True
        self._do_stream_fix(file_path)

    @work(thread=True)
    def _do_stream_fix(self, file_path: Path) -> None:
        original = file_path.read_text(encoding="utf-8")
        try:
            for chunk in llm.stream_response(
                system=self.FIX_SYSTEM,
                user_text="Find issues and provide the corrected file.",
                file_content=original,
                file_name=file_path.name,
                smart=self.smart,
                max_tokens=4096,
            ):
                self.call_from_thread(self._stream_chunk, chunk)
        except Exception as e:
            self.call_from_thread(self._write_error, str(e))
            self.call_from_thread(self._stream_done)
            return

        full_response = "".join(self._stream_buffer)
        self.call_from_thread(self._stream_done)

        fixed = _extract_code_block(full_response)
        if fixed is None:
            self.call_from_thread(self._write_error, "Could not extract corrected code block.")
            return

        diff = _render_diff(original, fixed, file_path.name)
        if not diff.strip():
            self.call_from_thread(self._write_system, "No changes — file looks correct.")
            return

        # Show diff and ask for confirmation
        self.call_from_thread(self._show_fix_diff, file_path, fixed, diff)

    def _show_fix_diff(self, file_path: Path, fixed: str, diff: str) -> None:
        history = self.query_one("#history", RichLog)
        history.write(Text.from_markup("\n[bold]Diff:[/bold]"))
        history.write(Syntax(diff, "diff", theme="monokai"))
        history.write(Text.from_markup(
            "\n[bold yellow]Apply this fix?[/bold yellow]  Type [bold]y[/bold] to apply, [bold]n[/bold] to skip."
        ))
        self._pending_fix = (file_path, fixed)
        self._context["status"] = "awaiting confirm"
        self._refresh_sidebar()
        self.query_one("#prompt", Input).placeholder = "y to apply, n to skip"
        self.query_one("#output-scroll", VerticalScroll).scroll_end(animate=False)

    def _handle_fix_confirm(self, value: str) -> None:
        if self._pending_fix is None:
            return
        file_path, fixed = self._pending_fix
        self._pending_fix = None
        self.query_one("#prompt", Input).placeholder = MODES[self.current_mode]["hint"]

        if value.lower() == "y":
            try:
                file_path.write_text(fixed, encoding="utf-8")
                self._write_system(f"Fix applied to {file_path}")
                self._context["status"] = "fix applied"
            except OSError as e:
                self._write_error(str(e))
        else:
            self._write_system("Fix not applied.")
            self._context["status"] = "skipped"

        self._refresh_sidebar()

    # ── Index ─────────────────────────────────────────────────────────────────

    def _run_index(self, value: str) -> None:
        parts = value.split()
        directory = Path(parts[0])
        reset = "--reset" in parts

        if not directory.exists() or not directory.is_dir():
            self._write_error(f"Directory not found: {directory}")
            return

        self._write_user(f"index {value}")
        self._context = {"dir": str(directory), "status": "indexing..."}
        self._refresh_sidebar()
        self._do_index(directory, reset)

    @work(thread=True)
    def _do_index(self, directory: Path, reset: bool) -> None:
        from codeassist.parser import SKIP_DIRS, SUPPORTED_EXTENSIONS, parse_file as _parse
        import shutil

        if reset and Path(self.db_path).exists():
            shutil.rmtree(self.db_path)
            self.call_from_thread(self._write_system, f"Cleared existing index.")

        all_files = [
            f for f in directory.rglob("*")
            if f.is_file()
            and f.suffix.lower() in SUPPORTED_EXTENSIONS
            and not any(p in SKIP_DIRS for p in f.parts)
        ]

        if not all_files:
            self.call_from_thread(self._write_error, f"No supported files found in {directory}")
            return

        self.call_from_thread(self._write_system, f"Found {len(all_files)} file(s). Parsing...")

        all_chunks = []
        for f in all_files:
            all_chunks.extend(_parse(f))

        self.call_from_thread(self._write_system, f"Extracted {len(all_chunks)} chunk(s). Embedding...")

        stored = emb.index_chunks(all_chunks, db_path=self.db_path)

        self.call_from_thread(self._write_system,
            f"[green]Done.[/green] Indexed {stored} chunks from {len(all_files)} files → {self.db_path}")
        self.call_from_thread(self._update_index_context, stored, len(all_files))

    def _update_index_context(self, stored: int, files: int) -> None:
        self._context = {"dir": self._context.get("dir", "."), "status": f"{stored} chunks, {files} files"}
        self._refresh_sidebar()

    # ── Generic stream worker ─────────────────────────────────────────────────

    @work(thread=True)
    def _do_stream_response(
        self, system: str, user_text: str, file_content: str, file_name: str
    ) -> None:
        try:
            for chunk in llm.stream_response(
                system=system,
                user_text=user_text,
                file_content=file_content,
                file_name=file_name,
                smart=self.smart,
            ):
                self.call_from_thread(self._stream_chunk, chunk)
        except Exception as e:
            self.call_from_thread(self._write_error, str(e))
        finally:
            self.call_from_thread(self._stream_done)


def launch(db_path: str = ".codeassist/db") -> None:
    """Entry point called by the `codeassist ui` command."""
    app = CodeAssistApp()
    app.db_path = db_path
    app.run()
