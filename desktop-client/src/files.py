"""File system access — read, write, list files on desktop."""

# TODO: Implement:
#   - list_directory(path) — ls with metadata
#   - read_file(path) — read text file content
#   - write_file(path, content) — write/create file
#   - file_info(path) — size, modified date, type
#   - search_files(pattern, root) — glob search
#   - Safety: configurable allowed directories, max file size

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def list_directory(path: str = ".") -> list[dict]:
    """List directory contents with metadata."""
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        return []
    return [
        {"name": item.name, "is_dir": item.is_dir(), "size": item.stat().st_size if item.is_file() else 0}
        for item in sorted(p.iterdir())
    ]


def read_file(path: str, max_size: int = 1_000_000) -> str | None:
    """Read text file content (up to max_size bytes)."""
    p = Path(path).expanduser().resolve()
    if not p.is_file() or p.stat().st_size > max_size:
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def write_file(path: str, content: str) -> bool:
    """Write content to file."""
    p = Path(path).expanduser().resolve()
    p.write_text(content, encoding="utf-8")
    return True
