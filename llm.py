from collections.abc import Iterator
from typing import Optional

import anthropic

from codeassist.config import FAST_MODEL, SMART_MODEL, require_api_key

SYSTEM_PROMPT = (
    "You are a concise code assistant embedded in a developer's terminal. "
    "Answer questions about code clearly and briefly. "
    "When showing code, use fenced code blocks with the language tag. "
    "Avoid lengthy preamble — get to the point."
)


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=require_api_key())


def stream_ask(
    question: str,
    file_content: Optional[str] = None,
    file_name: Optional[str] = None,
    smart: bool = False,
) -> Iterator[str]:
    """Stream a response for a plain question, with optional file context."""
    model = SMART_MODEL if smart else FAST_MODEL

    messages: list[anthropic.types.MessageParam] = []

    if file_content:
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"File: {file_name or 'snippet'}\n\n```\n{file_content}\n```",
                    # cache the file content so repeated questions on the same file
                    # don't re-tokenize it
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": question,
                },
            ],
        })
    else:
        messages.append({"role": "user", "content": question})

    with _client().messages.stream(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    ) as stream:
        for text in stream.text_stream:
            yield text
