from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live

from codeassist import llm

console = Console()


def ask_command(
    question: str = typer.Argument(..., help="Question to ask about the code"),
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Source file to use as context", exists=True
    ),
    smart: bool = typer.Option(
        False, "--smart", "-s", help="Use the smarter (slower) model"
    ),
) -> None:
    """Ask a question about code. Optionally provide a file as context."""
    file_content: Optional[str] = None
    file_name: Optional[str] = None

    if file:
        file_content = file.read_text(encoding="utf-8")
        file_name = file.name
        console.print(f"[dim]Context: {file}[/dim]")

    console.print()
    collected: list[str] = []

    with Live(console=console, refresh_per_second=15, vertical_overflow="visible") as live:
        for chunk in llm.stream_ask(question, file_content, file_name, smart=smart):
            collected.append(chunk)
            live.update(Markdown("".join(collected)))

    console.print()
