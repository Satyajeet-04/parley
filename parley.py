#!/usr/bin/env python3
"""
Parley - Token-Efficient AI Chat Automation via Chrome DevTools Protocol

Let the AI chats already open in your browser (ChatGPT, Gemini, Claude, Grok...)
talk to each other and to your coding agent - using text-only extraction,
so it stays fast and cheap (no screenshots, no vision tokens).

Uses Universal DOM Discovery (no hard-coded CSS selectors) plus a
MutationObserver to reliably detect when streaming responses finish.

Usage:
  parley.py list                              # List all browser tabs
  parley.py read <tab_id>                     # Read latest AI response (universal)
  parley.py send <tab_id> <text>              # Type + submit (via CDP Input)
  parley.py send-wait <tab_id> <text> [ms]    # Send + wait for full response (recommended)
  parley.py type <tab_id> <text>              # Type without submitting
  parley.py click <tab_id> <selector>         # Click element by CSS selector
  parley.py navigate <tab_id> <url>           # Navigate a tab to a URL
  parley.py eval <tab_id> <js>                # Evaluate JavaScript in the tab
  parley.py wait-stream <tab_id> [timeout_ms] # Wait for streaming to finish (MutationObserver)
  parley.py poll <tab_id> [interval_ms]       # Poll for new content
  parley.py bridge <tab_from> <tab_to> [rounds] # Relay a conversation between two AIs

Project: https://github.com/Satyajeet-04/parley
License: MIT
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import websocket

CDP_HOST = os.environ.get("PARLEY_CDP_HOST", "localhost")
CDP_PORT = int(os.environ.get("PARLEY_CDP_PORT", "9222"))
CDP_HTTP = f"http://{CDP_HOST}:{CDP_PORT}"

# Maximum reconnect attempts for WebSocket connections
MAX_RECONNECT = 3
RECONNECT_DELAY = 1


def http_get(path):
    try:
        with urllib.request.urlopen(f"{CDP_HTTP}{path}", timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def get_ws_url(tab_id):
    tabs = http_get("/json/list")
    if isinstance(tabs, dict) and "error" in tabs:
        return None
    for tab in tabs:
        if tab.get("id") == tab_id:
            return tab.get("webSocketDebuggerUrl")
    return None


def cdp_connect(tab_id, retries=MAX_RECONNECT):
    """Connect to a tab via WebSocket with automatic reconnection."""
    ws_url = get_ws_url(tab_id)
    if not ws_url:
        return None
    for attempt in range(retries):
        try:
            ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
            return ws
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(RECONNECT_DELAY)
                # Refresh WebSocket URL (may have changed)
                ws_url = get_ws_url(tab_id)
                if not ws_url:
                    return None
            else:
                return None
    return None


def cdp_send(ws, method, params=None, timeout=10):
    """Send CDP command and wait for response with timeout."""
    msg_id = int(time.time() * 1000) % 100000
    msg = {"id": msg_id, "method": method}
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))
    ws.settimeout(timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = json.loads(ws.recv())
            if resp.get("id") == msg_id:
                return resp.get("result", resp.get("error", {}))
        except websocket.WebSocketTimeoutException:
            break
        except Exception:
            break
    return {"error": "timeout"}


def cdp_send_with_retry(ws, method, params=None, timeout=10, tab_id=None, retries=MAX_RECONNECT):
    """Send CDP command with automatic reconnection on failure."""
    for attempt in range(retries):
        try:
            result = cdp_send(ws, method, params, timeout)
            if "error" not in result:
                return result
            # If error and we have retries left, reconnect
            if attempt < retries - 1 and tab_id:
                ws.close()
                ws = cdp_connect(tab_id)
                if not ws:
                    return {"error": "reconnect failed"}
        except Exception as e:
            if attempt < retries - 1 and tab_id:
                try:
                    ws.close()
                except:
                    pass
                ws = cdp_connect(tab_id)
                if not ws:
                    return {"error": "reconnect failed"}
            else:
                return {"error": str(e)}
    return {"error": "max retries exceeded"}


# ============================================================================
# UNIVERSAL DOM DISCOVERY (No CSS Selectors - Agora Approach)
# ============================================================================

# JavaScript for Universal DOM Discovery - works across ChatGPT, Gemini, Claude, Grok
UNIVERSAL_FIND_INPUT = """
(() => {
    // Find all contenteditable elements
    const editables = document.querySelectorAll('[contenteditable="true"]');
    if (editables.length === 0) {
        // Fallback: try textareas
        const textareas = document.querySelectorAll('textarea');
        if (textareas.length > 0) {
            // Pick the largest textarea
            let best = textareas[0];
            let bestArea = best.clientWidth * best.clientHeight;
            for (const ta of textareas) {
                const area = ta.clientWidth * ta.clientHeight;
                if (area > bestArea) {
                    best = ta;
                    bestArea = area;
                }
            }
            return { found: true, type: 'textarea', tag: best.tagName };
        }
        return { found: false, error: 'no input found' };
    }
    
    // Pick the largest contenteditable by area (Agora approach)
    let best = editables[0];
    let bestArea = best.clientWidth * best.clientHeight;
    for (const el of editables) {
        const area = el.clientWidth * el.clientHeight;
        if (area > bestArea) {
            best = el;
            bestArea = area;
        }
    }
    best.focus();
    return { found: true, type: 'contenteditable', area: bestArea, tag: best.tagName };
})()
"""

def make_focus_and_type_js(text):
    """Build focus-and-type JS with embedded text value (CDP arguments don't work with arrow functions)."""
    # Escape backslashes and quotes for JS string embedding
    escaped = text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '\\r')
    return f"""
    (() => {{
        const text = '{escaped}';
        // Strategy 1: contenteditable elements
        const editables = document.querySelectorAll('[contenteditable="true"]');
        let input = null;
        if (editables.length > 0) {{
            let bestArea = 0;
            for (const el of editables) {{
                const area = el.clientWidth * el.clientHeight;
                if (area > bestArea) {{ input = el; bestArea = area; }}
            }}
        }}
        // Strategy 2: rich-textarea (Gemini)
        if (!input) {{
            const rich = document.querySelector('rich-textarea');
            if (rich) {{
                rich.textContent = text;
                rich.dispatchEvent(new Event('input', {{ bubbles: true }}));
                return {{ ok: true, method: 'rich-textarea' }};
            }}
        }}
        // Strategy 3: textarea
        if (!input) {{
            const textareas = document.querySelectorAll('textarea');
            if (textareas.length > 0) {{
                let bestArea = 0;
                for (const ta of textareas) {{
                    const area = ta.clientWidth * ta.clientHeight;
                    if (area > bestArea) {{ input = ta; bestArea = area; }}
                }}
            }}
        }}
        if (!input) return {{ error: 'no input found' }};
        input.focus();
        if (input.contentEditable === 'true' || input.isContentEditable) {{
            document.execCommand('insertText', false, text);
            return {{ ok: true, method: 'execCommand' }};
        }}
        if (input.tagName === 'TEXTAREA') {{
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(input, text);
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return {{ ok: true, method: 'textarea-set' }};
        }}
        return {{ error: 'unknown input type' }};
    }})()
    """

