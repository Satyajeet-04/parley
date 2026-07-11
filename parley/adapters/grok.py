"""xAI Grok (grok.com / x.com/i/grok) site adapter."""

from .base import SiteAdapter


class GrokAdapter(SiteAdapter):
    name = "grok"
    url_patterns = ("grok.com", "x.com/i/grok")
    response_selectors = ('[data-testid="grok-response"]', ".grok-response")
    input_selectors = ("textarea", '[contenteditable="true"]')
    send_button_selectors = ('button[aria-label*="Send"]',)
    needs_reload_recovery = False
