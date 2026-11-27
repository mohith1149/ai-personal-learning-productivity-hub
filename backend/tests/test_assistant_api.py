"""HTTP-level tests for /api/ai: auth, status, tools, memory, chat (with a scripted provider) and approvals."""
import pytest

from app.ai.providers import ScriptedProvider
from app.ai.types import LLMResponse, ProviderError, ToolCall
from app.routers import assistant as router

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Ada", "timezone": "Asia/Kolkata"}


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def use(monkeypatch, *responses):
    p = ScriptedProvider(list(responses))
    monkeypatch.setattr(router, "current_provider", lambda *_a, **_k: p)
    return p


def propose(name, **input_) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall("tu_1", name, input_)], stop_reason="tool_use")


@pytest.mark.parametrize("method, path", [
    ("get", "/api/ai/status"), ("get", "/api/ai/tools"), ("get", "/api/ai/models"),
    ("post", "/api/ai/chat"), ("get", "/api/ai/conversations"), ("get", "/api/ai/conversations/1"), ("delete", "/api/ai/conversations/1"),
    ("get", "/api/ai/pending"), ("post", "/api/ai/pending/1/approve"), ("post", "/api/ai/pending/1/reject"),
])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_status_says_ai_is_off_and_never_claims_a_live_connection(c):
    r = c.get("/api/ai/status").json()
    assert (r["provider"], r["connected"], r["model"], r["live_verified"]) == ("none", False, None, False) and "off" in r["message"].lower()


def test_status_with_a_provider_still_says_it_is_not_live_verified(c, monkeypatch):
    use(monkeypatch)
    r = c.get("/api/ai/status").json()
    assert (r["provider"], r["connected"], r["live_verified"]) == ("scripted", True, False) and "not been tested" in r["message"]


def test_the_tools_endpoint_lists_what_the_assistant_may_do(c):
    tools = {t["name"]: t for t in c.get("/api/ai/tools").json()}
    assert tools["get_today_tasks"]["kind"] == "read" and tools["create_task"]["kind"] == "write"
    assert tools["create_task"]["input_schema"]["properties"]["title"] and len(tools) == 19
    assert "api_key" not in str(tools).lower()


def test_chat_is_unavailable_without_a_provider(c):
    r = c.post("/api/ai/chat", json={"message": "hi"})
    assert r.status_code == 503 and "No AI provider" in r.json()["detail"]
    assert c.get("/api/ai/conversations").json() == []


@pytest.mark.parametrize("body", [{}, {"message": ""}, {"message": "hi", "extra": 1}, {"message": "x" * 4001}, {"message": "hi", "conversation_id": "a"}])
def test_chat_validation(c, monkeypatch, body):
    use(monkeypatch, LLMResponse(text="x"))
    assert c.post("/api/ai/chat", json=body).status_code == 422


def test_chat_a_read_tool_and_the_conversation_list(c, monkeypatch):
    c.post("/api/tasks", json={"title": "Write report"})
    use(monkeypatch, propose("get_pending_tasks"), LLMResponse(text="You have one open task: Write report."))
    r = c.post("/api/ai/chat", json={"message": "what's open?"})
    assert r.status_code == 200 and r.json()["reply"] == "You have one open task: Write report." and r.json()["pending"] == []
    cid = r.json()["conversation_id"]
    assert [x["title"] for x in c.get("/api/ai/conversations").json()] == ["what's open?"]
    conv = c.get(f"/api/ai/conversations/{cid}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "assistant"] and conv["messages"][1]["tool_calls"][0]["name"] == "get_pending_tasks"
    assert c.delete(f"/api/ai/conversations/{cid}").status_code == 204
    assert c.get(f"/api/ai/conversations/{cid}").status_code == 404


def test_a_provider_failure_is_a_clean_502(c, monkeypatch):
    class Broken:
        name, model = "broken", "m"

        def complete(self, **kw):
            raise ProviderError("The Anthropic API request failed (RuntimeError)")

    monkeypatch.setattr(router, "current_provider", lambda *_a, **_k: Broken())
    r = c.post("/api/ai/chat", json={"message": "hi"})
    assert r.status_code == 502 and "RuntimeError" in r.json()["detail"]


def test_propose_review_approve_end_to_end(c, monkeypatch):
    use(monkeypatch, propose("create_task", title="Read paper", priority=2), LLMResponse(text="Proposed. Waiting for your approval."))
    out = c.post("/api/ai/chat", json={"message": "add a task to read the paper"}).json()
    assert len(out["pending"]) == 1
    aid = out["pending"][0]["id"]
    assert c.get("/api/tasks").json()["items"] == []                                  # not created yet
    queue = c.get("/api/ai/pending").json()
    assert [(a["id"], a["status"], a["summary"]) for a in queue] == [(aid, "pending", 'Create the task "Read paper"')]
    assert c.get(f"/api/ai/conversations/{out['conversation_id']}").json()["pending"][0]["id"] == aid

    done = c.post(f"/api/ai/pending/{aid}/approve")
    assert done.status_code == 200 and done.json()["status"] == "executed"
    assert [t["title"] for t in c.get("/api/tasks").json()["items"]] == ["Read paper"]
    assert c.post(f"/api/ai/pending/{aid}/approve").status_code == 409
    assert c.post(f"/api/ai/pending/{aid}/reject").status_code == 409
    assert c.get("/api/ai/pending").json() == []
    assert [a["id"] for a in c.get("/api/ai/pending", params={"status": "executed"}).json()] == [aid]
    assert c.get("/api/ai/pending", params={"status": "bogus"}).status_code == 422


def test_reject_over_http(c, monkeypatch):
    use(monkeypatch, propose("create_task", title="Nope"), LLMResponse(text="ok"))
    aid = c.post("/api/ai/chat", json={"message": "add"}).json()["pending"][0]["id"]
    assert c.post(f"/api/ai/pending/{aid}/reject").json()["status"] == "rejected"
    assert c.get("/api/tasks").json()["items"] == []
    assert c.post("/api/ai/pending/99999/approve").status_code == 404


def test_other_users_data_is_not_reachable(c, db, monkeypatch):
    from app.models import AIConversation, AIPendingAction, User

    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    conv = AIConversation(user_id=2, title="theirs")
    db.add(conv)
    db.commit()
    db.add(AIPendingAction(conversation_id=conv.id, tool_use_id="x", tool_name="create_task", tool_input='{"title": "Theirs"}'))
    db.commit()
    aid = db.query(AIPendingAction).one().id
    assert c.get("/api/ai/conversations").json() == [] and c.get("/api/ai/pending").json() == []
    assert c.get(f"/api/ai/conversations/{conv.id}").status_code == 404
    assert c.post(f"/api/ai/pending/{aid}/approve").status_code == 404
    use(monkeypatch, LLMResponse(text="x"))
    assert c.post("/api/ai/chat", json={"message": "hi", "conversation_id": conv.id}).status_code == 404
    assert c.get("/api/tasks").json()["items"] == []