UNIVERSAL_SEND_ENTER = """
(() => {
    // Press Enter on the input
    const active = document.activeElement;
    if (!active) return { error: 'no active element' };
    
    active.dispatchEvent(new KeyboardEvent('keydown', {
        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
    }));
    active.dispatchEvent(new KeyboardEvent('keyup', {
        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
    }));
    return { ok: true };
})()
"""

# Universal response detection - works across all AI services
UNIVERSAL_GET_RESPONSE = """
(() => {
    // Strategy 1: Look for assistant messages (ChatGPT pattern)
    let msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        // Check if this is the latest message overall (not an old response)
        const allMsgs = document.querySelectorAll('[data-message-author-role]');
        const lastOverall = allMsgs[allMsgs.length - 1];
        const isLatest = lastOverall && lastOverall.getAttribute('data-message-author-role') === 'assistant';
        return { 
            text: last.innerText, 
            count: msgs.length, 
            source: 'chatgpt',
            isLatest: isLatest,
            hasStreaming: !!last.querySelector('[data-is-streaming="true"]'),
            hasStopButton: !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="stop"]')
        };
    }
    
    // Strategy 1b: Look for agent-turn (newer ChatGPT pattern)
    msgs = document.querySelectorAll('.agent-turn');
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        return { 
            text: last.innerText, 
            count: msgs.length, 
            source: 'chatgpt-agent-turn',
            isLatest: true,
            hasStreaming: false,
            hasStopButton: !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="stop"]')
        };
    }
    
    // Strategy 2: Look for model responses (Gemini pattern - multiple selectors)
    msgs = document.querySelectorAll('model-response');
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        const rawText = last.innerText?.trim();
        if (rawText && rawText !== 'Gemini said' && rawText !== 'You said') {
            const text = rawText.replace(/^(Gemini said|You said)[ ]*/i, '').trim();
            if (text) return { 
                text: text, 
                count: msgs.length, 
                source: 'gemini',
                isLatest: true,
                hasStreaming: false,
                hasStopButton: !!document.querySelector('button[aria-label*="Stop"], .stop-button')
            };
        }
    }
    
    // Strategy 2b: Gemini with assistant-messages-primary
    msgs = document.querySelectorAll('assistant-messages-primary .message-text, .message-content');
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        return { 
            text: last.innerText, 
            count: msgs.length, 
            source: 'gemini-assistant',
            isLatest: true,
            hasStreaming: false,
            hasStopButton: !!document.querySelector('button[aria-label*="Stop"], .stop-button')
        };
    }
    
    // Strategy 2c: Gemini response-container (newer UI)
    msgs = document.querySelectorAll('response-container');
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        // Extract text from visible inner elements (skip headers like "Gemini said")
        const innerTexts = [];
        for (const el of last.querySelectorAll('*')) {
            if (el.children.length === 0 && el.innerText && el.innerText.trim() && 
                el.innerText.trim() !== 'Gemini said' && el.innerText.trim() !== 'You said') {
                innerTexts.push(el.innerText.trim());
            }
        }
        const text = innerTexts.join(' ');
        if (text) {
            return { 
                text: text, 
                count: msgs.length, 
                source: 'gemini-response-container',
                isLatest: true,
                hasStreaming: false,
                hasStopButton: !!document.querySelector('button[aria-label*="Stop"], .stop-button')
            };
        }
    }
    
    // Strategy 2d: Gemini structured-content-container (fallback)
    msgs = document.querySelectorAll('structured-content-container');
    if (msgs.length > 0) {
        // Find the last visible one with text
        for (let i = msgs.length - 1; i >= 0; i--) {
            const el = msgs[i];
            if (el.offsetParent !== null && getComputedStyle(el).display !== 'none') {
                const text = el.innerText?.trim();
                if (text && text !== 'Gemini said' && text !== 'You said') {
                    return { 
                        text: text, 
                        count: msgs.length, 
                        source: 'gemini-structured',
                        isLatest: true,
                        hasStreaming: false,
                        hasStopButton: !!document.querySelector('button[aria-label*="Stop"], .stop-button')
                    };
                }
            }
        }
    }
    
    // Strategy 3: Look for Claude pattern
    msgs = document.querySelectorAll('[data-is-streaming], .assistant-message');
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        return { 
            text: last.innerText, 
            count: msgs.length, 
            source: 'claude',
            isLatest: true,
            hasStreaming: last.hasAttribute('data-is-streaming'),
            hasStopButton: !!document.querySelector('button[aria-label*="Stop"]')
        };
    }
    
    // Strategy 4: Look for Grok pattern
    msgs = document.querySelectorAll('[data-testid="grok-response"], .grok-response');
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        return { 
            text: last.innerText, 
            count: msgs.length, 
            source: 'grok',
            isLatest: true,
            hasStreaming: false,
            hasStopButton: !!document.querySelector('button[aria-label*="Stop"]')
        };
    }
    
    // Strategy 5: Generic - find any response-like container
    // Look for elements that contain long text blocks
    const allDivs = document.querySelectorAll('div, p, section');
    let longestText = '';
    let longestEl = null;
    for (const div of allDivs) {
        const text = div.innerText || '';
        if (text.length > longestText.length && text.length > 100) {
            // Check if this looks like a response (not navigation, not header)
            const rect = div.getBoundingClientRect();
            if (rect.height > 50 && rect.width > 200) {
                longestText = text;
                longestEl = div;
            }
        }
    }
    
    if (longestEl) {
        return { 
            text: longestText, 
            count: 1, 
            source: 'generic',
            hasStreaming: false,
            hasStopButton: false
        };
    }
    
    return { text: '', count: 0, source: 'none', hasStreaming: false, hasStopButton: false };
})()
"""

