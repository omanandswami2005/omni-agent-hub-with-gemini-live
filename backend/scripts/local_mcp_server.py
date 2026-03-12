"""Local test MCP server — proper MCP protocol via FastMCP.

Provides tools for testing MCP integration with ADK's McpToolset:
  - echo: Echo back a message
  - get_server_time: Return current UTC time
  - calculate: Basic arithmetic

Run via stdio:
    python scripts/local_mcp_server.py
"""

from datetime import datetime, timezone

from mcp.server import FastMCP

mcp = FastMCP("local-test-mcp")


@mcp.tool()
def echo(message: str) -> str:
    """Echo back a message — useful for testing MCP connectivity."""
    return f"Echo: {message}"


@mcp.tool()
def get_server_time() -> str:
    """Get the current server time in UTC."""
    return f"Current server time: {datetime.now(timezone.utc).isoformat()}"


@mcp.tool()
def calculate(operation: str, a: float, b: float) -> str:
    """Perform basic arithmetic (add, subtract, multiply, divide).

    Args:
        operation: One of add, subtract, multiply, divide
        a: First operand
        b: Second operand
    """
    ops = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b != 0 else "Error: division by zero",
    }
    result = ops.get(operation, f"Unknown operation: {operation}")
    return f"{a} {operation} {b} = {result}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
