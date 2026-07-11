"""
parley.adapters.base - Site adapter interface.

A SiteAdapter describes how to talk to one AI chat UI: which selectors identify
its responses / input / send button, and whether it needs special recovery
(e.g. Gemini's stuck-button reload). Response *detection* itself is handled by
the universal strategies in `parley.adapters.js`; adapters carry the metadata
and hints that the workflow layer uses to pick behaviour.

To add support for a new site, subclass SiteAdapter, set `name`,
`url_patterns` and selectors, and register it in `parley.adapters.__init__`.
"""


class SiteAdapter:
    name = "generic"
    # Substrings matched against the tab URL to auto-detect the site.
    url_patterns = ()
    # Selectors (informational + used by generic helpers / future extension).
    response_selectors = ()
    input_selectors = ('[contenteditable="true"]', "textarea")
    send_button_selectors = ()
    # Gemini leaves its send button stuck after a response; needs a page reload.
    needs_reload_recovery = False

    @classmethod
    def matches(cls, url):
        url = (url or "").lower()
        return any(p in url for p in cls.url_patterns)

    def __repr__(self):
        return f"<SiteAdapter {self.name}>"
