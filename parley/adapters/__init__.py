"""
parley.adapters - Site adapter registry + auto-detection.

    from parley.adapters import detect
    adapter = detect("https://gemini.google.com/app")  # -> GeminiAdapter()
"""

from .base import SiteAdapter
from .chatgpt import ChatGPTAdapter
from .gemini import GeminiAdapter
from .claude import ClaudeAdapter
from .grok import GrokAdapter
from .generic import GenericAdapter

# Order matters: most specific first. Generic is the fallback.
REGISTRY = [
    ChatGPTAdapter,
    GeminiAdapter,
    ClaudeAdapter,
    GrokAdapter,
]

_GENERIC = GenericAdapter()


def detect(url):
    """Return a SiteAdapter instance for the given tab URL (GenericAdapter fallback)."""
    for cls in REGISTRY:
        if cls.matches(url):
            return cls()
    return _GENERIC


def all_adapters():
    """Return one instance of every registered adapter (including generic)."""
    return [cls() for cls in REGISTRY] + [_GENERIC]


__all__ = [
    "SiteAdapter",
    "ChatGPTAdapter",
    "GeminiAdapter",
    "ClaudeAdapter",
    "GrokAdapter",
    "GenericAdapter",
    "REGISTRY",
    "detect",
    "all_adapters",
]
