"""File system access — read, write, list files on the desktop.

All operations are restricted to a configurable set of allowed directories
(defaults to user home ``~``). Paths outside these directories are rejected.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default maximum file size for reads (1 MB)
_MAX_READ_SIZE = 1_000_000

# Allowed root directories — paths outside these are denied.
# Populated by ``set_allowed_directories``.
_allowed_roots: list[Path] = [Path.home()]


def set_allowed_directories(dirs: list[str]) -> None:
    """Configure which directories the file module can access."""
    global _allowed_roots  # noqa: PLW0603
    _allowed_roots = [Path(d).expanduser().resolve() for d in dirs]


def _check_allowed(path: Path) -> bool:
    """Return True if *path* is inside one of the allowed root directories."""
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in _allowed_roots)


def list_directory(path: str = ".") -> list[dict] | dict:
    """List directory contents with metadata.

    Returns:
        A list of dicts with ``name``, ``is_dir``, ``size`` keys,
        or an error dict if the path is disallowed or invalid.
    """
    p = Path(path).expanduser().resolve()
    if not _check_allowed(p):
        return {"error": "Access denied — path outside allowed directories"}
    if not p.is_dir():
        return {"error": f"Not a directory: {p}"}
    try:
        return [
            {
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0,
            }
            for item in sorted(p.iterdir())
        ]
    except PermissionError:
        return {"error": f"Permission denied: {p}"}


def read_file(path: str, max_size: int = _MAX_READ_SIZE) -> str | dict:
    """Read text file content (up to *max_size* bytes).

    Returns:
        File content string, or an error dict.
    """
    p = Path(path).expanduser().resolve()
    if not _check_allowed(p):
        return {"error": "Access denied — path outside allowed directories"}
    if not p.is_file():
        return {"error": f"File not found: {p}"}
    if p.stat().st_size > max_size:
        return {"error": f"File too large ({p.stat().st_size} bytes, limit {max_size})"}
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return {"error": f"Permission denied: {p}"}


def write_file(path: str, content: str) -> dict:
    """Write content to a file, creating parent directories if needed.

    Returns:
        Dict with ``ok`` and the path written.
    """
    p = Path(path).expanduser().resolve()
    if not _check_allowed(p):
        return {"error": "Access denied — path outside allowed directories"}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(p)}
    except PermissionError:
        return {"error": f"Permission denied: {p}"}


def file_info(path: str) -> dict:
    """Return metadata about a file or directory.

    Returns:
        Dict with ``name``, ``size``, ``is_dir``, ``modified`` (ISO timestamp).
    """
    p = Path(path).expanduser().resolve()
    if not _check_allowed(p):
        return {"error": "Access denied — path outside allowed directories"}
    if not p.exists():
        return {"error": f"Path does not exist: {p}"}
    try:
        stat = p.stat()
        from datetime import datetime, timezone  # noqa: PLC0415

        return {
            "name": p.name,
            "size": stat.st_size,
            "is_dir": p.is_dir(),
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    except PermissionError:
        return {"error": f"Permission denied: {p}"}


def search_files(
    directory: str = ".",
    pattern: str = "",
    content: str = "",
    max_results: int = 50,
) -> list[dict] | dict:
    """Search for files by name pattern and/or content.

    Args:
        directory: Root directory to search (recursively).
        pattern: Glob pattern for filenames (e.g. ``*.csv``, ``report*``).
        content: Text to search for inside files (case-insensitive grep).
        max_results: Maximum number of results to return.

    Returns:
        A list of matching file dicts with ``path``, ``name``, ``size``,
        and optionally ``match_line``, or an error dict.
    """
    import fnmatch  # noqa: PLC0415

    root = Path(directory).expanduser().resolve()
    if not _check_allowed(root):
        return {"error": "Access denied — path outside allowed directories"}
    if not root.is_dir():
        return {"error": f"Not a directory: {root}"}

    results: list[dict] = []
    try:
        for item in root.rglob("*"):
            if len(results) >= max_results:
                break
            if not item.is_file():
                continue
            # Name-pattern filter
            if pattern and not fnmatch.fnmatch(item.name, pattern):
                continue
            entry: dict = {
                "path": str(item),
                "name": item.name,
                "size": item.stat().st_size,
            }
            # Content filter
            if content:
                try:
                    text = item.read_text(encoding="utf-8", errors="ignore")
                    lower_content = content.lower()
                    for i, line in enumerate(text.splitlines(), 1):
                        if lower_content in line.lower():
                            entry["match_line"] = i
                            entry["match_preview"] = line.strip()[:200]
                            break
                    else:
                        continue  # no content match — skip file
                except (PermissionError, OSError):
                    continue
            results.append(entry)
    except PermissionError:
        return {"error": f"Permission denied while searching: {root}"}

    return results

        return {
            "name": p.name,
            "path": str(p),
            "size": stat.st_size,
            "is_dir": p.is_dir(),
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    except PermissionError:
        return {"error": f"Permission denied: {p}"}
