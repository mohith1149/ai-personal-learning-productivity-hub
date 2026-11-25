"""Gemini adapter: request and response translation against a fake HTTP transport. No network, no key, never run live here."""
import json

import httpx
import pytest

from app.ai import tools
from app.ai.gemini import GeminiProvider, to_gemini_schema
from app.ai.providers import get_provider
from app.ai.types import ProviderError
from app.config import Settings

KEY = "AIza-test-key-NOT-REAL"
USER_MSG = {"role": "user", "content": [{"type": "text", "text": "What is on today?"}]}


def provider(status=200, body=None, seen=None, raise_exc=None):
    def handler(req: httpx.Request):
        if raise_exc:
            raise raise_exc
        if seen is not None:
            seen.append(req)
        return httpx.Response(status, json=body if body is not None else {"candidates": [{"content": {"parts": [{"text": "Hi"}]}, "finishReason": "STOP"}]})
    return GeminiProvider(KEY, "gemini-test", httpx.Client(transport=httpx.MockTransport(handler)))


def test_plain_text_reply_and_request_shape():
    seen: list = []
    r = provider(seen=seen).complete(system="Be brief.", messages=[USER_MSG], tools=[])
    assert (r.text, r.tool_calls, r.stop_reason) == ("Hi", [], "end_turn")
    req = seen[0]
    body = json.loads(req.content)
    assert req.url.path == "/v1beta/models/gemini-test:generateContent" and KEY not in str(req.url)     # key never in the URL
    assert req.headers["x-goog-api-key"] == KEY
    assert body["systemInstruction"]["parts"][0]["text"] == "Be brief." and "tools" not in body
    assert body["contents"] == [{"role": "user", "parts": [{"text": "What is on today?"}]}]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


def test_function_call_becomes_a_tool_call_with_a_generated_id():
    body = {"candidates": [{"content": {"parts": [{"text": "Let me look."}, {"functionCall": {"name": "get_plan", "args": {"day": "2026-12-02"}}},
                                                 {"functionCall": {"name": "get_today_tasks"}}]}, "finishReason": "STOP"}]}
    r = provider(body=body).complete(system="s", messages=[USER_MSG], tools=[])
    assert r.text == "Let me look." and r.stop_reason == "tool_use"
    assert [(c.id, c.name, c.input) for c in r.tool_calls] == [("call_1", "get_plan", {"day": "2026-12-02"}), ("call_2", "get_today_tasks", {})]


def test_tool_history_is_translated_both_ways():
    seen: list = []
    msgs = [USER_MSG,
            {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "get_plan", "input": {"day": "2026-12-02"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "{\"items\": []}", "is_error": False}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_9", "content": "boom", "is_error": True}]}]
    provider(seen=seen).complete(system="s", messages=msgs, tools=[])
    c = json.loads(seen[0].content)["contents"]
    assert c[1] == {"role": "model", "parts": [{"functionCall": {"name": "get_plan", "args": {"day": "2026-12-02"}}}]}
    assert c[2]["parts"][0]["functionResponse"] == {"name": "get_plan", "response": {"result": "{\"items\": []}"}}
    assert c[3]["parts"][0]["functionResponse"]["response"] == {"error": "boom"}


def test_every_real_tool_schema_is_converted_to_gemini_safe_json():
    seen: list = []
    provider(seen=seen).complete(system="s", messages=[USER_MSG], tools=tools.specs())
    decls = json.loads(seen[0].content)["tools"][0]["functionDeclarations"]
    assert len(decls) == len(tools.TOOLS)
    banned = {"additionalProperties", "$defs", "$ref", "anyOf", "default", "title", "format", "pattern", "maxLength", "minLength"}

    def walk(o, is_properties=False):
        if isinstance(o, dict):
            if not is_properties:  # in a `properties` map the keys are field names (a field may legitimately be called "title")
                assert not (set(o) & banned), set(o) & banned
            for k, v in o.items():
                walk(v, is_properties=(k == "properties" and not is_properties))
        elif isinstance(o, list):
            [walk(v) for v in o]
    walk(decls)
    by_name = {d["name"]: d for d in decls}
    assert "parameters" not in by_name["get_today_tasks"]                                  # no-argument tool: no empty object
    assert by_name["create_project_challenge"]["parameters"]["properties"]["new_project"]["properties"]["title"]["type"] == "string"   # $ref inlined


def test_schema_conversion_details():
    s = {"type": "object", "properties": {"a": {"anyOf": [{"type": "integer", "minimum": 1}, {"type": "null"}], "default": None},
                                          "b": {"$ref": "#/$defs/B"}}, "$defs": {"B": {"type": "string", "enum": ["x", "y"], "title": "B"}}, "additionalProperties": False}
    assert to_gemini_schema(s) == {"type": "object", "properties": {"a": {"type": "integer", "minimum": 1, "nullable": True}, "b": {"type": "string", "enum": ["x", "y"]}}}


@pytest.mark.parametrize("status, fragment", [(400, "GEMINI_API_KEY"), (403, "GEMINI_API_KEY"), (404, "GEMINI_MODEL"), (429, "limit"), (500, "HTTP 500")])
def test_http_errors_have_safe_messages(status, fragment):
    with pytest.raises(ProviderError) as e:
        provider(status, {"error": {"message": f"secret detail {KEY}"}}).complete(system="s", messages=[USER_MSG], tools=[])
    assert fragment in str(e.value) and KEY not in str(e.value) and "secret detail" not in str(e.value)


def test_blocked_or_empty_answer_is_reported():
    with pytest.raises(ProviderError, match="no answer"):
        provider(body={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}).complete(system="s", messages=[USER_MSG], tools=[])


def test_network_failure_is_reported_without_details():
    with pytest.raises(ProviderError, match="Couldn't reach") as e:
        provider(raise_exc=httpx.ConnectError(f"dns failure for {KEY}")).complete(system="s", messages=[USER_MSG], tools=[])
    assert KEY not in str(e.value)


def test_max_tokens_is_reported_as_such():
    body = {"candidates": [{"content": {"parts": [{"text": "cut off"}]}, "finishReason": "MAX_TOKENS"}]}
    assert provider(body=body).complete(system="s", messages=[USER_MSG], tools=[]).stop_reason == "max_tokens"


def test_get_provider_selects_gemini_only_with_both_the_setting_and_a_key():
    base = dict(secret_key="x" * 40, _env_file=None)
    assert get_provider(Settings(**base, ai_provider="gemini", gemini_api_key=KEY)).name == "gemini"
    assert get_provider(Settings(**base, ai_provider="gemini")) is None                       # key missing
    assert get_provider(Settings(**base, ai_provider="none", gemini_api_key=KEY)) is None      # a key alone never turns AI on
    assert get_provider(Settings(**base, ai_provider="gemini", gemini_api_key=KEY)).model == "gemini-3.5-flash"
