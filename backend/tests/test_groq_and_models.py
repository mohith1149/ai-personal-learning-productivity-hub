"""Groq adapter, the model catalog and picking a model per request. All against fake HTTP: no network, no key, never run live here."""
import json

import httpx
import pytest

from app.ai import catalog, tools
from app.ai.groq import GroqProvider
from app.ai.providers import ScriptedProvider, get_provider
from app.ai.types import LLMResponse, ProviderError
from app.config import Settings
from app.routers import assistant as router

KEY = "gsk_test-key-NOT-REAL"
USER_MSG = {"role": "user", "content": [{"type": "text", "text": "What is on today?"}]}
OK = {"choices": [{"message": {"content": "Hi"}, "finish_reason": "stop"}]}


def groq(status=200, body=None, seen=None, raise_exc=None, text=None):
    def handler(req: httpx.Request):
        if raise_exc:
            raise raise_exc
        if seen is not None:
            seen.append(req)
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=body if body is not None else OK)
    return GroqProvider(KEY, "llama-test", httpx.Client(transport=httpx.MockTransport(handler)))


def complete(p, messages=None, tools_=None):
    return p.complete(system="Be brief.", messages=messages or [USER_MSG], tools=tools_ or [])


# ------------------------------ the adapter ------------------------------


def test_plain_reply_and_request_shape():
    seen: list = []
    r = complete(groq(seen=seen))
    assert (r.text, r.tool_calls, r.stop_reason) == ("Hi", [], "end_turn")
    req, body = seen[0], json.loads(seen[0].content)
    assert req.url.path == "/openai/v1/chat/completions" and KEY not in str(req.url) and req.headers["authorization"] == f"Bearer {KEY}"
    assert body["model"] == "llama-test" and "tools" not in body
    assert body["messages"] == [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "What is on today?"}]


def test_tool_call_arguments_are_parsed_from_the_json_string():
    body = {"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "get_plan", "arguments": "{\"day\": \"2026-12-02\"}"}},
        {"id": "c2", "type": "function", "function": {"name": "get_today_tasks", "arguments": ""}}]}, "finish_reason": "tool_calls"}]}
    r = complete(groq(body=body))
    assert r.stop_reason == "tool_use" and r.text == ""
    assert [(c.id, c.name, c.input) for c in r.tool_calls] == [("c1", "get_plan", {"day": "2026-12-02"}), ("c2", "get_today_tasks", {})]


