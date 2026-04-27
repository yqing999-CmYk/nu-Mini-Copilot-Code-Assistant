from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from codeassist import embeddings as emb
from codeassist.parser import SKIP_DIRS, SUPPORTED_EXTENSIONS, parse_file

console = Console()


def index_command(
    directory: Path = typer.Argument(
        ..., help="Directory to index", exists=True, file_okay=False
    ),
    db_path: str = typer.Option(
        ".codeassist/db", "--db", help="Path to store the vector database"
    ),
    reset: bool = typer.Option(
        False, "--reset", help="Delete existing index before re-indexing"
    ),
) -> None:
    """Index a codebase to enable context-aware queries with `ask`."""

    if reset and Path(db_path).exists():
        import shutil
        shutil.rmtree(db_path)
        console.print(f"[dim]Cleared existing index at {db_path}[/dim]")

    # Collect supported files, skipping irrelevant dirs
    all_files: list[Path] = []
    for f in directory.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        all_files.append(f)

    if not all_files:
        console.print(f"[yellow]No supported files (.py, .js, .ts, .tsx) found in {directory}[/yellow]")
        raise typer.Exit(1)

    console.print(f"[dim]Found {len(all_files)} file(s).[/dim]")

    # Parse all files into chunks
    all_chunks = []
    with Progress(
        SpinnerColumn("line"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing...", total=len(all_files))
        for f in all_files:
            all_chunks.extend(parse_file(f))
            progress.advance(task)

    if not all_chunks:
        console.print("[yellow]No code chunks extracted — files may be empty.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[dim]Extracted {len(all_chunks)} chunk(s). Loading embedding model...[/dim]")

    # Embed and store
    with Progress(
        SpinnerColumn("line"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Embedding and storing...", total=None)
        stored = emb.index_chunks(all_chunks, db_path=db_path)
        progress.stop_task(task)

    console.print(f"[green]Done.[/green] Indexed [bold]{stored}[/bold] chunks from "
                  f"[bold]{len(all_files)}[/bold] files.")
    console.print(f"[dim]Index saved to: {db_path}[/dim]")
    console.print("[dim]Run `codeassist ask \"...\"` to query the codebase.[/dim]")