# Returns just the message count (fast, no text extraction)
UNIVERSAL_GET_MSG_COUNT = """
(() => {
    let msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
    if (msgs.length > 0) return { count: msgs.length, source: 'chatgpt' };
    msgs = document.querySelectorAll('.agent-turn');
    if (msgs.length > 0) return { count: msgs.length, source: 'chatgpt-agent-turn' };
    msgs = document.querySelectorAll('model-response');
    if (msgs.length > 0) return { count: msgs.length, source: 'gemini' };
    if (msgs.length > 0) return { count: msgs.length, source: 'gemini-assistant' };
    msgs = document.querySelectorAll('[data-is-streaming]');
    if (msgs.length > 0) return { count: msgs.length, source: 'claude' };
    return { count: 0, source: 'none' };
})()
"""


# ============================================================================
# MUTATION OBSERVER STREAMING DETECTION
# ============================================================================

def make_mutation_observer_js(timeout_ms, silence_ms, initial_msg_count=0, prev_text=""):
    """Build MutationObserver JS with embedded values (CDP arguments don't work with arrow functions).
    If initial_msg_count > 0, waits for message count to increase before tracking text changes.
    If prev_text is set, ignores response text equal to prev_text (waits for a genuinely NEW response)."""
    return f"""
    new Promise((resolve) => {{
        const timeoutMs = {timeout_ms};
        const silenceMs = {silence_ms};
        const initialMsgCount = {initial_msg_count};
        const prevText = {json.dumps(prev_text)};
        const startTime = Date.now();
        let lastChangeTime = Date.now();
        let lastText = '';
        let observer = null;
        let checkInterval = null;
        let countIncreased = initialMsgCount === 0;
        let countIncreaseTime = 0;
        
        function getMsgCount() {{
            let msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            if (msgs.length > 0) return msgs.length;
            msgs = document.querySelectorAll('.agent-turn');
            if (msgs.length > 0) return msgs.length;
            msgs = document.querySelectorAll('model-response');
            if (msgs.length > 0) return msgs.length;
            msgs = document.querySelectorAll('assistant-messages-primary .message-text');
            if (msgs.length > 0) return msgs.length;
            msgs = document.querySelectorAll('[data-is-streaming]');
            if (msgs.length > 0) return msgs.length;
            return 0;
        }}
        
        function getLatestAssistantText() {{
            // Only look at the LAST message from each strategy — never fall through to old messages
            let msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            if (msgs.length > 0) return msgs[msgs.length - 1].innerText || '';
            msgs = document.querySelectorAll('.agent-turn');
            if (msgs.length > 0) return msgs[msgs.length - 1].innerText || '';
            
            // Gemini: model-response has header-only innerText, real content in child containers
            msgs = document.querySelectorAll('model-response');
            if (msgs.length > 0) {{
                const last = msgs[msgs.length - 1];
                const t = last.innerText?.trim();
                if (t && t !== 'Gemini said' && t !== 'You said') {{
                    // Strip "Gemini said" / "You said" header prefix if present
                    const stripped = t.replace(/^(Gemini said|You said)[ ]*/i, '').trim();
                    if (stripped) return stripped;
                }}
                // Header-only: check response-container children of this same element
                const rc = last.querySelector('response-container');
                if (rc) {{
                    const texts = [];
                    for (const el of rc.querySelectorAll('*')) {{
                        if (el.children.length === 0 && el.innerText && el.innerText.trim() &&
                            el.innerText.trim() !== 'Gemini said' && el.innerText.trim() !== 'You said') {{
                            texts.push(el.innerText.trim());
                        }}
                    }}
                    if (texts.length > 0) return texts.join(' ');
                }}
                // Still loading, no content yet
                return '';
            }}
            msgs = document.querySelectorAll('assistant-messages-primary .message-text');
            if (msgs.length > 0) {{
                const last = msgs[msgs.length - 1];
                const t = last.innerText?.trim();
                if (t && t !== 'Gemini said' && t !== 'You said') return t;
                return '';
            }}
            msgs = document.querySelectorAll('[data-is-streaming]');
            if (msgs.length > 0) return msgs[msgs.length - 1].innerText || '';
            // Fallback: standalone response-container
            msgs = document.querySelectorAll('response-container');
            if (msgs.length > 0) {{
                const last = msgs[msgs.length - 1];
                const texts = [];
                for (const el of last.querySelectorAll('*')) {{
                    if (el.children.length === 0 && el.innerText && el.innerText.trim() && 
                        el.innerText.trim() !== 'Gemini said' && el.innerText.trim() !== 'You said') {{
                        texts.push(el.innerText.trim());
                    }}
                }}
                if (texts.length > 0) return texts.join(' ');
            }}
            // Fallback: standalone structured-content-container
            msgs = document.querySelectorAll('structured-content-container');
            if (msgs.length > 0) {{
                const last = msgs[msgs.length - 1];
                if (last.offsetParent !== null && getComputedStyle(last).display !== 'none') {{
                    const t = last.innerText?.trim();
                    if (t && t !== 'Gemini said' && t !== 'You said') return t;
                }}
            }}
            return '';
        }}
        
        function getAnyText() {{
            // Fallback: find ANY response text (used only when no initial_msg_count tracking)
            let msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            if (msgs.length > 0) return msgs[msgs.length - 1].innerText;
            msgs = document.querySelectorAll('.agent-turn');
            if (msgs.length > 0) return msgs[msgs.length - 1].innerText;
            msgs = document.querySelectorAll('model-response');
            if (msgs.length > 0) {{
                const last = msgs[msgs.length - 1];
                const t = last.innerText?.trim();
                if (t && t !== 'Gemini said' && t !== 'You said') {{
                    const stripped = t.replace(/^(Gemini said|You said)[ ]*/i, '').trim();
                    if (stripped) return stripped;
                }}
                // Header-only: check child containers
                const rc = last.querySelector('response-container');
                if (rc) {{
                    const texts = [];
                    for (const el of rc.querySelectorAll('*')) {{
                    if (el.children.length === 0 && el.innerText && el.innerText.trim() && 
                        el.innerText.trim() !== 'Gemini said' && el.innerText.trim() !== 'You said') {{
                        texts.push(el.innerText.trim());
                    }}
                    }}
                    if (texts.length > 0) return texts.join(' ');
                }}
            }}
            msgs = document.querySelectorAll('assistant-messages-primary .message-text');
            if (msgs.length > 0) {{
                const last = msgs[msgs.length - 1];
                const t = last.innerText?.trim();
                if (t && t !== 'Gemini said' && t !== 'You said') return t;
            }}
            msgs = document.querySelectorAll('[data-is-streaming]');
            if (msgs.length > 0) return msgs[msgs.length - 1].innerText;
            msgs = document.querySelectorAll('response-container');
            if (msgs.length > 0) {{
                const last = msgs[msgs.length - 1];
                const texts = [];
                for (const el of last.querySelectorAll('*')) {{
                    if (el.children.length === 0 && el.innerText && el.innerText.trim() && 
                        el.innerText.trim() !== 'Gemini said' && el.innerText.trim() !== 'You said') {{
                        texts.push(el.innerText.trim());
                    }}
                }}
                const joined = texts.join(' ');
                if (joined) return joined;
            }}
            msgs = document.querySelectorAll('structured-content-container');
            if (msgs.length > 0) {{
                for (let i = msgs.length - 1; i >= 0; i--) {{
                    const el = msgs[i];
                    if (el.offsetParent !== null && getComputedStyle(el).display !== 'none') {{
                        const t = el.innerText?.trim();
                        if (t && t !== 'Gemini said' && t !== 'You said') return t;
                    }}
                }}
            }}
            return '';
        }}
        
        function getText() {{
            const t = initialMsgCount > 0 ? getLatestAssistantText() : getAnyText();
            // Ignore the previous response text: wait for a genuinely NEW response
            if (prevText && t && t.trim() === prevText.trim()) return '';
            return t;
        }}
        
        function isStreaming() {{
            // Gemini loading animation
            if (document.body.classList.contains('enable-lm-loading-animation')) return true;
            // Stop button (ChatGPT, Claude)
            if (document.querySelector('button[aria-label*="Stop"], button[aria-label*="stop"], .stop-button')) return true;
            // Claude streaming attribute
            const streaming = document.querySelectorAll('[data-is-streaming="true"]');
            if (streaming.length > 0) return true;
            return false;
        }}
        
        function checkDone() {{
            const now = Date.now();
            
            // Phase 1: Wait for message count to increase
            if (!countIncreased) {{
                const currentCount = getMsgCount();
                if (currentCount > initialMsgCount) {{
                    countIncreased = true;
                    countIncreaseTime = now;
                    lastText = '';
                    lastChangeTime = now;
                }}
                if (now - startTime >= timeoutMs) {{
                    cleanup();
                    resolve({{ done: false, text: '', duration: now - startTime, error: 'timeout_no_new_message', initial_count: initialMsgCount, current_count: currentCount }});
                    return;
                }}
                return;
            }}
            
            // Phase 2: Track text changes after count increased
            const currentText = getText();
            if (currentText !== lastText) {{
                lastText = currentText;
                lastChangeTime = now;
            }}
            const silenceDuration = now - lastChangeTime;
            
            // If text exists and hasn't changed for a long time, finish even if streaming indicator is stuck
            // (Gemini keeps enable-lm-loading-animation on permanently after response)
            if (lastText.length > 0 && silenceDuration >= 5000) {{
                cleanup();
                resolve({{ done: true, text: lastText, duration: now - startTime, msg_count: getMsgCount(), note: 'text_stable_despite_streaming' }});
                return;
            }}
            
            // Don't finish while still streaming (but only reset silence if text is actively changing)
            if (isStreaming()) {{
                if (currentText !== lastText) {{
                    lastChangeTime = now;  // Only reset timer when text actually changes
                }}
                return;
            }}
            
            // After streaming stops, wait for silence period
            if (silenceDuration >= silenceMs && lastText.length > 0) {{
                cleanup();
                resolve({{ done: true, text: lastText, duration: now - startTime, msg_count: getMsgCount() }});
                return;
            }}
            
            // Quick finish if no stop button and text exists (fallback)
            if (!isStreaming() && lastText.length > 0 && silenceDuration >= 500) {{
                cleanup();
                resolve({{ done: true, text: lastText, duration: now - startTime, msg_count: getMsgCount() }});
                return;
            }}
            
            if (now - startTime >= timeoutMs) {{
                cleanup();
                resolve({{ done: false, text: lastText, duration: now - startTime, error: 'timeout' }});
                return;
            }}
        }}
        
        function cleanup() {{
            if (observer) {{ observer.disconnect(); observer = null; }}
            if (checkInterval) {{ clearInterval(checkInterval); checkInterval = null; }}
        }}
        
        const target = document.querySelector('[data-message-author-role="assistant"]')?.parentElement ||
                       document.querySelector('model-response')?.parentElement ||
                       document.body;
        
        observer = new MutationObserver(() => {{ lastChangeTime = Date.now(); }});
        observer.observe(target, {{ childList: true, subtree: true, characterData: true }});
        
        checkInterval = setInterval(checkDone, 200);
        lastText = initialMsgCount > 0 ? '' : getText();
    }})
    """


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_list():
    tabs = http_get("/json/list")
    if isinstance(tabs, dict) and "error" in tabs:
        print(json.dumps(tabs, indent=2))
        return
    result = []
    for tab in tabs:
        if tab.get("type") == "page":  # Only show pages, not iframes/workers
            result.append({
                "id": tab.get("id"),
                "title": tab.get("title", "")[:80],
                "url": tab.get("url", ""),
            })
    print(json.dumps(result, indent=2))


