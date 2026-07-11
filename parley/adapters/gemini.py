"""Google Gemini (gemini.google.com) site adapter.

Gemini is an Angular app with several quirks handled by the workflow layer:
  * The primary input is a Quill `rich-textarea` / contenteditable.
  * Response text lives in nested `response-container` / `structured-content-container`
    elements (the `model-response` host only exposes a "Gemini said" header).
  * After a response completes, the send button's inner <button> aria-label can
    stay stuck at "Stop response" indefinitely — the reliable recovery is a page
    reload (conversation history is preserved). Hence needs_reload_recovery=True.
"""

from .base import SiteAdapter


class GeminiAdapter(SiteAdapter):
    name = "gemini"
    url_patterns = ("gemini.google.com",)
    response_selectors = (
        "model-response",
        "response-container",
        "structured-content-container",
        "assistant-messages-primary .message-text",
    )
    input_selectors = ('[contenteditable="true"]', "rich-textarea")
    send_button_selectors = ("gem-icon-button.send-button button",)
    needs_reload_recovery = True
