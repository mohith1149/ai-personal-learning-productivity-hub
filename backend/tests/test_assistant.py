"""AI foundation: tool registry, the tool-calling loop, approvals, memory, and the provider adapters (no live provider is ever called)."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.ai import prompt, tools
from app.ai.providers import AnthropicProvider, ScriptedProvider, get_provider
from app.ai.types import LLMResponse, ProviderError, ToolCall
from app.config import get_settings
from app.models import AIPendingAction, Task, User
from app.services import assistant as svc
from app.services import auth as auth_service

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)   # 15:30 Mon 23 Nov in Kolkata
TODAY = date(2026, 11, 23)
REAL_TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()   # tools read the real clock, so data they should find is dated by it


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(db, email="me@example.com", password="correct-horse-9", display_name="Ada", timezone="Asia/Kolkata")


@pytest.fixture
def other(db, user) -> User:
    u = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(u)
    db.commit()
    return u


def call(name, id_="t1", **input_) -> ToolCall:
    return ToolCall(id=id_, name=name, input=input_)


def say(text) -> LLMResponse:
    return LLMResponse(text=text)


def ask(*calls, text="") -> LLMResponse:
    return LLMResponse(text=text, tool_calls=list(calls), stop_reason="tool_use")


def results_in(request: dict) -> list[dict]:
    """The tool_result blocks in the last message sent to the provider."""
    return [b for b in request["messages"][-1]["content"] if b.get("type") == "tool_result"]


def chat(db, user, provider, text="hello", conversation_id=None):
    return svc.chat(db, user, provider, text, conversation_id, now=NOW)


# ============================== tool registry ==============================


def test_the_tool_set_is_exactly_what_the_design_allows():
    reads = {n for n, t in tools.TOOLS.items() if t.kind == "read"}
    writes = {n for n, t in tools.TOOLS.items() if t.kind == "write"}
    assert reads == {"get_today_tasks", "get_pending_tasks", "get_plan", "get_dashboard", "get_course_progress", "get_next_video", "get_active_projects",
                     "get_roadmap_progress", "get_habit_status", "get_challenge_status", "look_up_github_repo", "get_weekly_report", "get_slipping_items", "get_goals"}
    assert writes == {"create_task", "complete_task", "reschedule_task", "record_project_progress", "create_project_challenge"}
    assert "complete_challenge" not in tools.TOOLS          # evidence must come from the user, never the model


def test_no_tool_accepts_a_user_id_or_extra_fields():
    for t in tools.TOOLS.values():
        spec = t.spec()
        assert spec["input_schema"].get("additionalProperties") is False, t.name
        assert "user_id" not in json.dumps(spec["input_schema"]), t.name
        assert t.description and spec["name"] == t.name
        assert (t.kind == "write") == (t.summarise is not None), t.name


# ============================== the loop: reads ==============================


def test_a_read_tool_runs_and_its_result_goes_back_to_the_model(db, user):
    db.add(Task(user_id=user.id, title="Write report", scheduled_date=REAL_TODAY))
    db.commit()
    p = ScriptedProvider([ask(call("get_today_tasks")), say("You have one task today: Write report.")])
    out = chat(db, user, p, "what do I have today?")
    assert out["reply"] == "You have one task today: Write report." and out["pending"] == []
    seen = results_in(p.requests[1])
    assert len(seen) == 1 and seen[0]["tool_use_id"] == "t1" and not seen[0]["is_error"]
    assert "Write report" in seen[0]["content"]
    assert p.requests[0]["tools"] and p.requests[0]["messages"][0]["content"][0]["text"] == "what do I have today?"
    conv = svc.get_conversation(db, user, out["conversation_id"])
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "assistant"]        # tool results are not shown as chat lines
    assert conv["messages"][1]["tool_calls"][0]["name"] == "get_today_tasks"


def test_tools_only_see_the_signed_in_users_data(db, user, other):
    db.add_all([Task(user_id=user.id, title="Mine", scheduled_date=REAL_TODAY), Task(user_id=other.id, title="Secret", scheduled_date=REAL_TODAY)])
    db.commit()
    p = ScriptedProvider([ask(call("get_today_tasks"), call("get_pending_tasks", id_="t2")), say("ok")])
    chat(db, user, p)
    contents = " ".join(r["content"] for r in results_in(p.requests[1]))
    assert "Mine" in contents and "Secret" not in contents


@pytest.mark.parametrize("name", [n for n, t in tools.TOOLS.items() if t.kind == "read" and not t.spec()["input_schema"].get("required")])  # the GitHub lookup needs a link
def test_every_read_tool_runs_on_an_empty_account(db, user, name):
    p = ScriptedProvider([ask(call(name)), say("done")])
    chat(db, user, p)
    r = results_in(p.requests[1])[0]
    assert not r["is_error"], r["content"]
    json.loads(r["content"])


def test_bad_tool_calls_become_errors_the_model_can_read(db, user):
    p = ScriptedProvider([ask(call("drop_database", id_="a"), call("get_plan", id_="b", day="not-a-date"), call("get_today_tasks", id_="c", user_id=2)), say("sorry")])
    chat(db, user, p)
    by = {r["tool_use_id"]: r for r in results_in(p.requests[1])}
    assert by["a"]["is_error"] and "Unknown tool" in by["a"]["content"]
    assert by["b"]["is_error"] and "Invalid arguments" in by["b"]["content"]
    assert by["c"]["is_error"] and "Invalid arguments" in by["c"]["content"]          # a model can't pass a user id


def test_the_loop_stops_after_the_step_limit(db, user):
    p = ScriptedProvider([ask(call("get_today_tasks", id_=f"t{i}")) for i in range(svc.MAX_STEPS)])
    out = chat(db, user, p)
    assert len(p.requests) == svc.MAX_STEPS and "too many steps" in out["reply"]


def test_an_empty_provider_reply_is_shown_as_such(db, user):
    assert chat(db, user, ScriptedProvider([LLMResponse()]))["reply"] == ""
    assert svc.get_conversation(db, user, 1)["messages"][-1]["text"] == "(no reply)"


def test_a_provider_failure_is_raised_and_the_user_message_is_kept(db, user):
    with pytest.raises(ProviderError):
        chat(db, user, ScriptedProvider([]))
    assert [m["text"] for m in svc.get_conversation(db, user, 1)["messages"]] == ["hello"]


def test_no_provider_and_bad_messages(db, user):
    with pytest.raises(svc.NotConnected):
        chat(db, user, None)
    with pytest.raises(svc.RuleError):
        chat(db, user, ScriptedProvider([]), "   ")
    with pytest.raises(svc.RuleError):
        chat(db, user, ScriptedProvider([]), "x" * 4001)
    assert svc.list_conversations(db, user) == []


def test_a_conversation_continues_and_history_is_sent(db, user):
    p = ScriptedProvider([say("first"), say("second")])
    c1 = chat(db, user, p, "one")["conversation_id"]
    assert chat(db, user, p, "two", c1)["conversation_id"] == c1
    roles = [m["role"] for m in p.requests[1]["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert svc.list_conversations(db, user)[0]["message_count"] == 4


def test_other_users_conversations_are_not_reachable(db, user, other):
    cid = chat(db, user, ScriptedProvider([say("hi")]))["conversation_id"]
    with pytest.raises(svc.NotFound):
        svc.get_conversation(db, other, cid)
    with pytest.raises(svc.NotFound):
        chat(db, other, ScriptedProvider([say("x")]), "hi", cid)
    with pytest.raises(svc.NotFound):
        svc.delete_conversation(db, other, cid)
    svc.delete_conversation(db, user, cid)
    assert svc.list_conversations(db, user) == []


def test_history_never_starts_in_the_middle_of_a_tool_exchange(db, user, monkeypatch):
    monkeypatch.setattr(svc, "HISTORY_LIMIT", 3)
    p = ScriptedProvider([ask(call("get_today_tasks")), say("a"), say("b")])
    cid = chat(db, user, p, "one")["conversation_id"]       # saved: user, assistant(tool_use), user(tool_result), assistant
    chat(db, user, p, "two", cid)
    first = p.requests[2]["messages"][0]
    assert first["role"] == "user" and first["content"][0]["type"] == "text"


# ============================== the loop: writes need approval ==============================


def test_a_write_tool_only_creates_a_proposal(db, user):
    p = ScriptedProvider([ask(call("create_task", title="Read paper", scheduled_date="2026-11-24")), say("I've proposed it. It's waiting for your approval.")])
    out = chat(db, user, p, "add a task to read the paper tomorrow")
    assert db.query(Task).count() == 0                                           # nothing changed
    assert len(out["pending"]) == 1
    action = out["pending"][0]
    assert (action["tool_name"], action["status"]) == ("create_task", "pending")
    assert action["summary"] == 'Create the task "Read paper" for 2026-11-24'
    assert "awaiting the user's approval" in results_in(p.requests[1])[0]["content"] and not results_in(p.requests[1])[0]["is_error"]
    assert [a["id"] for a in svc.list_pending(db, user)] == [action["id"]]


def test_approving_runs_the_service_once(db, user):
    p = ScriptedProvider([ask(call("create_task", title="Read paper")), say("proposed")])
    aid = chat(db, user, p)["pending"][0]["id"]
    done = svc.approve(db, user, aid, now=NOW)
    assert done["status"] == "executed" and done["resolved_at"] is not None and done["result"]["title"] == "Read paper"
    assert [t.title for t in db.query(Task).all()] == ["Read paper"] and db.query(Task).one().user_id == user.id
    with pytest.raises(svc.Conflict):
        svc.approve(db, user, aid)                                               # can't run twice
    with pytest.raises(svc.Conflict):
        svc.reject(db, user, aid)
    assert db.query(Task).count() == 1 and svc.list_pending(db, user) == []
    assert [a["id"] for a in svc.list_pending(db, user, "executed")] == [aid]


def test_rejecting_changes_nothing(db, user):
    aid = chat(db, user, ScriptedProvider([ask(call("create_task", title="Nope")), say("ok")]))["pending"][0]["id"]
    assert svc.reject(db, user, aid, now=NOW)["status"] == "rejected"
    assert db.query(Task).count() == 0
    with pytest.raises(svc.Conflict):
        svc.approve(db, user, aid)
    assert db.query(Task).count() == 0


def test_an_approved_action_that_breaks_a_rule_is_marked_failed_with_the_reason(db, user):
    aid = chat(db, user, ScriptedProvider([ask(call("complete_task", task_id=999)), say("ok")]))["pending"][0]["id"]
    out = svc.approve(db, user, aid)
    assert out["status"] == "failed" and "not found" in out["result"]["error"].lower()


def test_invalid_write_arguments_never_become_proposals(db, user):
    p = ScriptedProvider([ask(call("create_task", title=""), call("reschedule_task", id_="b", task_id=1, new_date="soon"), call("remember", id_="c", content="x" * 600)),
                          say("sorry")])
    out = chat(db, user, p)
    assert out["pending"] == [] and db.query(AIPendingAction).count() == 0
    assert all(r["is_error"] for r in results_in(p.requests[1]))


def test_proposals_are_capped(db, user):
    many = [call("create_task", id_=f"t{i}", title=f"Task {i}") for i in range(svc.MAX_PENDING_PER_TURN + 2)]
    out = chat(db, user, ScriptedProvider([ask(*many), say("ok")]))
    assert len(out["pending"]) == svc.MAX_PENDING_PER_TURN


def test_other_users_proposals_are_not_reachable(db, user, other):
    aid = chat(db, user, ScriptedProvider([ask(call("create_task", title="Mine")), say("ok")]))["pending"][0]["id"]
    with pytest.raises(svc.NotFound):
        svc.approve(db, other, aid)
    with pytest.raises(svc.NotFound):
        svc.reject(db, other, aid)
    assert svc.list_pending(db, other) == [] and db.query(Task).count() == 0


def test_an_approved_task_acts_only_on_the_users_own_data(db, user, other):
    db.add(Task(id=500, user_id=other.id, title="Theirs"))
    db.commit()
    aid = chat(db, user, ScriptedProvider([ask(call("complete_task", task_id=500)), say("ok")]))["pending"][0]["id"]
    assert svc.approve(db, user, aid)["status"] == "failed"
    assert db.get(Task, 500).status == "pending"


def test_reschedule_and_progress_and_challenge_proposals_run_through_the_services(db, user):
    from app.schemas import projects as ps
    from app.services import projects

    t = Task(user_id=user.id, title="Report", scheduled_date=REAL_TODAY)
    db.add(t)
    db.commit()
    pid = projects.create_project(db, user, ps.ProjectCreate(title="RAG"), now=NOW)["id"]
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()
    p = ScriptedProvider([ask(call("reschedule_task", id_="a", task_id=t.id, new_date=tomorrow), call("record_project_progress", id_="b", project_id=pid, minutes=45, summary="Built the loader"),
                              call("create_project_challenge", id_="c", mode="existing_project", project_id=pid, planned_task="Add retrieval", date=tomorrow)), say("ok")])
    out = chat(db, user, p)
    assert len(out["pending"]) == 3
    assert [svc.approve(db, user, a["id"])["status"] for a in out["pending"]] == ["executed"] * 3
    db.refresh(t)
    assert t.scheduled_date.isoformat() == tomorrow and t.status == "pending"          # moved, not completed
    from app.models import DailyChallenge, ProjectSession
    assert db.query(ProjectSession).one().minutes == 45 and db.query(DailyChallenge).one().status == "planned"


# ============================== the prompt ==============================


def test_the_system_prompt_carries_the_rules_and_the_date(db, user):
    p = ScriptedProvider([say("hi")])
    chat(db, user, p)
    system = p.requests[0]["system"]
    assert "Never guess or invent" in system and "NOT verified against GitHub" in system and "must approve" in system
    assert "Today is 2026-11-23" in system and "Ada" in system


def test_there_is_no_memory_feature_any_more():
    assert "remember" not in tools.TOOLS


# ============================== providers ==============================


class StubClient:
    def __init__(self, content=None, error=None):
        self.calls, self._content, self._error = [], content, error
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self._error:
            raise self._error
        return SimpleNamespace(content=self._content, stop_reason="tool_use")


def test_the_anthropic_adapter_translates_requests_and_responses():
    content = [SimpleNamespace(type="text", text="Looking. "), SimpleNamespace(type="tool_use", id="tu_1", name="get_today_tasks", input={}),
               SimpleNamespace(type="thinking", thinking="ignored")]
    client = StubClient(content)
    p = AnthropicProvider("sk-test", "claude-opus-5-5", client=client)
    out = p.complete(system="rules", messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}], tools=tools.specs())
    assert (out.text, out.stop_reason) == ("Looking. ", "tool_use") and out.tool_calls == [ToolCall("tu_1", "get_today_tasks", {})]
    sent = client.calls[0]
    assert sent["model"] == "claude-opus-5-5" and sent["system"] == "rules" and sent["tools"][0]["input_schema"] and "api_key" not in sent


def test_a_provider_error_never_leaks_the_key_or_request_details():
    secret = "sk-ant-SECRET-123"
    p = AnthropicProvider(secret, "m", client=StubClient(error=RuntimeError(f"401 for key {secret}")))
    with pytest.raises(ProviderError) as e:
        p.complete(system="s", messages=[], tools=[])
    assert secret not in str(e.value) and "RuntimeError" in str(e.value)


def test_ai_is_off_by_default_and_needs_both_provider_and_key():
    base = get_settings()
    assert base.ai_provider == "none" and get_provider(base) is None
    assert get_provider(base.model_copy(update={"anthropic_api_key": "sk-x"})) is None                       # a key alone does not turn it on
    assert get_provider(base.model_copy(update={"ai_provider": "anthropic", "anthropic_api_key": None})) is None
    p = get_provider(base.model_copy(update={"ai_provider": "anthropic", "anthropic_api_key": "sk-x"}))
    assert p.name == "anthropic" and p.model == base.anthropic_model
