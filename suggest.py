from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from codeassist import llm

console = Console()

SYSTEM = (
    "You are a concise code reviewer in a developer's terminal. "
    "Suggest concrete, actionable improvements to the code. "
    "Focus on: correctness, readability, edge cases, and performance. "
    "Reference line numbers where relevant. Be specific, not generic."
)

CONTEXT_RADIUS = 25  # lines above and below --ln target


def suggest_command(
    file: Path = typer.Argument(..., help="File to review", exists=True),
    ln: Optional[int] = typer.Option(
        None, "--ln", help="Focus suggestions around this line number"
    ),
    smart: bool = typer.Option(False, "--smart", "-s", help="Use the smarter model"),
) -> None:
    """Suggest improvements for a file or a specific line region."""
    lines = file.read_text(encoding="utf-8").splitlines()

    if ln is not None:
        if ln < 1 or ln > len(lines):
            console.print(f"[red]Line {ln} is out of range (file has {len(lines)} lines)[/red]")
            raise typer.Exit(1)
        start = max(0, ln - 1 - CONTEXT_RADIUS)
        end = min(len(lines), ln - 1 + CONTEXT_RADIUS)
        snippet = "\n".join(
            f"{i + 1:4d}  {line}" for i, line in enumerate(lines[start:end], start=start)
        )
        file_content = snippet
        user_text = (
            f"Suggest improvements for the code around line {ln}. "
            "Line numbers are shown on the left."
        )
        console.print(f"[dim]Reviewing {file} around line {ln} (lines {start+1}–{end})[/dim]")
    else:
        # Number every line so Claude can reference them precisely
        file_content = "\n".join(
            f"{i + 1:4d}  {line}" for i, line in enumerate(lines)
        )
        user_text = "Suggest improvements for this file. Line numbers are shown on the left."
        console.print(f"[dim]Reviewing: {file}[/dim]")

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
