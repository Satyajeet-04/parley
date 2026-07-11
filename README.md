<div align="center">

# Parley

**Let the AI chats already open in your browser talk to each other — and to your coding agent.**

Token-efficient browser automation for ChatGPT, Gemini, Claude, Grok and more, over the Chrome DevTools Protocol. Text-only, no screenshots, no vision tokens.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-6E56CF.svg)](https://modelcontextprotocol.io)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

## Why Parley?

Most "browser AI" tools screenshot the page and feed pixels to a vision model. That is slow and burns tokens. **Parley reads the DOM text directly** through the Chrome DevTools Protocol (CDP), so it is fast, cheap, and works with the sessions you are *already logged into* — no API keys, no per-token billing for the chat models themselves.

It also does the boring-but-hard part right: it **waits for streaming responses to actually finish** before handing you the text, using a `MutationObserver` instead of naive polling. No more half-written answers.

> The name comes from the French *parler*, "to speak" — a *parley* is a conversation between two sides. That is exactly what this does: it lets two AIs (or an AI and your agent) hold a conversation.

## Features

- **Token-efficient** — text extraction only, never screenshots.
- **Universal DOM discovery** — finds the input box and latest response without brittle per-site CSS selectors, with tuned fast-paths for ChatGPT, Gemini, Claude and Grok.
- **Reliable streaming detection** — a `MutationObserver` returns the response only once it stops changing, so you never grab a partial answer.
- **AI-to-AI bridging** — relay a conversation between two tabs (e.g. ChatGPT ↔ Gemini) for N rounds.
- **Self-healing** — auto-reconnects dropped CDP sockets and recovers Gemini's "stuck send button" state via a targeted reload that preserves history.
- **Three ways to use it** — a plain CLI, an [MCP](https://modelcontextprotocol.io) server (Claude Desktop / Cursor / opencode / any MCP client), and a native opencode plugin.
- **Zero heavy deps** — one small dependency (`websocket-client`). No Playwright, no Puppeteer, no headless Chrome download.

## How it works

```
┌──────────────┐    CDP (ws://localhost:9222)   ┌──────────────────────────┐
│  Your browser │ <────────────────────────────> │  parley.py               │
│  (Brave/Chrome│                                 │  • Runtime.evaluate (DOM)│
│   logged into │                                 │  • Input.insertText      │
│   ChatGPT,    │                                 │  • MutationObserver wait │
│   Gemini, ...)│                                 └────────────┬─────────────┘
└──────────────┘                                              │
                                              ┌───────────────┼───────────────┐
                                              │               │               │
                                          CLI usage      MCP server      opencode plugin
                                                      (parley_mcp.py)    (opencode/parley.ts)
```

## Install

**Requirements:** Python 3.8+, and Brave or Chrome/Chromium.

```bash
git clone https://github.com/Satyajeet-04/parley.git
cd parley
pip install -r requirements.txt
```

### 1. Start your browser with CDP enabled

Parley talks to a browser that has remote debugging turned on. Use the helper:

```bash
./scripts/start-browser.sh
```

Or launch it yourself (re-uses your normal profile, so you stay logged in):

```bash
brave-browser --remote-debugging-port=9222 --remote-allow-origins=*
# or: google-chrome --remote-debugging-port=9222 --remote-allow-origins=*
```

Open tabs for the AIs you want to use (ChatGPT, Gemini, ...) and sign in.

### 2. Try it

```bash
python3 parley.py list
```

You should see your open tabs with their IDs.

## Usage (CLI)

```bash
# List tabs and grab the ID you want
python3 parley.py list

# Send a message and wait for the full reply (recommended)
python3 parley.py send-wait <TAB_ID> "Explain CDP in one sentence."

# Read the latest response from a tab
python3 parley.py read <TAB_ID>

# Make two AIs talk to each other for 3 rounds
python3 parley.py bridge <CHATGPT_TAB_ID> <GEMINI_TAB_ID> 3
```

| Command | Description |
| --- | --- |
| `list` | List all browser tabs with IDs, titles, URLs |
| `read <tab>` | Read the latest AI response (auto-detected) |
| `send <tab> <text>` | Type and submit a message |
| `send-wait <tab> <text> [--timeout ms]` | Send **and wait** for the full response |
| `wait-stream <tab> [timeout_ms]` | Wait for an in-progress response to finish |
| `type <tab> <text>` | Type without submitting |
| `click <tab> <selector>` | Click an element by CSS selector |
| `navigate <tab> <url>` | Navigate a tab to a URL |
| `eval <tab> <js>` | Run JavaScript and return the result |
| `bridge <from> <to> [rounds]` | Relay a conversation between two tabs |

**Configuration** (environment variables):

| Variable | Default | Purpose |
| --- | --- | --- |
| `PARLEY_CDP_HOST` | `localhost` | CDP host |
| `PARLEY_CDP_PORT` | `9222` | CDP port |

## Usage (MCP server)

Parley ships an MCP server so any MCP client can drive your browser. Add it to your client config:

```json
{
  "mcpServers": {
    "parley": {
      "command": "python3",
      "args": ["/absolute/path/to/parley/parley_mcp.py"]
    }
  }
}
```

- **Claude Desktop:** `claude_desktop_config.json`
- **Cursor:** `.cursor/mcp.json`
- **opencode:** add under `mcp` in `opencode.json` (or use the native plugin below)

Tools exposed: `list_tabs`, `read`, `send`, `send_wait`, `wait_stream`, `type`, `click`, `navigate`, `eval`, `bridge`.

## Usage (opencode plugin)

For a native opencode integration (no MCP needed):

```bash
cp parley.py ~/.opencode/scripts/parley.py
cp opencode/parley.ts ~/.opencode/plugins/parley.ts
```

Restart opencode. You get the tools `browser_list_tabs`, `browser_read`, `browser_send`, `browser_send_wait`, `browser_bridge`, and more. Point it at a different script location with the `PARLEY_SCRIPT` env var if needed.

## Example: make ChatGPT and Gemini debate

```bash
# 1. In your browser open a ChatGPT tab and a Gemini tab, sign into both.
python3 parley.py list
#   -> note the two tab IDs

# 2. Seed one side
python3 parley.py send-wait <CHATGPT_ID> "Argue that tabs are better than spaces. One paragraph."

# 3. Relay the debate for 4 rounds
python3 parley.py bridge <CHATGPT_ID> <GEMINI_ID> 4
```

## Troubleshooting

- **`list` returns an error / empty** — the browser is not running with `--remote-debugging-port=9222`, or a different app is on that port. Restart via `scripts/start-browser.sh`.
- **403 on connect** — make sure you launched with `--remote-allow-origins=*`.
- **Response looks empty or truncated** — the model may still be generating; prefer `send-wait` / `wait-stream`, which wait for completion.
- **Gemini stops responding after a while** — Parley auto-recovers by reloading the tab (history is preserved). If it persists, reload the Gemini tab manually.
- **Only the first message works on a service** — you are likely using it logged-out/anonymous (rate-limited). Sign in for full use.

## Roadmap

- [ ] Firefox (via the Remote Protocol) support
- [ ] Structured extraction of code blocks and tables
- [ ] Multi-tab fan-out (ask N models the same prompt in parallel)
- [ ] Optional websocket-free HTTP fallback

## Contributing

Contributions are very welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Adding support for a new AI site is usually just a few selectors.

## Disclaimer

Parley automates *your own* logged-in browser sessions locally. Respect the Terms of Service of each site you automate. This project is not affiliated with OpenAI, Google, Anthropic, or xAI.

## License

[MIT](LICENSE) © 2026 Satyajeet

---

<div align="center">
If Parley saved you some tokens, consider leaving a ⭐ — it helps others find it.
</div>
