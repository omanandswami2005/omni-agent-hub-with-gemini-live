"""Local test MCP server — runs via stdio for integration testing.

Provides simple tools for testing the MCP integration with ADK:
  - echo: Echo back a message
  - get_time: Return current server time
  - calculate: Basic arithmetic

Run directly:  python -m scripts.local_mcp_server
Or via the test script which launches it as a subprocess.
"""

import json
import sys


def handle_request(request: dict) -> dict:
    """Handle a JSON-RPC request from the MCP client."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "local-test-mcp", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None  # No response needed

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo back a message — useful for testing MCP connectivity",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "description": "Message to echo"},
                            },
                            "required": ["message"],
                        },
                    },
                    {
                        "name": "get_server_time",
                        "description": "Get the current server time",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "calculate",
                        "description": "Perform basic arithmetic (add, subtract, multiply, divide)",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "operation": {
                                    "type": "string",
                                    "description": "Operation: add, subtract, multiply, divide",
                                    "enum": ["add", "subtract", "multiply", "divide"],
                                },
                                "a": {"type": "number", "description": "First operand"},
                                "b": {"type": "number", "description": "Second operand"},
                            },
                            "required": ["operation", "a", "b"],
                        },
                    },
                ],
            },
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "echo":
            msg = arguments.get("message", "")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Echo: {msg}"}],
                },
            }

        if tool_name == "get_server_time":
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Current server time: {now}"}],
                },
            }

        if tool_name == "calculate":
            op = arguments.get("operation", "")
            a = float(arguments.get("a", 0))
            b = float(arguments.get("b", 0))
            ops = {
                "add": a + b,
                "subtract": a - b,
                "multiply": a * b,
                "divide": a / b if b != 0 else "Error: division by zero",
            }
            result = ops.get(op, f"Unknown operation: {op}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"{a} {op} {b} = {result}"}],
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        }

    # Unknown method
    if req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }
    return None


def main():
    """Run the MCP server on stdio (JSON-RPC over stdin/stdout)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
