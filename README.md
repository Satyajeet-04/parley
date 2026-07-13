<div align="center">

# Parley

**A lightweight CDP browser-automation framework with first-class AI workflow support.**

Drive any website you're already logged into — read the DOM, fill forms, click, extract data, run JS — over the Chrome DevTools Protocol. Text-only, no screenshots, no vision tokens. Built-in workflows let the AI chats already open in your browser talk to each other and to your coding agent.

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

Under the hood the core CDP engine is fully general-purpose — AI chat automation is just one workflow built on top of it. You can point the same primitives at news sites, dashboards, documentation, or internal web apps.

### Demo: AI-to-AI Bridge

```
$ python3 parley.py send-wait <gemini_tab> "What is the capital of France?" 60000
{
  "send_method": "gemini",
  "response_text": "The capital of France is Paris.",
  "response_complete": true,
  "duration_ms": 5312
}

$ python3 parley.py bridge <chatgpt_tab> <gemini_tab> 1
{
  "round": 1,
  "source_text": "The capital of France is Paris.",
  "target_text": "That's correct! Paris is the capital of France...",
  "target_complete": true,
  "duration_ms": 8241
}

$ python3 parley.py cookies <gemini_tab> gemini.google.com
{
  "count": 3,
  "cookies": [
    {"name": "COMPASS", "value": "...", "httpOnly": true, "secure": true},
    {"name": "NID",     "value": "...", "httpOnly": true, "secure": true}
  ]
}
```

## Features

- **General-purpose CDP engine** — `read-dom`, `extract`, `click`, `type`, `navigate`, `wait-for`, `eval`, and cookie access work on **any** website.
- **Token-efficient** — text extraction only, never screenshots.
- **Universal DOM discovery** — finds the input box and latest response without brittle per-site CSS selectors, with tuned fast-paths for ChatGPT, Gemini, Claude and Grok.
- **Reliable streaming detection** — a `MutationObserver` returns the response only once it stops changing, so you never grab a partial answer.
- **AI-to-AI bridging** — relay a conversation between two tabs (e.g. ChatGPT ↔ Gemini) for N rounds.
- **Self-healing** — auto-reconnects dropped CDP sockets and recovers Gemini's "stuck send button" state via a targeted reload that preserves history.
- **Three ways to use it** — a plain CLI, an [MCP](https://modelcontextprotocol.io) server (Claude Desktop / Cursor / opencode / any MCP client), and a native opencode plugin.
- **Zero heavy deps** — one small dependency (`websocket-client`). No Playwright, no Puppeteer, no headless Chrome download.

### Generic Automation (any website)

```bash
# Extract all headings from a page
python3 parley.py extract <tab_id> h2

# Read a specific DOM element
python3 parley.py read-dom <tab_id> ".main-content"

# Run any JS and get the result
python3 parley.py eval <tab_id> "document.querySelectorAll('a[href]').length"

# Extract session cookies for authenticated API calls
python3 parley.py cookies <tab_id> api.example.com

# Click a button
python3 parley.py click <tab_id> "button[data-testid='submit']"

# Wait for an element to appear (up to 10s)
python3 parley.py wait-for <tab_id> ".result-loaded"
```

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

## Architecture

Parley is organized in three layers so the generic engine stays independent of any site-specific knowledge:

```
parley/
├── core.py            Core CDP engine — connection, DOM, JS eval, input,
│                      navigation, wait_for, cookies. Knows nothing about AI sites.
├── adapters/          Per-site knowledge (selectors, quirks)
│   ├── base.py          SiteAdapter base class + URL matching
│   ├── chatgpt.py       Gemini / Claude / Grok / Generic adapters
│   ├── gemini.py        …
│   ├── generic.py       fallback for any website
│   └── js.py            injected JS (universal DOM discovery, MutationObserver)
└── workflows.py       AI workflows on top: send, send_and_wait, wait_stream,
                       poll, bridge, robust_send (Gemini stuck-state recovery)
```

`parley.py` (root), `parley_mcp.py`, and `opencode/parley.ts` are all thin layers over these three modules.

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
| `read-dom <tab> [selector]` | Read page/element text — works on **any** site |
| `extract <tab> <selector> [attr]` | Extract text/attribute from all matches (scraping) |
| `wait-for <tab> <selector> [timeout_ms]` | Wait for an element to appear |
| `cookies <tab> [domain]` | List cookies (incl. HttpOnly) via CDP |
| `set-cookie <tab> <name> <value> <domain> [path]` | Set a cookie |

### Generic automation example

```bash
# Scrape all links off a page
python3 parley.py extract <TAB_ID> "a" href

# Read an article's body text
python3 parley.py read-dom <TAB_ID> "article"

# Reuse a logged-in session elsewhere (handle cookies as secrets!)
python3 parley.py cookies <TAB_ID> github.com
```

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

Tools exposed: `list_tabs`, `read`, `send`, `send_wait`, `wait_stream`, `type`, `click`, `navigate`, `eval`, `bridge`, `read_dom`, `extract`, `wait_for`, `cookies`.

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

## Responsible use

Parley is a general-purpose automation tool. With great DOM access comes real responsibility:

- **Respect Terms of Service & robots policies.** Automating a site — especially private APIs or bulk scraping — may violate its terms even when it's your own logged-in session.
- **Rate-limit yourself.** Don't hammer sites; add delays and cap request volume.
- **Cookies are credentials.** `cookies` can read HttpOnly session tokens. Anyone with them can impersonate your login. Never log, print into shared transcripts, or commit them. Store only in memory or a permission-locked, git-ignored file.
- **Mind privacy & data laws.** Only collect data you're allowed to, and handle personal data lawfully.

You are responsible for how you use it.

## Disclaimer

Parley automates *your own* logged-in browser sessions locally. This project is not affiliated with OpenAI, Google, Anthropic, or xAI.

## License

[MIT](LICENSE) © 2026 Satyajeet

---

<div align="center">
If Parley saved you some tokens, consider leaving a ⭐ — it helps others find it.
</div>
