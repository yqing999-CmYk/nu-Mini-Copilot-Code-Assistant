from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from codeassist import llm
from codeassist.parser import parse_file

console = Console()

SYSTEM = (
    "You are a concise code assistant in a developer's terminal. "
    "Explain code clearly: what it does, how it works, key logic, and any gotchas. "
    "Use fenced code blocks when showing examples. Get to the point."
)


def explain_command(
    file: Path = typer.Argument(..., help="File to explain", exists=True),
    fn: Optional[str] = typer.Option(
        None, "--fn", help="Name of a specific function or class to explain"
    ),
    smart: bool = typer.Option(False, "--smart", "-s", help="Use the smarter model"),
) -> None:
    """Explain a file or a specific function/class within it."""
    source = file.read_text(encoding="utf-8")

    if fn:
        # Extract just the named function/class via parser
        chunks = parse_file(file)
        match = next((c for c in chunks if c.name == fn), None)
        if match is None:
            console.print(f"[red]No function or class named '{fn}' found in {file}[/red]")
            raise typer.Exit(1)
        file_content = match.content
        label = f"{fn} ({match.kind}) — {file.name} lines {match.start_line}-{match.end_line}"
        console.print(f"[dim]Explaining: {label}[/dim]")
    else:
        file_content = source
        console.print(f"[dim]Explaining: {file}[/dim]")

    user_text = f"Explain this code." if not fn else f"Explain the `{fn}` {_kind(fn, file)} in detail."

    console.print()
    collected: list[str] = []
    with Live(console=console, refresh_per_second=15, vertical_overflow="visible") as live:
        for chunk in llm.stream_response(
            system=SYSTEM,
            user_text=user_text,
            file_content=file_content,
            file_name=file.name,
            smart=smart,
        ):
            collected.append(chunk)
            live.update(Markdown("".join(collected)))
    console.print()


def _kind(fn: str, file: Path) -> str:
    """Best-effort label — just used in the prompt string."""
    chunks = parse_file(file)
    match = next((c for c in chunks if c.name == fn), None)
    return match.kind if match else "symbol"
