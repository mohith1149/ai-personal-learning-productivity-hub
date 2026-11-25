"""Google Gemini adapter (free tier available), over the plain REST API with httpx, so no extra package is needed.

Translates our provider-neutral messages (see app/ai/types.py) to Gemini's `generateContent` format and back.
Verified here only against a fake HTTP transport (request and response translation). It has NOT been called live until the owner adds a key.

Security: the key goes in the `x-goog-api-key` HEADER, never the URL (httpx logs URLs). Error messages are written here; raw Google error text is
never passed on. Note for the owner: on the free tier Google may use prompts to improve its products, so don't put private data into the assistant.

Known limits: we make up our own call ids (`call_N`) and map results back by name. Gemini 3 models attach a `thoughtSignature` to each function
call and reject the next turn (400) if it isn't sent back, so it is kept in the tool_use block's `meta` and echoed. Found by testing live."""
from urllib.parse import quote

import httpx

from app.ai.types import LLMResponse, ProviderError, ToolCall

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Gemini accepts only a subset of JSON Schema. Everything else is dropped (our own validation on the server still enforces it).
_KEEP = {"type", "description", "enum", "items", "properties", "required", "nullable", "minimum", "maximum"}


def to_gemini_schema(schema: dict, defs: dict | None = None) -> dict:
    """Make a pydantic JSON schema acceptable to Gemini: inline $ref, turn anyOf [X, null] into nullable X, keep only supported keys."""
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return to_gemini_schema(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        options = [o for o in schema["anyOf"] if o.get("type") != "null"]
        out = to_gemini_schema(options[0], defs) if options else {"type": "string"}
        if len(options) != len(schema["anyOf"]):
            out["nullable"] = True
        if "description" in schema:
            out.setdefault("description", schema["description"])
        return out
    out: dict = {}
    for key, value in schema.items():
        if key not in _KEEP:
            continue
        if key == "properties":
            out[key] = {name: to_gemini_schema(sub, defs) for name, sub in value.items()}
        elif key == "items":
            out[key] = to_gemini_schema(value, defs)
        else:
            out[key] = value
    return out


def _declarations(tools: list[dict]) -> list[dict]:
    decls = []
    for t in tools:
        d = {"name": t["name"], "description": t["description"]}
        params = to_gemini_schema(t["input_schema"])
        if params.get("properties"):  # Gemini rejects an object with no properties, so a no-argument tool omits `parameters`
            d["parameters"] = params
        decls.append(d)
    return decls


def _contents(messages: list[dict]) -> list[dict]:
    names: dict[str, str] = {}  # tool_use id -> tool name, so a tool_result can be sent back as a functionResponse
    out = []
    for m in messages:
        parts = []
        for b in m["content"]:
            if b["type"] == "text":
                parts.append({"text": b["text"]})
            elif b["type"] == "tool_use":
                names[b["id"]] = b["name"]
                part = {"functionCall": {"name": b["name"], "args": b["input"]}}
                if (b.get("meta") or {}).get("thoughtSignature"):  # Gemini 3 requires this to be sent back, or the next turn is a 400
                    part["thoughtSignature"] = b["meta"]["thoughtSignature"]
                parts.append(part)
            elif b["type"] == "tool_result":
                key = "error" if b.get("is_error") else "result"
                parts.append({"functionResponse": {"name": names.get(b["tool_use_id"], "tool"), "response": {key: b["content"]}}})
        if parts:
            out.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
    return out


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, http: httpx.Client | None = None, max_tokens: int = 2048):
        self.model = model
        self.max_tokens = max_tokens
        self._key = api_key
        self._http = http or httpx.Client(timeout=httpx.Timeout(60.0))

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        body: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": _contents(messages),
            "generationConfig": {"maxOutputTokens": self.max_tokens, "thinkingConfig": {"thinkingBudget": 0}},
        }
        if tools:
            body["tools"] = [{"functionDeclarations": _declarations(tools)}]
        try:
            r = self._http.post(f"{API_BASE}/models/{quote(self.model, safe='')}:generateContent", json=body, headers={"x-goog-api-key": self._key})
        except httpx.HTTPError:
            raise ProviderError("Couldn't reach the Gemini API. Check your connection") from None
        if r.status_code != 200:
            raise ProviderError(self._explain(r.status_code))
        try:
            data = r.json()
            cand = (data.get("candidates") or [None])[0]
            if cand is None:
                raise ProviderError("Gemini returned no answer (it may have been blocked by its safety filter). Try rephrasing")
            parts = (cand.get("content") or {}).get("parts") or []
        except ValueError:
            raise ProviderError("Gemini returned a response that couldn't be read") from None
        text, calls = [], []
        for p in parts:
            if "text" in p:
                text.append(p["text"])
            elif "functionCall" in p:
                fc = p["functionCall"]
                calls.append(ToolCall(id=f"call_{len(calls) + 1}", name=fc["name"], input=dict(fc.get("args") or {}),
                                      meta={"thoughtSignature": p["thoughtSignature"]} if p.get("thoughtSignature") else None))
        reason = cand.get("finishReason", "STOP")
        return LLMResponse(text="".join(text), tool_calls=calls, stop_reason="tool_use" if calls else ("max_tokens" if reason == "MAX_TOKENS" else "end_turn"))

    @staticmethod
    def _explain(status: int) -> str:
        if status in (400, 403):
            return "The Gemini API rejected the request. Check GEMINI_API_KEY and GEMINI_MODEL in backend/.env"
        if status == 404:
            return "Gemini doesn't know that model. Check GEMINI_MODEL in backend/.env"
        if status == 429:
            return "Gemini's free-tier limit was reached. Wait a minute and try again"
        return f"The Gemini API had a problem (HTTP {status}). Try again shortly"
