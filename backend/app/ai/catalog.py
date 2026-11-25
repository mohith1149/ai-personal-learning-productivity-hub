"""Which models can be picked in the chat. Every provider that has a key is offered.

Model names go stale (Gemini's first default was retired), so for Groq and Gemini the list is asked of the provider itself and cached for a few
minutes. If that fails (offline, bad key) a short curated list is used instead, and the configured default is always included."""
import re
import time

import httpx

from app.config import Settings

LABELS = {"groq": "Groq (free)", "gemini": "Google Gemini (free tier)", "anthropic": "Anthropic Claude (paid)"}
CURATED = {
    "groq": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
    "gemini": ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-pro"],
    "anthropic": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
}
# Models in a provider's list that cannot chat with tools (speech, images, safety classifiers, embeddings...).
_NOT_CHAT = ("whisper", "tts", "guard", "orpheus", "embed", "safeguard", "image", "transcribe", "lyria", "robotics", "computer-use", "antigravity",
             "research", "nano-banana", "omni", "live", "audio", "gemma", "compound", "allam")
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")
_TTL = 600.0
_cache: dict[str, tuple[float, list[str]]] = {}


def valid_model_id(model: str) -> bool:
    return bool(MODEL_ID.match(model))


def _fetch(provider: str, key: str, http: httpx.Client) -> list[str]:
    if provider == "groq":
        r = http.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        ids = [m["id"] for m in r.json()["data"]]
    elif provider == "gemini":
        r = http.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200}, headers={"x-goog-api-key": key})
        r.raise_for_status()
        ids = [m["name"].removeprefix("models/") for m in r.json()["models"] if "generateContent" in m.get("supportedGenerationMethods", [])]
    else:
        raise ValueError(provider)
    return sorted(i for i in ids if valid_model_id(i) and not any(w in i.lower() for w in _NOT_CHAT))


def _models(provider: str, key: str, http: httpx.Client | None) -> list[str]:
    if provider not in ("groq", "gemini"):
        return CURATED.get(provider, [])
    hit = _cache.get(provider)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    try:
        live = _fetch(provider, key, http or httpx.Client(timeout=httpx.Timeout(8.0)))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return CURATED[provider]  # not cached, so the next visit tries again
    if not live:
        return CURATED[provider]
    _cache[provider] = (time.monotonic(), live)
    return live


def configured(settings: Settings) -> dict[str, tuple[str, str]]:
    """provider -> (api key, default model), for every provider that has a key. Empty when AI is off."""
    if settings.ai_provider == "none":
        return {}
    pairs = {"groq": (settings.groq_api_key, settings.groq_model), "gemini": (settings.gemini_api_key, settings.gemini_model),
             "anthropic": (settings.anthropic_api_key, settings.anthropic_model)}
    return {p: (k, m) for p, (k, m) in pairs.items() if k}


def options(settings: Settings, http: httpx.Client | None = None) -> list[dict]:
    """What the model menu shows: the default provider first, each with its models (its configured default always among them)."""
    keys = configured(settings)
    out = []
    for provider in sorted(keys, key=lambda p: p != settings.ai_provider):
        key, default = keys[provider]
        models = _models(provider, key, http)
        out.append({"provider": provider, "label": LABELS[provider], "default_model": default, "models": models if default in models else [default, *models]})
    return out
