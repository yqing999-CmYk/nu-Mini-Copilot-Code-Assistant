import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

CHUNK_LINES = 50
OVERLAP_LINES = 10

# Directories to skip when walking a codebase
SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".venv", "venv", "dist", "build", ".codeassist"}


@dataclass
class CodeChunk:
    content: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    name: Optional[str] = None   # function / class name if available
    kind: Optional[str] = None   # "function" | "class" | "chunk"


def parse_file(path: Path) -> list[CodeChunk]:
    ext = path.suffix.lower()
    language = SUPPORTED_EXTENSIONS.get(ext)
    if language is None:
        return []

    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    if not source.strip():
        return []

    if language == "python":
        return _parse_python(source, str(path))
    else:
        return _sliding_chunks(source, str(path), language)


def _parse_python(source: str, file_path: str) -> list[CodeChunk]:
    """Use stdlib ast to extract function/class chunks, plus sliding chunks for the rest."""
    lines = source.splitlines()
    chunks: list[CodeChunk] = []
    covered: set[int] = set()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _sliding_chunks(source, file_path, "python")

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = node.lineno - 1           # 0-based
        end = node.end_lineno             # type: ignore[attr-defined]
        content = "\n".join(lines[start:end])
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        chunks.append(CodeChunk(
            content=content,
            file_path=file_path,
            language="python",
            start_line=start + 1,
            end_line=end,
            name=node.name,
            kind=kind,
        ))
        covered.update(range(start, end))

    # Sliding chunks for module-level lines not inside any def/class
    uncovered = [i for i in range(len(lines)) if i not in covered]
    chunks.extend(_chunks_from_line_indices(uncovered, lines, file_path, "python"))

    return chunks


def _chunks_from_line_indices(
    indices: list[int],
    lines: list[str],
    file_path: str,
    language: str,
) -> list[CodeChunk]:
    """Group consecutive indices into sliding chunks."""
    chunks: list[CodeChunk] = []
    group: list[int] = []

    def flush(g: list[int]) -> None:
        if len(g) < 4:
            return
        content = "\n".join(lines[i] for i in g)
        chunks.append(CodeChunk(
            content=content,
            file_path=file_path,
            language=language,
            start_line=g[0] + 1,
            end_line=g[-1] + 1,
            kind="chunk",
        ))

    for idx in indices:
        if group and idx != group[-1] + 1:
            flush(group)
            group = []
        group.append(idx)
    flush(group)
    return chunks


def _sliding_chunks(source: str, file_path: str, language: str) -> list[CodeChunk]:
    """Split source into overlapping line windows."""
    lines = source.splitlines()
    chunks: list[CodeChunk] = []
    i = 0
    while i < len(lines):
        end = min(i + CHUNK_LINES, len(lines))
        content = "\n".join(lines[i:end])
        if content.strip():
            chunks.append(CodeChunk(
                content=content,
                file_path=file_path,
                language=language,
                start_line=i + 1,
                end_line=end,
                kind="chunk",
            ))
        i += CHUNK_LINES - OVERLAP_LINES
    return chunks
