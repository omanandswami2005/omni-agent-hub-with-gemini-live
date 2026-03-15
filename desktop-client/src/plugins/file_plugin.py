"""File plugin — sandboxed read / write / list / info / search / upload-to-E2B."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from src.files import file_info, list_directory, read_file, search_files, write_file
from src.plugin_registry import DesktopPlugin

logger = logging.getLogger(__name__)

# Populated at load time from config.server_url (ws→http)
_api_base_url: str = "http://localhost:8000"
_auth_token: str = ""


def _set_api_context(cfg) -> None:
    """Extract HTTP base URL and auth token from desktop config."""
    global _api_base_url, _auth_token  # noqa: PLW0603
    if cfg is None:
        return
    ws_url = getattr(cfg, "server_url", "") or ""
    # Convert ws(s)://host:port/ws/live → http(s)://host:port
    base = ws_url.replace("ws://", "http://").replace("wss://", "https://")
    base = base.split("/ws/")[0] if "/ws/" in base else base
    _api_base_url = base.rstrip("/")
    _auth_token = getattr(cfg, "auth_token", "") or ""


async def _handle_read_file(**kwargs) -> dict:
    return read_file(kwargs["path"])


async def _handle_write_file(**kwargs) -> dict:
    return write_file(kwargs["path"], kwargs["content"])


async def _handle_list_directory(**kwargs) -> dict:
    return list_directory(kwargs["path"])


async def _handle_file_info(**kwargs) -> dict:
    return file_info(kwargs["path"])


async def _handle_search_files(**kwargs) -> dict:
    return search_files(
        directory=kwargs.get("directory", "~"),
        pattern=kwargs.get("pattern", ""),
        content=kwargs.get("content", ""),
        max_results=kwargs.get("max_results", 50),
    )


async def _handle_upload_to_e2b(**kwargs) -> dict:
    """Read a local file and upload it to the E2B desktop sandbox via the backend API."""
    local_path = kwargs.get("path", "")
    dest_path = kwargs.get("destination", "")
    if not local_path:
        return {"error": "path is required"}

    p = Path(local_path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"File not found: {p}"}
    if p.stat().st_size > 50_000_000:  # 50 MB limit
        return {"error": f"File too large: {p.stat().st_size} bytes (limit 50MB)"}

    if not dest_path:
        dest_path = f"/home/user/{p.name}"

    try:
        content = p.read_bytes()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{_api_base_url}/tasks/desktop/upload",
                headers={"Authorization": f"Bearer {_auth_token}"},
                files={"file": (p.name, content)},
                data={"path": dest_path},
            )
            if resp.status_code != 200:
                return {"error": f"Upload failed ({resp.status_code}): {resp.text}"}
            result = resp.json()
            result["local_path"] = str(p)
            result["e2b_path"] = dest_path
            return result
    except Exception as e:
        logger.error("Upload to E2B failed: %s", e)
        return {"error": str(e)}


def register() -> DesktopPlugin:
    return DesktopPlugin(
        name="file",
        capabilities=["file_system", "file_search", "e2b_upload"],
        handlers={
            "read_file": _handle_read_file,
            "write_file": _handle_write_file,
            "list_directory": _handle_list_directory,
            "file_info": _handle_file_info,
            "search_files": _handle_search_files,
            "upload_to_e2b": _handle_upload_to_e2b,
        },
        tool_defs=[
            {
                "name": "read_file",
                "description": "Read the contents of a text file on the user's machine",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the file"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write content to a file on the user's machine",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the file"},
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "list_directory",
                "description": "List files and folders in a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the directory"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "file_info",
                "description": "Get metadata about a file (size, modified date, etc.)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the file"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "search_files",
                "description": "Search for files on the user's machine by name pattern and/or content. Supports recursive search with glob patterns (e.g. '*.csv', 'report*') and grep-like content matching.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "Root directory to search (default: home)", "default": "~"},
                        "pattern": {"type": "string", "description": "Glob pattern for filenames (e.g. '*.csv', '*.py')"},
                        "content": {"type": "string", "description": "Text to search for inside files (case-insensitive)"},
                        "max_results": {"type": "integer", "description": "Maximum results to return", "default": 50},
                    },
                },
            },
            {
                "name": "upload_to_e2b",
                "description": "Upload a file from the user's local machine to the E2B cloud desktop sandbox. Returns the E2B file path. Use this to transfer local files (CSV, images, scripts, etc.) so agents can process them in the cloud sandbox.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the local file to upload"},
                        "destination": {"type": "string", "description": "Destination path in the E2B sandbox (default: /home/user/<filename>)"},
                    },
                    "required": ["path"],
                },
            },
        ],
        on_load=_set_api_context,
    )
