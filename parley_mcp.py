#!/usr/bin/env python3
"""
Parley MCP Server - expose the Parley browser bridge over the Model Context
Protocol (MCP) so it works with Claude Desktop, Cursor, opencode, and any other
MCP-compatible client.

Transport: stdio (newline-delimited JSON-RPC 2.0). Zero third-party deps beyond
what parley.py already needs (websocket-client).

Register it (Claude Desktop / Cursor style):

    {
      "mcpServers": {
        "parley": {
          "command": "python3",
          "args": ["/absolute/path/to/parley_mcp.py"]
        }
      }
    }
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARLEY = os.path.join(HERE, "parley.py")

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "parley", "version": "1.0.0"}

# Tool name -> (parley subcommand, [ordered arg names], {defaults}, timeout_s)
TOOLS = [
    {
        "name": "list_tabs",
        "description": (
            "List all open browser tabs (Brave/Chrome via CDP). Returns tab IDs, "
            "titles, and URLs. Use this first to find the tab for ChatGPT, Gemini, "
            "Claude, or any web app."
        ),
        "cmd": "list",
        "args": [],
        "schema": {"type": "object", "properties": {}, "required": []},
        "timeout": 15,
    },
    {
        "name": "read",
        "description": (
            "Read the latest AI chat response from a tab (auto-detects ChatGPT, "
            "Gemini, Claude). Text only - no screenshots, so it is token-cheap."
        ),
        "cmd": "read",
        "args": ["tab_id"],
        "schema": {
            "type": "object",
            "properties": {"tab_id": {"type": "string", "description": "Tab ID from list_tabs"}},
            "required": ["tab_id"],
        },
        "timeout": 20,
    },
    {
        "name": "send",
        "description": "Type text into a tab's chat box and submit it (does not wait for the reply).",
        "cmd": "send",
        "args": ["tab_id", "text"],
        "schema": {
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "Tab ID from list_tabs"},
                "text": {"type": "string", "description": "Message to send"},
            },
            "required": ["tab_id", "text"],
        },
        "timeout": 30,
    },
    {
        "name": "send_wait",
        "description": (
            "Send a message AND wait for the AI to finish streaming its full "
            "response, then return the text. This is the recommended way to talk "
            "to an AI - it will not return early with a half-written answer."
        ),
        "cmd": "send-wait",
        "args": ["tab_id", "text"],
        "schema": {
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "Tab ID from list_tabs"},
                "text": {"type": "string", "description": "Message to send"},
            },
            "required": ["tab_id", "text"],
        },
        "timeout": 120,
    },
    {
        "name": "wait_stream",
        "description": "Wait for an in-progress AI response in a tab to finish streaming, then return it.",
        "cmd": "wait-stream",
        "args": ["tab_id"],
        "schema": {
            "type": "object",
            "properties": {"tab_id": {"type": "string", "description": "Tab ID from list_tabs"}},
            "required": ["tab_id"],
        },
        "timeout": 120,
    },
    {
        "name": "type",
        "description": "Type text into a tab's input without submitting (for composing / forms).",
        "cmd": "type",
        "args": ["tab_id", "text"],
        "schema": {
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "Tab ID from list_tabs"},
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["tab_id", "text"],
        },
        "timeout": 30,
    },
    {
        "name": "click",
        "description": "Click an element in a tab by CSS selector.",
        "cmd": "click",
        "args": ["tab_id", "selector"],
        "schema": {
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "Tab ID from list_tabs"},
                "selector": {"type": "string", "description": "CSS selector to click"},
            },
            "required": ["tab_id", "selector"],
        },
        "timeout": 15,
    },
    {
        "name": "navigate",
        "description": "Navigate a tab to a URL.",
        "cmd": "navigate",
        "args": ["tab_id", "url"],
        "schema": {
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "Tab ID from list_tabs"},
                "url": {"type": "string", "description": "URL to open"},
            },
            "required": ["tab_id", "url"],
        },
        "timeout": 30,
    },
    {
        "name": "eval",
        "description": "Evaluate JavaScript in a tab and return the result (for custom DOM queries).",
        "cmd": "eval",
        "args": ["tab_id", "code"],
        "schema": {
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "Tab ID from list_tabs"},
                "code": {"type": "string", "description": "JavaScript to evaluate (must return a value)"},
            },
            "required": ["tab_id", "code"],
        },
        "timeout": 20,
    },
    {
        "name": "bridge",
        "description": (
            "Relay a conversation between two tabs: read the latest response from "
            "tab_from and send it to tab_to, for N rounds. Makes two AIs talk to "
            "each other (e.g. ChatGPT <-> Gemini)."
        ),
        "cmd": "bridge",
        "args": ["tab_from", "tab_to", "rounds"],
        "schema": {
            "type": "object",
            "properties": {
                "tab_from": {"type": "string", "description": "Source tab ID (read from here)"},
                "tab_to": {"type": "string", "description": "Target tab ID (send to here)"},
                "rounds": {"type": "integer", "description": "Number of rounds (default 3)"},
            },
            "required": ["tab_from", "tab_to"],
        },
        "timeout": 300,
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def run_parley(tool, arguments):
    cmd = [sys.executable, PARLEY, tool["cmd"]]
    for arg in tool["args"]:
        if arg in arguments and arguments[arg] is not None:
            cmd.append(str(arguments[arg]))
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=tool["timeout"],
        )
        text = out.stdout.strip() or out.stderr.strip() or "(no output)"
        is_error = out.returncode != 0
        return text, is_error
    except subprocess.TimeoutExpired:
        return f"Timed out after {tool['timeout']}s", True
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}", True


def make_result(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def make_error(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle(msg):
    method = msg.get("method")
    id_ = msg.get("id")

    if method == "initialize":
        return make_result(id_, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method == "notifications/initialized":
        return None  # notification, no reply

    if method == "ping":
        return make_result(id_, {})

    if method == "tools/list":
        return make_result(id_, {
            "tools": [
                {"name": t["name"], "description": t["description"], "inputSchema": t["schema"]}
                for t in TOOLS
            ]
        })

    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        tool = TOOLS_BY_NAME.get(name)
        if not tool:
            return make_error(id_, -32602, f"Unknown tool: {name}")
        text, is_error = run_parley(tool, arguments)
        return make_result(id_, {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        })

    if id_ is not None:
        return make_error(id_, -32601, f"Method not found: {method}")
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
