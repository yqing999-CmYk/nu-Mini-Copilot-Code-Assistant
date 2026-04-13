import typer
from rich.console import Console

from codeassist.commands.ask import ask_command

app = typer.Typer(
    name="codeassist",
    help="Lightweight CLI code assistant — write, understand, and improve code.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

app.command("ask")(ask_command)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