def test_tool_history_is_translated_to_assistant_tool_calls_and_tool_messages():
    seen: list = []
    msgs = [USER_MSG,
            {"role": "assistant", "content": [{"type": "text", "text": "Looking."}, {"type": "tool_use", "id": "c1", "name": "get_plan", "input": {"day": "x"}, "meta": {"thoughtSignature": "S"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "{\"items\": []}", "is_error": False}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "c2", "name": "create_task", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c2", "content": "boom", "is_error": True}]}]
    complete(groq(seen=seen), msgs)
    m = json.loads(seen[0].content)["messages"]
    assert m[2] == {"role": "assistant", "content": "Looking.", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "get_plan", "arguments": "{\"day\": \"x\"}"}}]}
    assert m[3] == {"role": "tool", "tool_call_id": "c1", "content": "{\"items\": []}"}
    assert m[4]["content"] is None and m[4]["tool_calls"][0]["id"] == "c2"          # an assistant turn with only a tool call has no text
    assert m[5] == {"role": "tool", "tool_call_id": "c2", "content": "Error: boom"}
    assert "meta" not in json.dumps(m) and "thoughtSignature" not in json.dumps(m)  # other providers' echo-back data is never sent


def test_every_real_tool_schema_is_plain_json_schema():
    seen: list = []
    complete(groq(seen=seen), tools_=tools.specs())
    body = json.loads(seen[0].content)
    assert body["tool_choice"] == "auto" and len(body["tools"]) == len(tools.TOOLS)
    banned = {"additionalProperties", "$defs", "$ref", "anyOf", "default", "title", "nullable"}

    def walk(o, in_properties=False):
        if isinstance(o, dict):
            if not in_properties:
                assert not (set(o) & banned), set(o) & banned
            for k, v in o.items():
                walk(v, in_properties=(k == "properties" and not in_properties))
        elif isinstance(o, list):
            [walk(v) for v in o]

    walk([t["function"]["parameters"] for t in body["tools"]])
    by_name = {t["function"]["name"]: t["function"] for t in body["tools"]}
    assert by_name["get_today_tasks"]["parameters"] == {"type": "object", "properties": {}}      # no-argument tool still has a valid object schema
    assert by_name["create_project_challenge"]["parameters"]["properties"]["new_project"]["properties"]["title"]["type"] == "string"


@pytest.mark.parametrize("status, text, fragment", [
    (401, "", "GROQ_API_KEY"), (403, "", "GROQ_API_KEY"), (404, "", "another model"), (413, "", "too large"), (429, "", "rate limit"),
    (400, '{"error": {"code": "tool_use_failed"}}', "malformed tool call"), (400, "nope", "another model"), (500, "", "HTTP 500")])
def test_http_errors_have_safe_messages(status, text, fragment):
    with pytest.raises(ProviderError) as e:
        complete(groq(status, text=text or f"secret detail {KEY}"))
    assert fragment in str(e.value) and KEY not in str(e.value) and "secret detail" not in str(e.value)


def test_network_failure_unreadable_answer_and_truncation():
    with pytest.raises(ProviderError, match="Couldn't reach") as e:
        complete(groq(raise_exc=httpx.ConnectError(f"dns failure for {KEY}")))
    assert KEY not in str(e.value)
    for bad in ({"choices": []}, {"nothing": 1}, {"choices": [{"message": {"tool_calls": [{"id": "a", "function": {"name": "n", "arguments": "{not json"}}]}}]}):
        with pytest.raises(ProviderError, match="couldn't be read"):
            complete(groq(body=bad))
    assert complete(groq(body={"choices": [{"message": {"content": "cut"}, "finish_reason": "length"}]})).stop_reason == "max_tokens"


# ------------------------------ choosing a model ------------------------------


def settings(**kw):
    return Settings(secret_key="x" * 40, _env_file=None, **kw)


def test_groq_is_selected_only_with_the_setting_and_a_key():
    assert get_provider(settings(ai_provider="groq", groq_api_key=KEY)).name == "groq"
    assert get_provider(settings(ai_provider="groq")) is None                      # key missing
    assert get_provider(settings(ai_provider="none", groq_api_key=KEY)) is None    # a key alone never turns AI on
    assert get_provider(settings(ai_provider="groq", groq_api_key=KEY)).model == "openai/gpt-oss-120b"


def test_the_menu_pick_overrides_provider_and_model_but_only_for_providers_with_a_key():
    s = settings(ai_provider="groq", groq_api_key=KEY, gemini_api_key="g")
    p = get_provider(s, "groq", "openai/gpt-oss-120b")
    assert (p.name, p.model) == ("groq", "openai/gpt-oss-120b")
    assert get_provider(s, "gemini", "gemini-x").name == "gemini"
    assert get_provider(s, "anthropic", "claude-x") is None                        # no key for it
    assert get_provider(s, None, "llama-3.1-8b-instant").name == "groq"            # model alone = default provider
    for bad in ("../../x", "a b", "", "x" * 101, "m;rm"):
        with pytest.raises(ValueError):
            get_provider(s, "groq", bad)


# ------------------------------ the catalog ------------------------------


@pytest.fixture(autouse=True)
def _fresh_cache():
    catalog._cache.clear()


def fake_http(groq_ids=None, fail=False):
    def handler(req: httpx.Request):
        if fail:
            return httpx.Response(500)
        if "groq" in req.url.host:
            return httpx.Response(200, json={"data": [{"id": i} for i in groq_ids]})
        return httpx.Response(200, json={"models": [{"name": "models/gemini-a", "supportedGenerationMethods": ["generateContent"]},
                                                      {"name": "models/embed-1", "supportedGenerationMethods": ["embedContent"]},
                                                      {"name": "models/gemini-a-tts", "supportedGenerationMethods": ["generateContent"]}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_live_model_lists_are_filtered_to_chat_models():
    s = settings(ai_provider="groq", groq_api_key=KEY, gemini_api_key="g")
    out = catalog.options(s, fake_http(["whisper-large-v3", "openai/gpt-oss-120b", "playai-tts", "openai/gpt-oss-20b", "meta-llama/llama-guard-4-12b"]))
    assert [o["provider"] for o in out] == ["groq", "gemini"]                      # the default provider comes first
    assert out[0]["models"] == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"] and out[1]["models"] == ["gemini-3.5-flash", "gemini-a"]  # default always included


def test_when_the_list_cannot_be_fetched_the_curated_list_is_used_and_not_cached():
    s = settings(ai_provider="groq", groq_api_key=KEY)
    out = catalog.options(s, fake_http(fail=True))
    assert out[0]["models"] == catalog.CURATED["groq"] and "groq" not in catalog._cache
    assert catalog.options(s, fake_http(["only-model"]))[0]["models"] == ["openai/gpt-oss-120b", "only-model"]


def test_nothing_is_offered_while_ai_is_off_and_only_providers_with_keys_are_listed():
    assert catalog.options(settings(groq_api_key=KEY)) == []
    assert [o["provider"] for o in catalog.options(settings(ai_provider="anthropic", anthropic_api_key="a"))] == ["anthropic"]


# ------------------------------ over HTTP ------------------------------

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Ada", "timezone": "Asia/Kolkata"}


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def test_models_endpoint(c, monkeypatch):
    assert c.get("/api/ai/models").json() == {"default_provider": None, "providers": []}      # AI off in tests
    opts = [{"provider": "groq", "label": "Groq (free)", "default_model": "m1", "models": ["m1", "m2"]}]
    monkeypatch.setattr(router, "get_model_options", lambda: opts)
    monkeypatch.setattr(router, "get_settings", lambda: settings(ai_provider="groq", groq_api_key=KEY))
    assert c.get("/api/ai/models").json() == {"default_provider": "groq", "providers": opts}


def test_the_chosen_model_reaches_chat_check_and_autofill(c, monkeypatch):
    asked: list = []

    def fake(provider=None, model=None):
        asked.append((provider, model))
        return ScriptedProvider([LLMResponse(text="ok")] * 3)

    monkeypatch.setattr(router, "current_provider", fake)
    assert c.post("/api/ai/chat", json={"message": "hi", "provider": "groq", "model": "openai/gpt-oss-20b"}).status_code == 200
    assert c.post("/api/ai/check", json={"provider": "gemini", "model": "gemini-3.5-flash"}).status_code == 200
    assert c.post("/api/ai/check").status_code == 200                                         # no body = defaults
    assert asked == [("groq", "openai/gpt-oss-20b"), ("gemini", "gemini-3.5-flash"), (None, None)]


def test_a_bad_pick_is_rejected(c):
    assert c.post("/api/ai/chat", json={"message": "hi", "provider": "skynet"}).status_code == 422
    assert c.post("/api/ai/chat", json={"message": "hi", "model": "x" * 101}).status_code == 422
    assert c.post("/api/ai/chat", json={"message": "hi", "extra": 1}).status_code == 422
    assert c.post("/api/ai/check", json={"model": "../../etc"}).status_code in (422, 503)    # invalid name (422) or AI off (503), never a call out
