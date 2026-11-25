"""Assistant orchestration: conversations, the tool-calling loop, and approvals.

Flow of one chat turn:
  1. the user's message is saved;
  2. the provider is asked for a reply, given the system prompt and the tool list;
  3. if it asks for READ tools they run now and their results go back to it; if it asks for WRITE tools, a pending action is stored and the
     model is told "awaiting approval" (nothing has changed);
  4. repeat until it answers in plain text (at most MAX_STEPS rounds).
Pending actions run only when the user approves them (POST /ai/pending/{id}/approve), through the same service functions as the web pages.
The model never receives a user id, a database handle or a way to skip approval."""
import json
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import prompt, tools
from app.ai.types import LLMProvider, ProviderError
from app.core.timeutil import user_today
from app.models import AIConversation, AIMessage, AIPendingAction, User
from app.services import challenges, courses, dashboard, habits, planner, projects, roadmap, tasks  # noqa: F401  (their exceptions are caught below)

MAX_STEPS = 6
MAX_PENDING_PER_TURN = 5
MAX_PENDING_OPEN = 20
HISTORY_LIMIT = 40
MAX_MESSAGE = 4000


class NotFound(Exception):
    pass


class RuleError(ValueError):
    pass


class Conflict(Exception):
    pass


class NotConnected(Exception):
    """No AI provider is configured."""


# Business-rule errors raised by the services a tool calls. They are safe, human-readable messages.
_SERVICE_ERRORS = tuple({m.NotFound for m in (tasks, courses, projects, roadmap, habits, planner, challenges) if hasattr(m, "NotFound")}
                        | {m.RuleError for m in (tasks, courses, projects, roadmap, habits, planner, challenges) if hasattr(m, "RuleError")}
                        | {m.Conflict for m in (tasks, courses, projects, roadmap, habits, planner, challenges) if hasattr(m, "Conflict")}
                        | {ValueError})


def _run_tool(db: Session, user: User, name: str, raw_input: dict) -> tuple[str, bool]:
    """Validate and run one tool now. Returns (text for the model, is_error)."""
    tool = tools.TOOLS.get(name)
    if tool is None:
        return f"Unknown tool '{name}'.", True
    try:
        args = tool.args.model_validate(raw_input)
        return json.dumps(tools.encode(tool.run(db, user, args))), False
    except ValidationError as e:
        return "Invalid arguments: " + "; ".join(f"{'.'.join(map(str, err['loc'])) or 'input'}: {err['msg']}" for err in e.errors()[:5]), True
    except _SERVICE_ERRORS as e:
        db.rollback()
        return str(e) or type(e).__name__, True
    except Exception:  # an unexpected failure must not leak internals to the model
        db.rollback()
        return "The tool failed unexpectedly.", True


# ============================== conversations ==============================


def _conversation(db: Session, user: User, conversation_id: int) -> AIConversation:
    c = db.scalar(select(AIConversation).where(AIConversation.id == conversation_id, AIConversation.user_id == user.id))
    if c is None:
        raise NotFound("Conversation not found")
    return c


def _save(db: Session, conversation_id: int, role: str, blocks: list[dict]) -> AIMessage:
    m = AIMessage(conversation_id=conversation_id, role=role, content=json.dumps(blocks))
    db.add(m)
    db.flush()
    return m


def _history(db: Session, conversation_id: int) -> list[dict]:
    rows = list(db.scalars(select(AIMessage).where(AIMessage.conversation_id == conversation_id).order_by(AIMessage.id.desc()).limit(HISTORY_LIMIT)))[::-1]
    msgs = [{"role": r.role, "content": json.loads(r.content)} for r in rows]
    # never start in the middle of a tool exchange: begin at a user message that is plain text
    while msgs and not (msgs[0]["role"] == "user" and any(b.get("type") == "text" for b in msgs[0]["content"])):
        msgs.pop(0)
    return msgs


def _view_message(m: AIMessage) -> dict:
    blocks = json.loads(m.content)
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return {"id": m.id, "role": m.role, "text": text, "tool_calls": [{"name": b["name"], "input": b["input"]} for b in blocks if b.get("type") == "tool_use"],
            "is_tool_result": any(b.get("type") == "tool_result" for b in blocks), "created_at": m.created_at}


def list_conversations(db: Session, user: User) -> list[dict]:
    rows = db.execute(select(AIConversation, func.count(AIMessage.id)).outerjoin(AIMessage, AIMessage.conversation_id == AIConversation.id)
                      .where(AIConversation.user_id == user.id).group_by(AIConversation.id).order_by(AIConversation.id.desc()))
    return [{"id": c.id, "title": c.title, "message_count": n, "updated_at": c.updated_at} for c, n in rows]


def get_conversation(db: Session, user: User, conversation_id: int) -> dict:
    c = _conversation(db, user, conversation_id)
    views = [_view_message(m) for m in db.scalars(select(AIMessage).where(AIMessage.conversation_id == c.id).order_by(AIMessage.id))]
    return {"id": c.id, "title": c.title, "messages": [v for v in views if not v["is_tool_result"]],
            "pending": [_pending_out(a) for a in _pending_rows(db, user, conversation_id=c.id)]}


def delete_conversation(db: Session, user: User, conversation_id: int) -> None:
    db.delete(_conversation(db, user, conversation_id))
    db.commit()


# ============================== the chat turn ==============================


