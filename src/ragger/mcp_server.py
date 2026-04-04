"""MCP server exposing Ragger tools to Claude."""

import json
import os

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ragger")

BRIDGE_URL = f"http://127.0.0.1:{os.environ.get('RAGGER_BRIDGE_PORT', '7919')}"
BRIDGE_TOKEN = os.environ.get("RAGGER_BRIDGE_TOKEN", "")
BRIDGE_HEADERS = {"Authorization": f"Bearer {BRIDGE_TOKEN}"}


@mcp.tool(name="RaggerRun")
def ragger_run(name: str, script: str) -> str:
    """Execute a persistent Lua actor in the RuneLite client.

    Args:
        name: Short descriptive name in kebab-case (e.g. "tick-counter", "npc-highlighter")
        script: Lua source code to execute
    """
    try:
        resp = requests.post(
            f"{BRIDGE_URL}/run",
            json={"name": name, "script": script},
            headers=BRIDGE_HEADERS,
            timeout=10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="RaggerEval")
def ragger_eval(script: str) -> str:
    """Evaluate a Lua expression in the RuneLite client and return the result.

    Runs on the game client thread with access to all APIs (scene, player,
    client, items, coords, etc.). Returns the result as JSON.

    Args:
        script: Lua expression to evaluate (e.g. "scene:npcs()", "player:hp()")
    """
    try:
        resp = requests.post(
            f"{BRIDGE_URL}/eval",
            json={"script": script},
            headers=BRIDGE_HEADERS,
            timeout=10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="RaggerActorList")
def ragger_actor_list() -> str:
    """List all currently running Lua actors by name."""
    try:
        resp = requests.get(
            f"{BRIDGE_URL}/list",
            headers=BRIDGE_HEADERS,
            timeout=10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="RaggerActorSource")
def ragger_actor_source(name: str) -> str:
    """Retrieve the Lua source code of a running actor by name.

    Args:
        name: The actor name (e.g. "tick-counter", "npc-highlighter")
    """
    try:
        resp = requests.post(
            f"{BRIDGE_URL}/source",
            json={"name": name},
            headers=BRIDGE_HEADERS,
            timeout=10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="RaggerTemplateList")
def ragger_template_list() -> str:
    """List all registered Lua actor templates by name."""
    try:
        resp = requests.get(
            f"{BRIDGE_URL}/templates",
            headers=BRIDGE_HEADERS,
            timeout=10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="RaggerTemplateSource")
def ragger_template_source(name: str) -> str:
    """Retrieve the Lua source code of a registered template by name.

    Args:
        name: The template name (e.g. "tile-marker", "counter-display")
    """
    try:
        resp = requests.post(
            f"{BRIDGE_URL}/template-source",
            json={"name": name},
            headers=BRIDGE_HEADERS,
            timeout=10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="RaggerMailRecvAsync")
def ragger_recv_async(limit: int = 0, from_actor: str = "") -> str:
    """Pop messages from the claude mailbox without blocking.

    Returns immediately with up to `limit` messages (0 = all available).
    Optionally filter by sender actor name.

    Args:
        limit: Max messages to return. 0 returns all available.
        from_actor: Regex pattern to match sender actor names (e.g. "loot-.*", "quest-guide/.*"). Empty string = any actor.
    """
    try:
        params = {}
        if limit > 0:
            params["limit"] = limit
        if from_actor:
            params["from"] = from_actor
        resp = requests.get(
            f"{BRIDGE_URL}/mail-recv",
            params=params,
            headers=BRIDGE_HEADERS,
            timeout=10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="RaggerMailRecvSync")
def ragger_recv_sync(count: int = 1, from_actor: str = "", timeout: int = 30) -> str:
    """Block until exactly `count` messages arrive, then return them.

    Waits for the specified number of messages to accumulate in the claude
    mailbox before returning. Returns early with whatever was collected if
    the timeout is reached.

    Args:
        count: Exact number of messages to wait for (minimum 1).
        from_actor: Regex pattern to match sender actor names (e.g. "loot-.*", "quest-guide/.*"). Empty string = any actor.
        timeout: Max seconds to wait (1-300, default 30).
    """
    try:
        params = {"count": max(1, count), "timeout": min(300, max(1, timeout))}
        if from_actor:
            params["from"] = from_actor
        resp = requests.get(
            f"{BRIDGE_URL}/mail-recv-block",
            params=params,
            headers=BRIDGE_HEADERS,
            timeout=timeout + 10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="RaggerMailSend")
def ragger_mail(target: str, data: dict) -> str:
    """Send a message to a running Lua actor's on_mail hook.

    The actor receives on_mail(from, data) where from is "claude"
    and data is the table you provide here.

    Args:
        target: The actor name to send to (e.g. "tile-marker", "npc-highlighter")
        data: Key-value table to deliver (string/number/boolean values)
    """
    try:
        resp = requests.post(
            f"{BRIDGE_URL}/mail",
            json={"target": target, "data": data},
            headers=BRIDGE_HEADERS,
            timeout=10,
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


if __name__ == "__main__":
    mcp.run()
