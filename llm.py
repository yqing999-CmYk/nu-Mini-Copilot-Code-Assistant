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


def stream_response(
    system: str,
    user_text: str,
    file_content: Optional[str] = None,
    file_name: Optional[str] = None,
    smart: bool = False,
    max_tokens: int = 2048,
) -> Iterator[str]:
    """Generic streaming call with an optional cached file block.

    Used by explain / suggest / fix commands which each supply their own
    system prompt and user instruction.
    """
    model = SMART_MODEL if smart else FAST_MODEL

    if file_content:
        content: list = [
            {
                "type": "text",
                "text": f"File: {file_name or 'code'}\n\n```\n{file_content}\n```",
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": user_text},
        ]
    else:
        content = [{"type": "text", "text": user_text}]

    messages: list[anthropic.types.MessageParam] = [{"role": "user", "content": content}]

    with _client().messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    ) as stream:
        for text in stream.text_stream:
            yield text


def stream_ask(
    question: str,
    file_content: Optional[str] = None,
    file_name: Optional[str] = None,
    context_chunks: Optional[list[str]] = None,
    smart: bool = False,
) -> Iterator[str]:
    """Stream a response for a question.

    Priority of context:
      1. file_content  — a single file provided with --file
      2. context_chunks — retrieved from the embedding index
      3. no context    — plain LLM call
    """
    model = SMART_MODEL if smart else FAST_MODEL
    messages: list[anthropic.types.MessageParam] = []

    if file_content:
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"File: {file_name or 'snippet'}\n\n```\n{file_content}\n```",
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": question},
            ],
        })
    elif context_chunks:
        joined = "\n\n---\n\n".join(context_chunks)
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Relevant code from the codebase:\n\n{joined}",
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": question},
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
