"""Provider-neutral message and response types.

Messages are stored and exchanged as a list of {role, content: [blocks]} where a block is one of
  {"type": "text", "text": ...}
  {"type": "tool_use", "id": ..., "name": ..., "input": {...}}      (assistant asks for a tool)
  {"type": "tool_result", "tool_use_id": ..., "content": "...", "is_error": bool}   (we answer, role "user")
A provider adapter translates this to and from its own API."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict
    meta: dict | None = None   # provider-specific data that must be echoed back (Gemini's thoughtSignature); stored in the tool_use block


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


class ProviderError(Exception):
    """The provider could not answer (network, auth, rate limit...). The message is safe to show: it never contains the API key."""


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse: ...