def cmd_read(tab_id):
    ws = cdp_connect(tab_id)
    if not ws:
        print(json.dumps({"error": "cannot connect to tab"}))
        return
    try:
        result = cdp_send_with_retry(ws, "Runtime.evaluate", {
            "expression": UNIVERSAL_GET_RESPONSE,
            "returnByValue": True,
        }, tab_id=tab_id)
        if "result" in result:
            val = result["result"]
            if "value" in val:
                print(json.dumps(val["value"], indent=2, ensure_ascii=False))
                return
        print(json.dumps(result, indent=2))
    finally:
        try:
            ws.close()
        except:
            pass


# Unstick a stuck Gemini "Stop response" state: clicking the stuck stop button
# resets the send button back to "Send message". Returns {reset: bool}.
RESET_STUCK_JS = """
(() => {
    const gemBtn = document.querySelector('gem-icon-button.send-button button');
    if (gemBtn && gemBtn.getAttribute('aria-label') === 'Stop response') {
        gemBtn.click();
        return { reset: true };
    }
    return { reset: false };
})()
"""

# Focus the input and select all existing content so the following Input.insertText
# REPLACES it (clears any accumulated/unsent text). Works for contenteditable,
# rich-textarea (Gemini Quill) and plain textarea.
FOCUS_AND_CLEAR_JS = """
(() => {
    const editables = document.querySelectorAll('[contenteditable="true"]');
    let input = null;
    let bestArea = 0;
    for (const el of editables) {
        const area = el.clientWidth * el.clientHeight;
        if (area > bestArea) { input = el; bestArea = area; }
    }
    if (!input) {
        const textareas = document.querySelectorAll('textarea');
        for (const ta of textareas) {
            const area = ta.clientWidth * ta.clientHeight;
            if (area > bestArea) { input = ta; bestArea = area; }
        }
    }
    if (!input) {
        const rich = document.querySelector('rich-textarea');
        if (rich) { rich.focus(); return { ok: true, method: 'rich-textarea' }; }
    }
    if (!input) return { error: 'no input found' };
    input.focus();
    // Select all existing content so insertText replaces it (clears accumulated text)
    if (input.tagName === 'TEXTAREA') {
        input.select();
    } else {
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(input);
        sel.removeAllRanges();
        sel.addRange(range);
    }
    return { ok: true, method: input.tagName };
})()
"""

