from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from codeassist import embeddings as emb
from codeassist import llm

console = Console()


def ask_command(
    question: str = typer.Argument(..., help="Question to ask about the code"),
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Source file to use as context", exists=True
    ),
    db_path: str = typer.Option(
        ".codeassist/db", "--db", help="Path to the vector database"
    ),
    top_k: int = typer.Option(
        5, "--top-k", "-k", help="Number of index chunks to retrieve"
    ),
    smart: bool = typer.Option(
        False, "--smart", "-s", help="Use the smarter (slower) model"
    ),
) -> None:
    """Ask a question about code. Uses --file for direct context, or the index when available."""
    file_content: Optional[str] = None
    file_name: Optional[str] = None
    context_chunks: Optional[list[str]] = None

    if file:
        file_content = file.read_text(encoding="utf-8")
        file_name = file.name
        console.print(f"[dim]Context: {file}[/dim]")
    elif emb.db_exists(db_path):
        results = emb.query_index(question, db_path=db_path, top_k=top_k)
        if results:
            context_chunks = [r["content"] for r in results]
            sources = sorted({r["metadata"]["file_path"] for r in results})
            console.print(f"[dim]Retrieved {len(results)} chunk(s) from index:[/dim]")
            for s in sources:
                console.print(f"[dim]  {s}[/dim]")

    console.print()
    collected: list[str] = []

    with Live(console=console, refresh_per_second=15, vertical_overflow="visible") as live:
        for chunk in llm.stream_ask(
            question,
            file_content=file_content,
            file_name=file_name,
            context_chunks=context_chunks,
            smart=smart,
        ):
            collected.append(chunk)
            live.update(Markdown("".join(collected)))

    console.print()
