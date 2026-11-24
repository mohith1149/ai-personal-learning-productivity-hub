"""HTTP endpoints for the AI foundation: status, tools, memory, chat, and approvals. Login required.

Chat answers 503 until a provider is configured (AI_PROVIDER + key in backend/.env). Everything else works without one."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.ai import tools
from app.ai.providers import get_provider
from app.ai.types import ProviderError
from app.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.schemas import assistant as s
from app.services import ai_memory, assistant as svc

router = APIRouter(prefix="/ai", tags=["ai"])

ERRORS = (svc.NotFound, svc.RuleError, svc.Conflict, ai_memory.NotFound, ai_memory.RuleError, ai_memory.Conflict)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, (svc.NotFound, ai_memory.NotFound)):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (svc.Conflict, ai_memory.Conflict)):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _run(fn, *args):
    try:
        return fn(*args)
    except ERRORS as e:
        raise _http(e) from None


def current_provider():
    """The configured provider or None. A function (not a constant) so tests can swap in a scripted one."""
    return get_provider(get_settings())


@router.get("/status", response_model=s.StatusOut)
def get_status(user: CurrentUser):
    cfg = get_settings()
    p = current_provider()
    if p is not None:
        return {"provider": p.name, "connected": True, "model": p.model, "live_verified": False,
                "message": "A provider is configured, but the live connection has not been tested yet."}
    msg = "AI is off. Set AI_PROVIDER=anthropic and ANTHROPIC_API_KEY in backend/.env to turn it on." if cfg.ai_provider == "none" else \
        "A provider is selected but its API key is missing in backend/.env."
    return {"provider": cfg.ai_provider, "connected": False, "model": None, "live_verified": False, "message": msg}


@router.get("/tools", response_model=list[s.ToolOut])
def list_tools(user: CurrentUser):
    """Everything the assistant is allowed to do. Write tools only create proposals that you approve."""
    return [{**t.spec(), "kind": t.kind} for t in tools.TOOLS.values()]


# ------------------------------ memory ------------------------------

@router.get("/memories", response_model=list[s.MemoryOut])
def list_memories(user: CurrentUser, db: DbSession):
    return ai_memory.list_memories(db, user)


@router.post("/memories", response_model=s.MemoryOut, status_code=status.HTTP_201_CREATED)
def add_memory(body: s.MemoryIn, user: CurrentUser, db: DbSession):
    return _run(ai_memory.add_memory, db, user, body.content, body.kind, "user")


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(ai_memory.delete_memory, db, user, memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------ chat ------------------------------

@router.post("/chat", response_model=s.ChatOut)
def chat(body: s.ChatIn, user: CurrentUser, db: DbSession):
    try:
        return svc.chat(db, user, current_provider(), body.message, body.conversation_id)
    except svc.NotConnected as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    except ProviderError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
    except ERRORS as e:
        raise _http(e) from None


@router.get("/conversations", response_model=list[s.ConversationSummary])
def conversations(user: CurrentUser, db: DbSession):
    return svc.list_conversations(db, user)


@router.get("/conversations/{conversation_id}", response_model=s.ConversationOut)
def get_conversation(conversation_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.get_conversation, db, user, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_conversation, db, user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------ approvals ------------------------------

@router.get("/pending", response_model=list[s.PendingOut])
def pending(user: CurrentUser, db: DbSession,
            action_status: Annotated[Literal["pending", "approved", "rejected", "executed", "failed"], Query(alias="status")] = "pending"):
    return _run(svc.list_pending, db, user, action_status)


@router.post("/pending/{action_id}/approve", response_model=s.PendingOut)
def approve(action_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.approve, db, user, action_id)


@router.post("/pending/{action_id}/reject", response_model=s.PendingOut)
def reject(action_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.reject, db, user, action_id)
