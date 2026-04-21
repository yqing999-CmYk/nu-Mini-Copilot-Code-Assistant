import difflib
import re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.syntax import Syntax

from codeassist import llm
from codeassist.errors import handle_errors

console = Console()

SYSTEM = (
    "You are a code repair tool in a developer's terminal. "
    "Analyze the code for bugs, errors, type issues, and logic problems. "
    "First, briefly list each issue you found (if any). "
    "Then output the COMPLETE corrected file inside a single fenced code block. "
    "If no issues are found, say so and still output the original code in a code block. "
    "IMPORTANT: the code block must contain the full file — not a diff, not a snippet."
)


def _extract_code_block(text: str) -> Optional[str]:
    """Pull the first fenced code block out of the response."""
    match = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    return match.group(1) if match else None


def _render_diff(original: str, fixed: str, file_name: str) -> str:
    orig_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines, fixed_lines,
        fromfile=f"a/{file_name}",
        tofile=f"b/{file_name}",
    )
    return "".join(diff)


def fix_command(
    file: Path = typer.Argument(..., help="File to fix", exists=True),
    apply: bool = typer.Option(False, "--apply", help="Write the fix to disk after confirming"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt (implies --apply)"),
    smart: bool = typer.Option(False, "--smart", "-s", help="Use the smarter model"),
) -> None:
    """Detect issues in a file and suggest (or apply) a fix."""
    original = file.read_text(encoding="utf-8")
    console.print(f"[dim]Analyzing: {file}[/dim]\n")

    # Stream the full analysis + fixed code from Claude
    collected: list[str] = []
    with handle_errors():
        with Live(console=console, refresh_per_second=15, vertical_overflow="visible") as live:
            for chunk in llm.stream_response(
                system=SYSTEM,
                user_text="Find issues and provide the corrected file.",
                file_content=original,
                file_name=file.name,
                smart=smart,
                max_tokens=4096,
            ):
                collected.append(chunk)
                live.update(Markdown("".join(collected)))

    full_response = "".join(collected)
    console.print()

    fixed = _extract_code_block(full_response)
    if fixed is None:
        console.print("[yellow]Could not extract a corrected code block from the response.[/yellow]")
        raise typer.Exit(1)

    diff = _render_diff(original, fixed, file.name)

    if not diff.strip():
        console.print("[green]No changes — the file looks correct.[/green]")
        return

    # Show the diff
    console.print("\n[bold]Diff:[/bold]")
    console.print(Syntax(diff, "diff", theme="monokai", line_numbers=False))

    # Confirm before writing
    if yes or apply:
        confirmed = yes or typer.confirm("\nApply this fix?", default=False)
        if confirmed:
            file.write_text(fixed, encoding="utf-8")
            console.print(f"[green]Fix applied to {file}[/green]")
        else:
            console.print("[dim]Fix not applied.[/dim]")
    else:
        console.print("[dim]Run with --apply to write the fix to disk.[/dim]")
