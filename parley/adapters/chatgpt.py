"""ChatGPT (chatgpt.com / chat.openai.com) site adapter."""

from .base import SiteAdapter


class ChatGPTAdapter(SiteAdapter):
    name = "chatgpt"
    url_patterns = ("chatgpt.com", "chat.openai.com")
    response_selectors = (
        '[data-message-author-role="assistant"]',
        ".agent-turn",
        ".markdown",
    )
    input_selectors = ("#prompt-textarea", '[contenteditable="true"]')
    send_button_selectors = ('button[data-testid="send-button"]',)
    needs_reload_recovery = False