# Click the send button. Uses aria-label as the reliable state signal for Gemini
# ("Send message" vs "Stop response"), data-testid for ChatGPT, aria-label for Claude.
SEND_CLICK_JS = """
(() => {
    // ChatGPT: button[data-testid=send-button]
    let btn = document.querySelector('button[data-testid="send-button"]');
    if (btn && !btn.disabled) { btn.click(); return { ok: true, method: 'chatgpt' }; }

    // Gemini: inner <button> aria-label is the reliable state signal
    const gem = document.querySelector('gem-icon-button.send-button button') ||
                document.querySelector('gem-icon-button.send-button');
    if (gem) {
        const aria = gem.getAttribute('aria-label') || '';
        if (aria === 'Stop response') {
            return { ok: false, method: 'gemini-still-stuck', fallback: 'enter_key' };
        }
        gem.click();
        return { ok: true, method: 'gemini' };
    }

    // Claude: button with send-related aria-label
    btn = document.querySelector('button[aria-label*="Send"], button[aria-label*="send"]');
    if (btn && !btn.disabled) { btn.click(); return { ok: true, method: 'claude' }; }

    return { ok: false, method: 'no_button_found', fallback: 'enter_key' };
})()
"""

REFOCUS_JS = """(() => { const e = document.querySelector('[contenteditable="true"]') || document.querySelector('rich-textarea') || document.querySelector('textarea'); if (e) { e.focus(); return true; } return false; })()"""

# Detect Gemini's stuck state: after a response completes, Gemini leaves its send
# button's inner <button> aria-label at "Stop response" permanently (a Gemini UI
# bug). Clicking it does NOT reliably reset. The reliable fix is a page reload,
# which preserves the conversation history but resets the Angular UI state.
GEMINI_STUCK_STATE_JS = """
(() => {
    const g = document.querySelector('gem-icon-button.send-button button');
    return { stuck: !!(g && g.getAttribute('aria-label') === 'Stop response') };
})()
"""


