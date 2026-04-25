from contextlib import contextmanager
from typing import Iterator

import anthropic
from rich.console import Console
from rich.panel import Panel

console = Console(stderr=True)


@contextmanager
def handle_errors() -> Iterator[None]:
    """Catch known API and config errors and print a clean message instead of a traceback."""
    try:
        yield
    except EnvironmentError as e:
        console.print(Panel(str(e), title="[red]Configuration Error[/red]", border_style="red"))
        raise SystemExit(1)
    except anthropic.AuthenticationError:
        console.print(Panel(
            "Invalid API key.\n"
            "Check that ANTHROPIC_API_KEY is set correctly in your .env file.",
            title="[red]Authentication Error[/red]",
            border_style="red",
        ))
        raise SystemExit(1)
    except anthropic.RateLimitError:
        console.print(Panel(
            "Rate limit reached. Wait a moment and try again.",
            title="[red]Rate Limit[/red]",
            border_style="red",
        ))
        raise SystemExit(1)
    except anthropic.APIConnectionError:
        console.print(Panel(
            "Could not connect to the Anthropic API.\n"
            "Check your internet connection and try again.",
            title="[red]Connection Error[/red]",
            border_style="red",
        ))
        raise SystemExit(1)
    except anthropic.APIError as e:
        console.print(Panel(
            str(e),
            title="[red]API Error[/red]",
            border_style="red",
        ))
        raise SystemExit(1)
