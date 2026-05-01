import textwrap
from pathlib import Path

import pytest

from codeassist.parser import (
    CHUNK_LINES,
    OVERLAP_LINES,
    SKIP_DIRS,
    SUPPORTED_EXTENSIONS,
    CodeChunk,
    parse_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_tmp(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# SUPPORTED_EXTENSIONS
# ---------------------------------------------------------------------------

def test_supported_extensions_keys():
    assert ".py" in SUPPORTED_EXTENSIONS
    assert ".js" in SUPPORTED_EXTENSIONS
    assert ".ts" in SUPPORTED_EXTENSIONS
    assert ".tsx" in SUPPORTED_EXTENSIONS
    assert ".jsx" in SUPPORTED_EXTENSIONS
    assert ".go" not in SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# Python parsing — named chunks
# ---------------------------------------------------------------------------

def test_python_function_extracted(tmp_path):
    f = write_tmp(tmp_path, "sample.py", """\
        def greet(name: str) -> str:
            return f"Hello, {name}"
    """)
    chunks = parse_file(f)
    names = [c.name for c in chunks]
    assert "greet" in names

    greet = next(c for c in chunks if c.name == "greet")
    assert greet.kind == "function"
    assert greet.language == "python"
    assert "def greet" in greet.content


def test_python_class_extracted(tmp_path):
    f = write_tmp(tmp_path, "sample.py", """\
        class Dog:
            def bark(self):
                return "woof"
    """)
    chunks = parse_file(f)
    names = [c.name for c in chunks]
    assert "Dog" in names

    dog = next(c for c in chunks if c.name == "Dog")
    assert dog.kind == "class"


def test_python_async_function_extracted(tmp_path):
    f = write_tmp(tmp_path, "sample.py", """\
        async def fetch(url: str) -> bytes:
            pass
    """)
    chunks = parse_file(f)
    assert any(c.name == "fetch" and c.kind == "function" for c in chunks)


def test_python_syntax_error_falls_back_to_sliding(tmp_path):
    f = write_tmp(tmp_path, "broken.py", "def (:\n    pass\n")
    chunks = parse_file(f)
    # Should not raise; falls back to sliding chunks
    assert isinstance(chunks, list)
    for c in chunks:
        assert isinstance(c, CodeChunk)


def test_python_line_range_is_accurate(tmp_path):
    src = "x = 1\n\ndef foo():\n    return 42\n"
    f = tmp_path / "lines.py"
    f.write_text(src)
    chunks = parse_file(f)
    foo = next((c for c in chunks if c.name == "foo"), None)
    assert foo is not None
    assert foo.start_line == 3
    assert foo.end_line == 4


# ---------------------------------------------------------------------------
# JS / TS parsing — sliding chunks
# ---------------------------------------------------------------------------

def test_ts_produces_sliding_chunks(tmp_path):
    lines = "\n".join(f"const x{i} = {i};" for i in range(80))
    f = write_tmp(tmp_path, "big.ts", lines)
    chunks = parse_file(f)
    assert len(chunks) > 1
    # All chunks should be of kind "chunk" (no AST)
    assert all(c.kind == "chunk" for c in chunks)


def test_ts_chunk_overlap(tmp_path):
    """Consecutive chunks should share OVERLAP_LINES lines."""
    lines = "\n".join(f"line{i}" for i in range(CHUNK_LINES + OVERLAP_LINES + 5))
    f = write_tmp(tmp_path, "sample.ts", lines)
    chunks = parse_file(f)
    assert len(chunks) >= 2
    # Second chunk starts before first chunk ends
    assert chunks[1].start_line < chunks[0].end_line


def test_js_extension_detected(tmp_path):
    f = write_tmp(tmp_path, "app.js", "function hello() { return 1; }\n")
    chunks = parse_file(f)
    assert all(c.language == "javascript" for c in chunks)


def test_jsx_extension_detected(tmp_path):
    f = write_tmp(tmp_path, "App.jsx", "export default function App() { return <div/>; }\n")
    chunks = parse_file(f)
    assert all(c.language == "javascript" for c in chunks)


# ---------------------------------------------------------------------------
# Unsupported / edge cases
# ---------------------------------------------------------------------------

def test_unsupported_extension_returns_empty(tmp_path):
    f = write_tmp(tmp_path, "notes.md", "# Hello\n")
    assert parse_file(f) == []


def test_empty_file_returns_empty(tmp_path):
    f = tmp_path / "empty.py"
    f.write_text("")
    assert parse_file(f) == []


def test_nonexistent_file_returns_empty():
    assert parse_file(Path("/nonexistent/file.py")) == []


# ---------------------------------------------------------------------------
# SKIP_DIRS content
# ---------------------------------------------------------------------------

def test_skip_dirs_contains_common_noise():
    for d in ("node_modules", "__pycache__", ".git", ".venv", "dist", "build"):
        assert d in SKIP_DIRS