def robust_send(ws, tab_id, text):
    """Shared send routine used by cmd_send and _send_and_wait.

    Handles: (1) reloading to recover from Gemini's stuck 'Stop response' state,
    (2) clearing accumulated input text, (3) inserting text via CDP, (4) clicking
    send with Enter-key fallback. Returns (result_dict, ws) — ws may be a new
    connection if a reload happened.
    """
    reloaded = False
    # Step 0: Detect Gemini stuck state. If the send button is stuck at
    # "Stop response" while we're about to send, reload the page to reset the UI.
    stuck_result = cdp_send_with_retry(ws, "Runtime.evaluate", {
        "expression": GEMINI_STUCK_STATE_JS,
        "returnByValue": True,
    }, tab_id=tab_id)
    stuck_val = stuck_result.get("result", {}).get("value", {}) if "result" in stuck_result else {}
    if stuck_val.get("stuck"):
        cdp_send_with_retry(ws, "Page.reload", {}, tab_id=tab_id)
        try:
            ws.close()
        except:
            pass
        time.sleep(7)  # Wait for reload + Angular re-init (conversation preserved)
        ws = cdp_connect(tab_id)
        reloaded = True

    # Step 1: Focus input + select all existing content (so insertText replaces it)
    focus_result = cdp_send_with_retry(ws, "Runtime.evaluate", {
        "expression": FOCUS_AND_CLEAR_JS,
        "returnByValue": True,
    }, tab_id=tab_id)
    focus_val = focus_result.get("result", {}).get("value", {}) if "result" in focus_result else {}

    # Capture the CURRENT latest response text (before sending) so the waiter can
    # tell when a genuinely NEW response has arrived (avoids returning stale text).
    prev_text = ""
    prev_result = cdp_send_with_retry(ws, "Runtime.evaluate", {
        "expression": UNIVERSAL_GET_RESPONSE,
        "returnByValue": True,
    }, tab_id=tab_id)
    if "result" in prev_result:
        prev_text = (prev_result["result"].get("value", {}) or {}).get("text", "") or ""

    # Step 2: Insert text via CDP Input.insertText (replaces selection)
    insert_result = cdp_send_with_retry(ws, "Input.insertText", {
        "text": text,
    }, tab_id=tab_id)

    time.sleep(0.4)  # Brief pause for UI (Angular/React) to register text

    # Step 3: Click send button
    click_result = cdp_send_with_retry(ws, "Runtime.evaluate", {
        "expression": SEND_CLICK_JS,
        "returnByValue": True,
    }, tab_id=tab_id)
    click_val = click_result.get("result", {}).get("value", {}) if "result" in click_result else {}
    send_method = click_val.get("method", "unknown")

    if not click_val.get("ok"):
        # Fallback: re-focus then press Enter via CDP key events
        cdp_send_with_retry(ws, "Runtime.evaluate", {
            "expression": REFOCUS_JS,
            "returnByValue": True,
        }, tab_id=tab_id)
        time.sleep(0.1)
        cdp_send_with_retry(ws, "Input.dispatchKeyEvent", {
            "type": "keyDown", "key": "Enter", "code": "Enter",
            "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
        }, tab_id=tab_id)
        cdp_send_with_retry(ws, "Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "Enter", "code": "Enter",
            "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
        }, tab_id=tab_id)
        send_method = "enter_key_fallback"

    return {
        "reloaded": reloaded,
        "prev_text": prev_text,
        "typed": len(text),
        "focus": focus_val,
        "insert": "ok" if "error" not in insert_result else insert_result,
        "send_method": send_method,
    }, ws


def cmd_send(tab_id, text):
    ws = cdp_connect(tab_id)
    if not ws:
        print(json.dumps({"error": "cannot connect to tab"}))
        return
    try:
        result, ws = robust_send(ws, tab_id, text)
        result["ok"] = True
        print(json.dumps(result))
    finally:
        try:
            ws.close()
        except:
            pass


def cmd_type(tab_id, text):
    ws = cdp_connect(tab_id)
    if not ws:
        print(json.dumps({"error": "cannot connect to tab"}))
        return
    try:
        focus_type_js = make_focus_and_type_js(text)
        result = cdp_send_with_retry(ws, "Runtime.evaluate", {
            "expression": focus_type_js,
            "returnByValue": True,
        }, tab_id=tab_id)
        
        if "result" in result:
            val = result["result"]
            if "value" in val:
                print(json.dumps(val["value"], indent=2))
                return
        print(json.dumps(result, indent=2))
    finally:
        try:
            ws.close()
        except:
            pass


def cmd_click(tab_id, selector):
    ws = cdp_connect(tab_id)
    if not ws:
        print(json.dumps({"error": "cannot connect to tab"}))
        return
    try:
        # Escape selector for JS string embedding
        escaped_selector = selector.replace('\\', '\\\\').replace("'", "\\'")
        js = f"""
        (() => {{
            const el = document.querySelector('{escaped_selector}');
            if (!el) return {{ error: 'not found: {escaped_selector}' }};
            el.click();
            return {{ ok: true, tag: el.tagName }};
        }})()
        """
        result = cdp_send_with_retry(ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True,
        }, tab_id=tab_id)
        if "result" in result:
            val = result["result"]
            if "value" in val:
                print(json.dumps(val["value"], indent=2))
                return
        print(json.dumps(result, indent=2))
    finally:
        try:
            ws.close()
        except:
            pass


def cmd_navigate(tab_id, url):
    ws = cdp_connect(tab_id)
    if not ws:
        print(json.dumps({"error": "cannot connect to tab"}))
        return
    try:
        result = cdp_send_with_retry(ws, "Page.navigate", {"url": url}, tab_id=tab_id)
        print(json.dumps(result, indent=2))
    finally:
        try:
            ws.close()
        except:
            pass


def cmd_eval(tab_id, js_code):
    ws = cdp_connect(tab_id)
    if not ws:
        print(json.dumps({"error": "cannot connect to tab"}))
        return
    try:
        result = cdp_send_with_retry(ws, "Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": True,
            "awaitPromise": True,
        }, tab_id=tab_id)
        if "result" in result:
            val = result["result"]
            if "value" in val:
                print(json.dumps(val["value"], indent=2, ensure_ascii=False))
                return
        print(json.dumps(result, indent=2))
    finally:
        try:
            ws.close()
        except:
            pass


