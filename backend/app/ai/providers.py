"""Providers: the interface, an offline scripted provider (tests, demos), an Anthropic adapter and a Gemini adapter (app/ai/gemini.py).

The Anthropic adapter is verified here only against a stub client (request and response translation). It has NOT been called live; that is
Phase 6, which needs the key in backend/.env. Nothing in the app claims otherwise."""
from collections.abc import Callable

from app.ai.types import LLMResponse, ProviderError, ToolCall
from app.config import Settings


class ScriptedProvider:
    """Returns pre-written responses in order (a callable may build one from the request). Used by tests; it records what it was asked."""

    name = "scripted"
    model = "scripted"

    def __init__(self, responses: list[LLMResponse | Callable[[dict], LLMResponse]]):
        self._responses = list(responses)
        self.requests: list[dict] = []

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.requests.append({"system": system, "messages": messages, "tools": tools})
        if not self._responses:
            raise ProviderError("The scripted provider has no more responses")
        r = self._responses.pop(0)
        return r(self.requests[-1]) if callable(r) else r


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, client=None, max_tokens: int = 2048):
        self.model = model
        self.max_tokens = max_tokens
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self._client = client

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        try:
            resp = self._client.messages.create(model=self.model, max_tokens=self.max_tokens, system=system, messages=messages, tools=tools)
        except Exception as exc:  # the SDK's errors can include request details; show only the class of problem
            raise ProviderError(f"The Anthropic API request failed ({type(exc).__name__})") from None
        text, calls = [], []
        for block in resp.content:
            if block.type == "text":
                text.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))
        return LLMResponse(text="".join(text), tool_calls=calls, stop_reason=resp.stop_reason or "end_turn")


def get_provider(settings: Settings):
    """The configured provider, or None when AI is off (the default) or its key is missing."""
    if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if settings.ai_provider == "gemini" and settings.gemini_api_key:
        from app.ai.gemini import GeminiProvider

        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    return None
