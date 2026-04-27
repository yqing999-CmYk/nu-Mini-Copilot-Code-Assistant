import sys
import typer
from rich.console import Console

# Ensure stdout/stderr use UTF-8 on Windows so Rich can render Unicode
# spinner characters, box-drawing lines, and emoji without crashing.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from codeassist.commands.ask import ask_command
from codeassist.commands.explain import explain_command
from codeassist.commands.fix import fix_command
from codeassist.commands.index import index_command
from codeassist.commands.suggest import suggest_command
from codeassist.ui import launch as _launch_ui

app = typer.Typer(
    name="codeassist",
    help="Lightweight CLI code assistant — write, understand, and improve code.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

app.command("ask")(ask_command)
app.command("index")(index_command)
app.command("explain")(explain_command)
app.command("suggest")(suggest_command)
app.command("fix")(fix_command)


@app.command("ui")
def ui_command(
    db_path: str = typer.Option(
        ".codeassist/db", "--db", help="Path to the vector database"
    ),
) -> None:
    """Launch the interactive terminal UI."""
    _launch_ui(db_path=db_path)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