def chat(db: Session, user: User, provider: LLMProvider | None, message: str, conversation_id: int | None = None, now: datetime | None = None) -> dict:
    if provider is None:
        raise NotConnected("No AI provider is connected. Set AI_PROVIDER and a key in backend/.env")
    message = message.strip()
    if not message:
        raise RuleError("Write a message first")
    if len(message) > MAX_MESSAGE:
        raise RuleError(f"Keep the message under {MAX_MESSAGE} characters")
    if conversation_id is None:
        conv = AIConversation(user_id=user.id, title=message[:60])
        db.add(conv)
        db.flush()
    else:
        conv = _conversation(db, user, conversation_id)
    _save(db, conv.id, "user", [{"type": "text", "text": message}])
    db.commit()

    system = prompt.system_prompt(user.display_name, user_today(user, now))
    specs = tools.specs()
    created: list[AIPendingAction] = []
    reply = ""
    for _step in range(MAX_STEPS):
        try:
            resp = provider.complete(system=system, messages=_history(db, conv.id), tools=specs)
        except ProviderError:
            db.rollback()
            raise
        blocks = ([{"type": "text", "text": resp.text}] if resp.text else []) + [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input, **({"meta": c.meta} if c.meta else {})} for c in resp.tool_calls]
        if not blocks:
            blocks = [{"type": "text", "text": "(no reply)"}]
        _save(db, conv.id, "assistant", blocks)
        db.commit()
        reply = resp.text or reply
        if not resp.tool_calls:
            break
        results = []
        for call in resp.tool_calls:
            tool = tools.TOOLS.get(call.name)
            if tool is not None and tool.kind == "write":
                text, is_error = _propose(db, user, conv.id, call, created)
            else:
                text, is_error = _run_tool(db, user, call.name, call.input)
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": text, "is_error": is_error})
        _save(db, conv.id, "user", results)
        db.commit()
    else:
        reply = reply or "I stopped because this needed too many steps. Please ask again more simply."
        _save(db, conv.id, "assistant", [{"type": "text", "text": reply}])
        db.commit()
    return {"conversation_id": conv.id, "reply": reply, "pending": [_pending_out(a) for a in created]}


def _propose(db: Session, user: User, conversation_id: int, call, created: list) -> tuple[str, bool]:
    """A write tool: validate now, store a pending action, change nothing."""
    tool = tools.TOOLS[call.name]
    try:
        args = tool.args.model_validate(call.input)
    except ValidationError as e:
        return "Invalid arguments: " + "; ".join(f"{'.'.join(map(str, err['loc'])) or 'input'}: {err['msg']}" for err in e.errors()[:5]), True
    if len(created) >= MAX_PENDING_PER_TURN or len(_pending_rows(db, user)) >= MAX_PENDING_OPEN:
        return "Too many proposals are already waiting for approval. Ask the user to review them first.", True
    action = AIPendingAction(conversation_id=conversation_id, tool_use_id=call.id, tool_name=call.name, tool_input=json.dumps(tools.encode(args.model_dump())), status="pending")
    db.add(action)
    db.flush()
    created.append(action)
    return f"Proposal #{action.id} is awaiting the user's approval. Nothing has been changed yet.", False


# ============================== approvals ==============================


def _pending_rows(db: Session, user: User, status: str = "pending", conversation_id: int | None = None) -> list[AIPendingAction]:
    q = select(AIPendingAction).join(AIConversation, AIConversation.id == AIPendingAction.conversation_id).where(AIConversation.user_id == user.id,
                                                                                                                AIPendingAction.status == status)
    if conversation_id is not None:
        q = q.where(AIPendingAction.conversation_id == conversation_id)
    return list(db.scalars(q.order_by(AIPendingAction.id)))


def _pending_out(a: AIPendingAction) -> dict:
    tool = tools.TOOLS.get(a.tool_name)
    inp = json.loads(a.tool_input)
    try:
        summary = tools.describe(a.tool_name, tool.args.model_validate(inp)) if tool else a.tool_name
    except ValidationError:
        summary = a.tool_name
    return {"id": a.id, "conversation_id": a.conversation_id, "tool_name": a.tool_name, "summary": summary, "input": inp, "status": a.status,
            "result": json.loads(a.result) if a.result else None, "created_at": a.created_at, "resolved_at": a.resolved_at}


def list_pending(db: Session, user: User, status: str = "pending") -> list[dict]:
    if status not in ("pending", "approved", "rejected", "executed", "failed"):
        raise RuleError("Unknown status")
    return [_pending_out(a) for a in _pending_rows(db, user, status)]


def _get_pending(db: Session, user: User, action_id: int) -> AIPendingAction:
    a = db.scalar(select(AIPendingAction).join(AIConversation, AIConversation.id == AIPendingAction.conversation_id)
                  .where(AIPendingAction.id == action_id, AIConversation.user_id == user.id))
    if a is None:
        raise NotFound("Proposal not found")
    return a


def approve(db: Session, user: User, action_id: int, now: datetime | None = None) -> dict:
    a = _get_pending(db, user, action_id)
    if a.status != "pending":
        raise Conflict(f"This proposal was already {a.status}")
    a.status = "approved"
    db.commit()  # claimed: a second approval request now conflicts instead of running it twice
    text, is_error = _run_tool(db, user, a.tool_name, json.loads(a.tool_input))
    a.status = "failed" if is_error else "executed"
    a.result = json.dumps({"error": text} if is_error else json.loads(text))
    a.resolved_at = now or datetime.now(timezone.utc)
    db.commit()
    return _pending_out(a)


def reject(db: Session, user: User, action_id: int, now: datetime | None = None) -> dict:
    a = _get_pending(db, user, action_id)
    if a.status != "pending":
        raise Conflict(f"This proposal was already {a.status}")
    a.status = "rejected"
    a.resolved_at = now or datetime.now(timezone.utc)
    db.commit()
    return _pending_out(a)
