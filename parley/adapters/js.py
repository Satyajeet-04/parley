"""
parley.adapters.js - Battle-tested JavaScript snippets for AI chat UIs.

These snippets implement "Universal DOM Discovery": instead of brittle
per-site CSS selectors they try a prioritized list of strategies that cover
ChatGPT, Gemini, Claude and Grok, with a generic fallback. They are kept
verbatim here because every branch was hard-won through live debugging
(Gemini's Angular quirks in particular).

CDP note: `Runtime.evaluate` does not pass `arguments` into arrow functions,
so snippets that need a value are built by functions that embed the value via
Python f-strings / json.dumps.
"""

import json


# Find the primary text input (largest contenteditable, else largest textarea).
UNIVERSAL_FIND_INPUT = """
(() => {
    const editables = document.querySelectorAll('[contenteditable="true"]');
    if (editables.length === 0) {
        const textareas = document.querySelectorAll('textarea');
        if (textareas.length > 0) {
            let best = textareas[0];
            let bestArea = best.clientWidth * best.clientHeight;
            for (const ta of textareas) {
                const area = ta.clientWidth * ta.clientHeight;
                if (area > bestArea) { best = ta; bestArea = area; }
            }
            return { found: true, type: 'textarea', tag: best.tagName };
        }
        return { found: false, error: 'no input found' };
    }
    let best = editables[0];
    let bestArea = best.clientWidth * best.clientHeight;
    for (const el of editables) {
        const area = el.clientWidth * el.clientHeight;
        if (area > bestArea) { best = el; bestArea = area; }
    }
    best.focus();
    return { found: true, type: 'contenteditable', area: bestArea, tag: best.tagName };
})()
"""


def make_focus_and_type_js(text):
    """Build focus-and-type JS with an embedded text value (no submit)."""
    escaped = text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '\\r')
    return f"""
    (() => {{
        const text = '{escaped}';
        const editables = document.querySelectorAll('[contenteditable="true"]');
        let input = null;
        if (editables.length > 0) {{
            let bestArea = 0;
            for (const el of editables) {{
                const area = el.clientWidth * el.clientHeight;
                if (area > bestArea) {{ input = el; bestArea = area; }}
            }}
        }}
        if (!input) {{
            const rich = document.querySelector('rich-textarea');
            if (rich) {{
                rich.textContent = text;
                rich.dispatchEvent(new Event('input', {{ bubbles: true }}));
                return {{ ok: true, method: 'rich-textarea' }};
            }}
        }}
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


# Universal response detection - works across all AI services.
UNIVERSAL_GET_RESPONSE = """
(() => {
    // Strategy 1: assistant messages (ChatGPT)
    let msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
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

    // Strategy 1b: agent-turn (newer ChatGPT)
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

    // Strategy 2: Gemini model-response
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

    // Strategy 2b: Gemini assistant-messages-primary
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

    // Strategy 3: Claude
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

    // Strategy 4: Grok
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

    // Strategy 5: Generic - longest visible text block
    const allDivs = document.querySelectorAll('div, p, section');
    let longestText = '';
    let longestEl = null;
    for (const div of allDivs) {
        const text = div.innerText || '';
        if (text.length > longestText.length && text.length > 100) {
            const rect = div.getBoundingClientRect();
            if (rect.height > 50 && rect.width > 200) {
                longestText = text;
                longestEl = div;
            }
        }
    }
    if (longestEl) {
        return { text: longestText, count: 1, source: 'generic', hasStreaming: false, hasStopButton: false };
    }

    return { text: '', count: 0, source: 'none', hasStreaming: false, hasStopButton: false };
})()
"""


# Returns just the message count (fast, no text extraction).
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


# Unstick a stuck Gemini "Stop response" state (best-effort; reload is the reliable fix).
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


# Focus input and select all existing content so the following Input.insertText REPLACES it.
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


# Click the send button. aria-label is the reliable state signal for Gemini.
SEND_CLICK_JS = """
(() => {
    let btn = document.querySelector('button[data-testid="send-button"]');
    if (btn && !btn.disabled) { btn.click(); return { ok: true, method: 'chatgpt' }; }

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

    btn = document.querySelector('button[aria-label*="Send"], button[aria-label*="send"]');
    if (btn && !btn.disabled) { btn.click(); return { ok: true, method: 'claude' }; }

    return { ok: false, method: 'no_button_found', fallback: 'enter_key' };
})()
"""


REFOCUS_JS = """(() => { const e = document.querySelector('[contenteditable="true"]') || document.querySelector('rich-textarea') || document.querySelector('textarea'); if (e) { e.focus(); return true; } return false; })()"""


# Detect Gemini's stuck state (send button aria-label stuck at "Stop response").
GEMINI_STUCK_STATE_JS = """
(() => {
    const g = document.querySelector('gem-icon-button.send-button button');
    return { stuck: !!(g && g.getAttribute('aria-label') === 'Stop response') };
})()
"""


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
            let msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            if (msgs.length > 0) return msgs[msgs.length - 1].innerText || '';
            msgs = document.querySelectorAll('.agent-turn');
            if (msgs.length > 0) return msgs[msgs.length - 1].innerText || '';

            msgs = document.querySelectorAll('model-response');
            if (msgs.length > 0) {{
                const last = msgs[msgs.length - 1];
                const t = last.innerText?.trim();
                if (t && t !== 'Gemini said' && t !== 'You said') {{
                    const stripped = t.replace(/^(Gemini said|You said)[ ]*/i, '').trim();
                    if (stripped) return stripped;
                }}
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
            if (prevText && t && t.trim() === prevText.trim()) return '';
            return t;
        }}

        function isStreaming() {{
            if (document.body.classList.contains('enable-lm-loading-animation')) return true;
            if (document.querySelector('button[aria-label*="Stop"], button[aria-label*="stop"], .stop-button')) return true;
            const streaming = document.querySelectorAll('[data-is-streaming="true"]');
            if (streaming.length > 0) return true;
            return false;
        }}

        function checkDone() {{
            const now = Date.now();

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

            const currentText = getText();
            if (currentText !== lastText) {{
                lastText = currentText;
                lastChangeTime = now;
            }}
            const silenceDuration = now - lastChangeTime;

            if (lastText.length > 0 && silenceDuration >= 5000) {{
                cleanup();
                resolve({{ done: true, text: lastText, duration: now - startTime, msg_count: getMsgCount(), note: 'text_stable_despite_streaming' }});
                return;
            }}

            if (isStreaming()) {{
                if (currentText !== lastText) {{
                    lastChangeTime = now;
                }}
                return;
            }}

            if (silenceDuration >= silenceMs && lastText.length > 0) {{
                cleanup();
                resolve({{ done: true, text: lastText, duration: now - startTime, msg_count: getMsgCount() }});
                return;
            }}

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
