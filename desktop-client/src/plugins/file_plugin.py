"""File plugin — sandboxed read / write / list / info operations."""

from __future__ import annotations

from src.files import file_info, list_directory, read_file, write_file
from src.plugin_registry import DesktopPlugin


async def _handle_read_file(**kwargs) -> dict:
    return read_file(kwargs["path"])


async def _handle_write_file(**kwargs) -> dict:
    return write_file(kwargs["path"], kwargs["content"])


async def _handle_list_directory(**kwargs) -> dict:
    return list_directory(kwargs["path"])


async def _handle_file_info(**kwargs) -> dict:
    return file_info(kwargs["path"])


def register() -> DesktopPlugin:
    return DesktopPlugin(
        name="file",
        capabilities=["file_system"],
        handlers={
            "read_file": _handle_read_file,
            "write_file": _handle_write_file,
            "list_directory": _handle_list_directory,
            "file_info": _handle_file_info,
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
        ],
    )
