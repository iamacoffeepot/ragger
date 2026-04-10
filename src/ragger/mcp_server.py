"""MCP server exposing Ragger tools to Claude."""

from __future__ import annotations

import json
import os

import requests
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

import ragger.item  # noqa: F401
from ragger.mcp_registry import register_all

mcp = FastMCP("ragger")

DB_PATH = os.environ.get("RAGGER_DB", "data/ragger.db")
register_all(mcp, DB_PATH)

BRIDGE_URL = f"http://127.0.0.1:{os.environ.get('RAGGER_BRIDGE_PORT', '7919')}"
BRIDGE_TOKEN = os.environ.get("RAGGER_BRIDGE_TOKEN", "")
BRIDGE_HEADERS: dict[str, str] = {"Authorization": f"Bearer {BRIDGE_TOKEN}"}


def _bridge_post(path: str, body: dict | list) -> str:
    try:
        resp = requests.post(
            f"{BRIDGE_URL}{path}", json=body, headers=BRIDGE_HEADERS, timeout=10
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


def _bridge_get(path: str, params: dict | None = None, timeout: int = 10) -> str:
    try:
        resp = requests.get(
            f"{BRIDGE_URL}{path}", params=params, headers=BRIDGE_HEADERS, timeout=timeout
        )
        return resp.text
    except requests.ConnectionError:
        return json.dumps({"error": "Bridge server not running"})


@mcp.tool(name="ActorSpawn")
def ragger_actor_spawn(name: str, script: str) -> str:
    """Spawn a Lua actor in the RuneLite client.

    Args:
        name: Short descriptive name in kebab-case (e.g. "tick-counter", "npc-highlighter")
        script: Lua source code to execute
    """
    return _bridge_post("/run", {"name": name, "script": script})


@mcp.tool(name="Eval")
def ragger_eval(script: str) -> str:
    """Evaluate a Lua expression in the RuneLite client and return the result.

    Runs on the game client thread with access to all APIs (scene, player,
    client, items, coords, etc.). Returns the result as JSON.

    Args:
        script: Lua expression to evaluate (e.g. "scene:npcs()", "player:hp()")
    """
    return _bridge_post("/eval", {"script": script})


@mcp.tool(name="ActorList")
def ragger_actor_list() -> str:
    """List all currently running Lua actors by name."""
    return _bridge_get("/list")


@mcp.tool(name="ActorSource")
def ragger_actor_source(name: str) -> str:
    """Retrieve the Lua source code of a running actor by name.

    Args:
        name: The actor name (e.g. "tick-counter", "npc-highlighter")
    """
    return _bridge_post("/source", {"name": name})


@mcp.tool(name="TemplateList")
def ragger_template_list() -> str:
    """List all registered Lua actor templates by name."""
    return _bridge_get("/templates")


@mcp.tool(name="TemplateSource")
def ragger_template_source(name: str) -> str:
    """Retrieve the Lua source code of a registered template by name.

    Args:
        name: The template name (e.g. "tile-marker", "counter-display")
    """
    return _bridge_post("/template-source", {"name": name})


@mcp.tool(name="MailRecvAsync")
def ragger_mail_recv_async(limit: int = 0, from_actor: str = "") -> str:
    """Pop messages from the claude mailbox without blocking.

    Returns immediately with up to `limit` messages (0 = all available).
    Optionally filter by sender actor name.

    Args:
        limit: Max messages to return. 0 returns all available.
        from_actor: Regex pattern to match sender actor names (e.g. "loot-.*", "quest-guide/.*"). Empty string = any actor.
    """
    params: dict[str, int | str] = {}
    if limit > 0:
        params["limit"] = limit
    if from_actor:
        params["from"] = from_actor
    return _bridge_get("/mail-recv", params)


@mcp.tool(name="MailRecvSync")
def ragger_mail_recv_sync(count: int = 1, from_actor: str = "", timeout: int = 30) -> str:
    """Block until exactly `count` messages arrive, then return them.

    Waits for the specified number of messages to accumulate in the claude
    mailbox before returning. Returns early with whatever was collected if
    the timeout is reached.

    Args:
        count: Exact number of messages to wait for (minimum 1).
        from_actor: Regex pattern to match sender actor names (e.g. "loot-.*", "quest-guide/.*"). Empty string = any actor.
        timeout: Max seconds to wait (1-300, default 30).
    """
    params: dict[str, int | str] = {"count": max(1, count), "timeout": min(300, max(1, timeout))}
    if from_actor:
        params["from"] = from_actor
    return _bridge_get("/mail-recv-block", params, timeout=timeout + 10)


class BatchMailMessage(BaseModel):
    target: str
    data: dict


@mcp.tool(name="MailSend")
def ragger_mail_send(name: str, messages: list[dict]) -> str:
    """Send one or more messages to a single actor's on_mail hook.

    All messages are delivered to the same actor in order.

    Args:
        name: Target actor name (e.g. "tile-marker", "npc-highlighter")
        messages: List of data dicts to deliver
    """
    return _bridge_post("/mail", [{"target": name, "data": m} for m in messages])


@mcp.tool(name="MailSendBatch")
def ragger_mail_send_batch(messages: list[BatchMailMessage]) -> str:
    """Send messages to multiple actors in one call.

    Each message specifies its own target actor. Messages are delivered in order.

    Args:
        messages: List of {target: str, data: dict} messages to deliver
    """
    return _bridge_post("/mail", [m.model_dump() for m in messages])


if __name__ == "__main__":
    mcp.run()
