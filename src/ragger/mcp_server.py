"""MCP server exposing Ragger tools to Claude."""

import json
import re
import secrets

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ragger")


def _kebab(name: str) -> str:
    """Convert a name to kebab-case."""
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip())
    name = re.sub(r"-+", "-", name).strip("-").lower()
    return name


@mcp.tool(name="RaggerRun")
def ragger_run(name: str, script: str) -> str:
    """Execute a Lua script in the RuneLite client.

    Args:
        name: Short descriptive name for the script (e.g. "tick-counter", "camera-spin")
        script: Lua source code to execute
    """
    uid = _kebab(name) + "-" + secrets.token_hex(2)
    return json.dumps({"type": "script", "name": uid, "source": script})


if __name__ == "__main__":
    mcp.run()
