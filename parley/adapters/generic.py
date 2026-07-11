"""Generic fallback adapter for any website (no AI-specific assumptions).

Used when a tab's URL matches no known AI chat site. Response detection falls
back to the "longest visible text block" strategy in the universal JS.
"""

from .base import SiteAdapter


class GenericAdapter(SiteAdapter):
    name = "generic"
    url_patterns = ()
    response_selectors = ()
    input_selectors = ('[contenteditable="true"]', "textarea")
    send_button_selectors = ('button[type="submit"]',)
    needs_reload_recovery = False
