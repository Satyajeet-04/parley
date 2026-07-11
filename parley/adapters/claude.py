"""Anthropic Claude (claude.ai) site adapter."""

from .base import SiteAdapter


class ClaudeAdapter(SiteAdapter):
    name = "claude"
    url_patterns = ("claude.ai",)
    response_selectors = ("[data-is-streaming]", ".assistant-message")
    input_selectors = ('[contenteditable="true"]',)
    send_button_selectors = (
        'button[aria-label*="Send"]',
        'button[aria-label*="send"]',
    )
    needs_reload_recovery = False
