"""Groq adapter (free tier, much higher request limits than Gemini's), over its OpenAI-compatible REST API with httpx: no extra package.

Translates our provider-neutral messages (app/ai/types.py) to the chat-completions format and back. Tool results are separate `role: "tool"`
messages there. Not yet called live with a real key: only verified against a fake HTTP transport.

Security: the key goes in the Authorization header, never the URL. Error messages are written here; raw provider error text is never passed on.
Note for the owner: on the free tier Groq may keep prompts, so don't put private data into the assistant."""
import json

import httpx

from app.ai.gemini import to_gemini_schema
from app.ai.types import LLMResponse, ProviderError, ToolCall

API_BASE = "https://api.groq.com/openai/v1"


def _schema(schema: dict) -> dict:
    """A plain JSON schema: $ref inlined and anyOf-with-null collapsed (shared with Gemini), minus Gemini's own `nullable` marker."""

    def strip(o):
        if isinstance(o, dict):  # only the boolean marker goes; a FIELD that happens to be called "nullable" has a dict value and stays
            return {k: strip(v) for k, v in o.items() if not (k == "nullable" and isinstance(v, bool))}
        return o

    return strip(to_gemini_schema(schema))


def _tools(tools: list[dict]) -> list[dict]:
    out = []
    for t in tools:
        params = _schema(t["input_schema"])
        params.setdefault("type", "object")
        params.setdefault("properties", {})
        out.append({"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": params}})
    return out


def _messages(system: str, messages: list[dict]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        text = "".join(b["text"] for b in m["content"] if b["type"] == "text")
        if m["role"] == "assistant":
            calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                     for b in m["content"] if b["type"] == "tool_use"]
            msg: dict = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        for b in m["content"]:  # tool results come first: each answers the assistant's tool_calls
            if b["type"] == "tool_result":
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"] if not b.get("is_error") else f"Error: {b['content']}"})
        if text:
            out.append({"role": "user", "content": text})
    return out


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, http: httpx.Client | None = None, max_tokens: int = 2048):
        self.model = model
        self.max_tokens = max_tokens
        self._key = api_key
        self._http = http or httpx.Client(timeout=httpx.Timeout(60.0))

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        body: dict = {"model": self.model, "messages": _messages(system, messages), "max_tokens": self.max_tokens, "temperature": 0.3}
        if tools:
            body["tools"] = _tools(tools)
            body["tool_choice"] = "auto"
        try:
            r = self._http.post(f"{API_BASE}/chat/completions", json=body, headers={"Authorization": f"Bearer {self._key}"})
        except httpx.HTTPError:
            raise ProviderError("Couldn't reach the Groq API. Check your connection") from None
        if r.status_code != 200:
            raise ProviderError(self._explain(r))
        try:
            choice = r.json()["choices"][0]
            msg = choice["message"]
            calls = []
            for tc in msg.get("tool_calls") or []:
                raw = (tc.get("function") or {}).get("arguments") or "{}"
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
                calls.append(ToolCall(id=tc["id"], name=tc["function"]["name"], input=args if isinstance(args, dict) else {}))
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("Groq returned a response that couldn't be read. Try again, or pick another model") from None
        reason = choice.get("finish_reason")
        return LLMResponse(text=msg.get("content") or "", tool_calls=calls, stop_reason="tool_use" if calls else ("max_tokens" if reason == "length" else "end_turn"))

    @staticmethod
    def _explain(r: httpx.Response) -> str:
        status = r.status_code
        if status == 401:
            return "Groq rejected the API key. Check GROQ_API_KEY in backend/.env"
        if status in (403,):
            return "Groq refused the request (this key or region may not be allowed). Check GROQ_API_KEY in backend/.env"
        if status == 404:
            return "Groq doesn't know that model. Pick another model from the menu"
        if status == 413:
            return "The request was too large for this Groq model. Start a new chat"
        if status == 429:
            return "Groq's rate limit was reached. Wait a minute and try again, or pick another model"
        if status == 400 and "tool_use_failed" in r.text:
            return "This model made a malformed tool call. Try again, or pick another model (larger models do this less)"
        if status == 400:
            return "Groq rejected the request. Pick another model from the menu"
        return f"The Groq API had a problem (HTTP {status}). Try again shortly"