def cmd_wait_stream(tab_id, timeout_ms=60000, silence_ms=1500):
    """Wait for AI response to finish streaming using MutationObserver.
    
    Tracks message count to detect when a NEW response arrives and finishes,
    rather than returning a stale (old) response.
    """
    ws = cdp_connect(tab_id)
    if not ws:
        print(json.dumps({"error": "cannot connect to tab"}))
        return
    try:
        # Step 1: Record current message count before waiting
        count_result = cdp_send(ws, "Runtime.evaluate", {
            "expression": UNIVERSAL_GET_MSG_COUNT,
            "returnByValue": True,
        })
        initial_count = 0
        if "result" in count_result and "value" in count_result["result"]:
            initial_count = count_result["result"]["value"].get("count", 0)

        # Step 2: Check if there's already a new response (count increased since last send)
        initial = cdp_send(ws, "Runtime.evaluate", {
            "expression": UNIVERSAL_GET_RESPONSE,
            "returnByValue": True,
        })
        initial_text = ""
        has_streaming = False
        has_stop = False
        initial_count_val = 0
        if "result" in initial and "value" in initial["result"]:
            val = initial["result"]["value"]
            initial_text = val.get("text", "")
            has_streaming = val.get("hasStreaming", False)
            has_stop = val.get("hasStopButton", False)
            initial_count_val = val.get("count", 0)
        
        # If response exists, not streaming, and count hasn't changed since we started,
        # this might be an old response. Check if we should wait for a new one.
        # The caller should track message counts between send() and wait_stream() calls.
        # For now: if text exists and not streaming, report it.
        # The caller can compare counts to detect stale responses.
        if initial_text and not has_streaming and not has_stop:
            print(json.dumps({
                "status": "complete",
                "text": initial_text,
                "msg_count": initial_count_val,
                "duration_ms": 0
            }))
            return
        
        # Step 3: If no response yet OR still streaming, wait for it to finish
        # Use initial_msg_count=0 to skip Phase 1 (count tracking) — the caller
        # already sent a message and knows a new response is coming.
        observer_js = make_mutation_observer_js(timeout_ms, silence_ms, initial_msg_count=0)
        result = cdp_send(ws, "Runtime.evaluate", {
            "expression": observer_js,
            "returnByValue": True,
            "awaitPromise": True,
        }, timeout=timeout_ms // 1000 + 5)
        
        if "result" in result:
            val = result["result"].get("value", {})
            print(json.dumps({
                "status": "complete" if val.get("done") else "timeout",
                "text": val.get("text", initial_text),
                "duration_ms": val.get("duration", 0),
            }, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({
                "status": "error",
                "text": initial_text,
                "error": str(result)
            }))
    finally:
        try:
            ws.close()
        except:
            pass


def cmd_poll(tab_id, interval_ms=2000):
    """Poll for new chat content - returns text when it changes."""
    ws = cdp_connect(tab_id)
    if not ws:
        print(json.dumps({"error": "cannot connect to tab"}))
        return
    try:
        last_hash = ""
        for _ in range(60):  # max 2 minutes
            result = cdp_send(ws, "Runtime.evaluate", {
                "expression": UNIVERSAL_GET_RESPONSE,
                "returnByValue": True,
            })
            if "result" in result:
                val = result["result"]
                if "value" in val:
                    current = val["value"]
                    current_hash = str(current.get("text", ""))[-200:]
                    if current_hash != last_hash and not current.get("hasStreaming") and not current.get("hasStopButton"):
                        last_hash = current_hash
                        print(json.dumps(current, indent=2, ensure_ascii=False))
                        return
                    if current.get("hasStreaming") or current.get("hasStopButton"):
                        time.sleep(1)
                        continue
            time.sleep(interval_ms / 1000)
        print(json.dumps({"error": "poll timeout", "last": last_hash}))
    finally:
        try:
            ws.close()
        except:
            pass


def cmd_bridge(tab_from, tab_to, rounds=3):
    """Bridge conversation: read from tab_from, send to tab_to, wait for response, repeat."""
    results = []
    
    for i in range(rounds):
        round_result = {"round": i}
        
        # Step 1: Wait for source to have a complete response
        ws_from = cdp_connect(tab_from)
        if not ws_from:
            round_result["error"] = "cannot connect to source"
            results.append(round_result)
            break
        
        try:
            # First check if source has any response
            initial = cdp_send(ws_from, "Runtime.evaluate", {
                "expression": UNIVERSAL_GET_RESPONSE,
                "returnByValue": True,
            })
            
            source_text = ""
            has_streaming = False
            has_stop = False
            
            if "result" in initial and "value" in initial["result"]:
                val = initial["result"]["value"]
                source_text = val.get("text", "")
                has_streaming = val.get("hasStreaming", False)
                has_stop = val.get("hasStopButton", False)
            
            # If source is streaming, wait for it to finish
            if has_streaming or has_stop:
                observer_js = make_mutation_observer_js(60000, 1500)
                wait_result = cdp_send(ws_from, "Runtime.evaluate", {
                    "expression": observer_js,
                    "returnByValue": True,
                    "awaitPromise": True,
                }, timeout=65)
                
                if "result" in wait_result and "value" in wait_result["result"]:
                    val = wait_result["result"]["value"]
                    source_text = val.get("text", source_text)
            
            if not source_text:
                round_result["error"] = "no text found in source"
                results.append(round_result)
                break
            
            round_result["source_chars"] = len(source_text)
            round_result["source_preview"] = source_text[:200]
            
        finally:
            try:
                ws_from.close()
            except:
                pass
        
        # Step 2: Send to target and wait for response (use combined send-wait approach)
        round_result_send = _send_and_wait(tab_to, source_text[:8000])
        round_result.update(round_result_send)
        
        results.append(round_result)
    
    print(json.dumps(results, indent=2, ensure_ascii=False))


def _send_and_wait(tab_id, text, wait_timeout_ms=60000, silence_ms=1500):
    """Send text to a tab and wait for response. Returns dict with send/wait results."""
    result = {}
    
    # Record message count BEFORE sending
    ws_pre = cdp_connect(tab_id)
    if not ws_pre:
        return {"error": "cannot connect to tab"}
    
    pre_count = 0
    try:
        count_result = cdp_send(ws_pre, "Runtime.evaluate", {
            "expression": UNIVERSAL_GET_MSG_COUNT,
            "returnByValue": True,
        })
        if "result" in count_result and "value" in count_result["result"]:
            pre_count = count_result["result"]["value"].get("count", 0)
    finally:
        try:
            ws_pre.close()
        except:
            pass
    
    result["pre_msg_count"] = pre_count
    
    # Send the text (shared robust routine: unstick + clear + insert + click)
    ws_send = cdp_connect(tab_id)
    if not ws_send:
        return {"error": "cannot connect for send"}
    
    prev_text = ""
    try:
        send_info, ws_send = robust_send(ws_send, tab_id, text)
        result["send_method"] = send_info.get("send_method", "unknown")
        result["reloaded"] = send_info.get("reloaded", False)
        prev_text = send_info.get("prev_text", "") or ""
        result["sent_chars"] = len(text)
    finally:
        try:
            ws_send.close()
        except:
            pass
    
    # Wait for response: check if message count increased, then wait for streaming to finish
    time.sleep(1)  # Brief pause for response to start
    
    ws_wait = cdp_connect(tab_id)
    if not ws_wait:
        return {**result, "error": "cannot connect for wait"}
    
    try:
        # Poll for message count increase or streaming start
        max_wait = wait_timeout_ms // 1000
        found_new = False
        for _ in range(max_wait * 2):  # Check every 500ms
            count_result = cdp_send(ws_wait, "Runtime.evaluate", {
                "expression": UNIVERSAL_GET_MSG_COUNT,
                "returnByValue": True,
            })
            current_count = 0
            if "result" in count_result and "value" in count_result["result"]:
                current_count = count_result["result"]["value"].get("count", 0)
            
            if current_count > pre_count:
                found_new = True
                break
            
            # Also check if streaming started (might be same count but new response appearing)
            check = cdp_send(ws_wait, "Runtime.evaluate", {
                "expression": UNIVERSAL_GET_RESPONSE,
                "returnByValue": True,
            })
            if "result" in check and "value" in check["result"]:
                val = check["result"]["value"]
                if val.get("hasStreaming") or val.get("hasStopButton"):
                    found_new = True
                    break
                # New response text appeared (differs from the pre-send response)
                new_text = val.get("text", "")
                if new_text and new_text.strip() != prev_text.strip():
                    found_new = True
                    break
            
            time.sleep(0.5)
        
        if not found_new:
            # Fallback: just wait for whatever response exists
            pass
        
        # Now wait for streaming to finish using MutationObserver.
        # initial_msg_count=0 skips Phase 1 count tracking (unreliable on Gemini).
        # prev_text makes the observer ignore the pre-send response and wait for NEW text.
        observer_js = make_mutation_observer_js(wait_timeout_ms, silence_ms, initial_msg_count=0, prev_text=prev_text)
        wait_result = cdp_send(ws_wait, "Runtime.evaluate", {
            "expression": observer_js,
            "returnByValue": True,
            "awaitPromise": True,
        }, timeout=wait_timeout_ms // 1000 + 5)
        
        if "result" in wait_result and "value" in wait_result["result"]:
            val = wait_result["result"]["value"]
            result["response_text"] = val.get("text", "")
            result["response_duration_ms"] = val.get("duration", 0)
            result["response_complete"] = val.get("done", False)
            if not result["response_text"]:
                result["note"] = "empty response (target may be rate-limited or not logged in)"
        else:
            # Observer didn't resolve (usually an empty/stalled response). Do a final
            # direct read so the caller still gets useful state instead of a bare error.
            final = cdp_send(ws_wait, "Runtime.evaluate", {
                "expression": UNIVERSAL_GET_RESPONSE,
                "returnByValue": True,
            })
            final_text = ""
            if "result" in final and "value" in final["result"]:
                final_text = final["result"]["value"].get("text", "")
            result["response_text"] = final_text
            result["response_complete"] = bool(final_text)
            if not final_text:
                result["note"] = "empty response (target may be rate-limited or not logged in)"
    finally:
        try:
            ws_wait.close()
        except:
            pass
    
    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "list":
        cmd_list()
    elif cmd == "read":
        if len(sys.argv) < 3:
            print("Usage: browser-bridge.py read <tab_id>")
            return
        cmd_read(sys.argv[2])
    elif cmd == "type":
        if len(sys.argv) < 4:
            print("Usage: browser-bridge.py type <tab_id> <text>")
            return
        cmd_type(sys.argv[2], " ".join(sys.argv[3:]))
    elif cmd == "send":
        if len(sys.argv) < 4:
            print("Usage: browser-bridge.py send <tab_id> <text>")
            return
        cmd_send(sys.argv[2], " ".join(sys.argv[3:]))
    elif cmd == "click":
        if len(sys.argv) < 4:
            print("Usage: browser-bridge.py click <tab_id> <selector>")
            return
        cmd_click(sys.argv[2], sys.argv[3])
    elif cmd == "navigate":
        if len(sys.argv) < 4:
            print("Usage: browser-bridge.py navigate <tab_id> <url>")
            return
        cmd_navigate(sys.argv[2], sys.argv[3])
    elif cmd == "eval":
        if len(sys.argv) < 4:
            print("Usage: browser-bridge.py eval <tab_id> <js_code>")
            return
        cmd_eval(sys.argv[2], " ".join(sys.argv[3:]))
    elif cmd == "wait-stream":
        if len(sys.argv) < 3:
            print("Usage: browser-bridge.py wait-stream <tab_id> [timeout_ms] [silence_ms]")
            return
        cmd_wait_stream(
            sys.argv[2],
            int(sys.argv[3]) if len(sys.argv) > 3 else 60000,
            int(sys.argv[4]) if len(sys.argv) > 4 else 1500
        )
    elif cmd == "poll":
        if len(sys.argv) < 3:
            print("Usage: browser-bridge.py poll <tab_id> [interval_ms]")
            return
        cmd_poll(sys.argv[2],
                 int(sys.argv[3]) if len(sys.argv) > 3 else 2000)
    elif cmd == "bridge":
        if len(sys.argv) < 4:
            print("Usage: browser-bridge.py bridge <tab_from> <tab_to> [rounds]")
            return
        cmd_bridge(sys.argv[2], sys.argv[3],
                   int(sys.argv[4]) if len(sys.argv) > 4 else 3)
    elif cmd == "send-wait":
        if len(sys.argv) < 4:
            print("Usage: browser-bridge.py send-wait <tab_id> <text> [timeout_ms]")
            return
        tab_id = sys.argv[2]
        # Parse optional --timeout flag
        timeout_ms = 60000
        text_parts = []
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--timeout" and i + 1 < len(sys.argv):
                timeout_ms = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i].startswith("--timeout="):
                timeout_ms = int(sys.argv[i].split("=")[1])
                i += 1
            else:
                text_parts.append(sys.argv[i])
                i += 1
        text = " ".join(text_parts)
        if not text:
            print("Error: text is required")
            return
        result = _send_and_wait(tab_id, text, timeout_ms)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
