"""
parley.workflows - AI chat workflow layer.

Built on top of `parley.core` (CDP engine) and `parley.adapters` (site
knowledge). Provides the higher-level operations that make Parley useful for
AI automation:

  * read_response(tab)         - extract the latest AI answer
  * robust_send(...)           - reliably type + submit a prompt (handles
                                 Gemini stuck-button reload + input clearing)
  * send_and_wait(tab, text)   - send, then wait for the full NEW response
  * wait_stream(tab)           - wait for an in-flight response to finish
  * bridge(from, to, rounds)   - relay a conversation between two AIs
  * poll(tab)                  - block until new content appears

Every function returns plain dicts/values; printing/formatting is the CLI's job.
"""

import time

from . import core
from .core import cdp_connect, cdp_send, cdp_send_with_retry
from .adapters import detect
from .adapters.js import (
    UNIVERSAL_GET_RESPONSE,
    UNIVERSAL_GET_MSG_COUNT,
    FOCUS_AND_CLEAR_JS,
    SEND_CLICK_JS,
    REFOCUS_JS,
    GEMINI_STUCK_STATE_JS,
    make_mutation_observer_js,
)


def read_response(tab_id):
    """Return the latest AI response object {text, source, hasStreaming, ...}."""
    val = core.evaluate(tab_id, UNIVERSAL_GET_RESPONSE)
    return val


def robust_send(ws, tab_id, text):
    """Shared send routine used by send() and send_and_wait().

    Handles: (1) reloading to recover from Gemini's stuck 'Stop response' state,
    (2) clearing accumulated input text, (3) inserting text via CDP, (4) clicking
    send with Enter-key fallback. Returns (result_dict, ws) - ws may be a new
    connection if a reload happened.
    """
    reloaded = False
    # Step 0: Detect Gemini stuck state; reload to reset the Angular UI if needed.
    stuck_result = cdp_send_with_retry(ws, "Runtime.evaluate", {
        "expression": GEMINI_STUCK_STATE_JS,
        "returnByValue": True,
    }, tab_id=tab_id)
    stuck_val = stuck_result.get("result", {}).get("value", {}) if "result" in stuck_result else {}
    if stuck_val.get("stuck"):
        cdp_send_with_retry(ws, "Page.reload", {}, tab_id=tab_id)
        try:
            ws.close()
        except Exception:
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


def send(tab_id, text):
    """Type + submit a prompt (no wait). Returns a result dict."""
    ws = cdp_connect(tab_id)
    if not ws:
        return {"error": "cannot connect to tab"}
    try:
        result, ws = robust_send(ws, tab_id, text)
        result["ok"] = True
        return result
    finally:
        try:
            ws.close()
        except Exception:
            pass


def wait_stream(tab_id, timeout_ms=60000, silence_ms=1500):
    """Wait for an AI response to finish streaming using MutationObserver."""
    ws = cdp_connect(tab_id)
    if not ws:
        return {"error": "cannot connect to tab"}
    try:
        count_result = cdp_send(ws, "Runtime.evaluate", {
            "expression": UNIVERSAL_GET_MSG_COUNT,
            "returnByValue": True,
        })
        initial_count = 0
        if "result" in count_result and "value" in count_result["result"]:
            initial_count = count_result["result"]["value"].get("count", 0)

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

        if initial_text and not has_streaming and not has_stop:
            return {
                "status": "complete",
                "text": initial_text,
                "msg_count": initial_count_val,
                "duration_ms": 0,
            }

        # initial_msg_count=0 skips Phase 1 count tracking (unreliable on Gemini).
        observer_js = make_mutation_observer_js(timeout_ms, silence_ms, initial_msg_count=0)
        result = cdp_send(ws, "Runtime.evaluate", {
            "expression": observer_js,
            "returnByValue": True,
            "awaitPromise": True,
        }, timeout=timeout_ms // 1000 + 5)

        if "result" in result:
            val = result["result"].get("value", {})
            return {
                "status": "complete" if val.get("done") else "timeout",
                "text": val.get("text", initial_text),
                "duration_ms": val.get("duration", 0),
            }
        return {"status": "error", "text": initial_text, "error": str(result)}
    finally:
        try:
            ws.close()
        except Exception:
            pass


def poll(tab_id, interval_ms=2000, max_iters=60):
    """Poll for new chat content - returns text when it changes and settles."""
    ws = cdp_connect(tab_id)
    if not ws:
        return {"error": "cannot connect to tab"}
    try:
        last_hash = ""
        for _ in range(max_iters):
            result = cdp_send(ws, "Runtime.evaluate", {
                "expression": UNIVERSAL_GET_RESPONSE,
                "returnByValue": True,
            })
            if "result" in result and "value" in result["result"]:
                current = result["result"]["value"]
                current_hash = str(current.get("text", ""))[-200:]
                if current_hash != last_hash and not current.get("hasStreaming") and not current.get("hasStopButton"):
                    return current
                if current.get("hasStreaming") or current.get("hasStopButton"):
                    time.sleep(1)
                    continue
            time.sleep(interval_ms / 1000)
        return {"error": "poll timeout", "last": last_hash}
    finally:
        try:
            ws.close()
        except Exception:
            pass


def send_and_wait(tab_id, text, wait_timeout_ms=60000, silence_ms=1500):
    """Send text to a tab and wait for the full NEW response. Returns a result dict."""
    result = {}

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
        except Exception:
            pass

    result["pre_msg_count"] = pre_count

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
        except Exception:
            pass

    time.sleep(1)  # Brief pause for response to start

    ws_wait = cdp_connect(tab_id)
    if not ws_wait:
        return {**result, "error": "cannot connect for wait"}

    try:
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

            check = cdp_send(ws_wait, "Runtime.evaluate", {
                "expression": UNIVERSAL_GET_RESPONSE,
                "returnByValue": True,
            })
            if "result" in check and "value" in check["result"]:
                val = check["result"]["value"]
                if val.get("hasStreaming") or val.get("hasStopButton"):
                    found_new = True
                    break
                new_text = val.get("text", "")
                if new_text and new_text.strip() != prev_text.strip():
                    found_new = True
                    break

            time.sleep(0.5)

        # Wait for streaming to finish. initial_msg_count=0 skips Phase 1;
        # prev_text makes the observer ignore the pre-send response.
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
        except Exception:
            pass

    return result


def bridge(tab_from, tab_to, rounds=3):
    """Relay a conversation: read from tab_from, send to tab_to, wait, repeat."""
    results = []

    for i in range(rounds):
        round_result = {"round": i}

        ws_from = cdp_connect(tab_from)
        if not ws_from:
            round_result["error"] = "cannot connect to source"
            results.append(round_result)
            break

        try:
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
            except Exception:
                pass

        round_result_send = send_and_wait(tab_to, source_text[:8000])
        round_result.update(round_result_send)
        results.append(round_result)

    return results
