"""HTTP endpoints for the AI assistant: status, models, tools, chat, and approvals. Login required.

Chat answers 503 until a provider is configured (AI_PROVIDER + key in backend/.env). Everything else works without one."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.ai import catalog, tools
from app.ai.providers import get_provider
from app.ai.types import ProviderError
from app.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.routers.challenges import _GH_STATUS, get_github
from app.schemas import assistant as s
from app.services import assistant as svc
from app.services import github as gh
from app.services import project_autofill as autofill

router = APIRouter(prefix="/ai", tags=["ai"])

ERRORS = (svc.NotFound, svc.RuleError, svc.Conflict)

# (provider, model) pairs that answered a real "Test the connection" since the backend started. In memory only: a restart honestly resets it.
_verified: set[tuple[str, str]] = set()


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, svc.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _run(fn, *args):
    try:
        return fn(*args)
    except ERRORS as e:
        raise _http(e) from None


def current_provider(provider: str | None = None, model: str | None = None):
    """The provider (the user's menu pick, else the default from .env) or None. A function so tests can swap in a scripted one."""
    try:
        return get_provider(get_settings(), provider, model)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None


def get_model_options() -> list[dict]:
    """A function so tests can avoid the network."""
    return catalog.options(get_settings())


@router.get("/status", response_model=s.StatusOut)
def get_status(user: CurrentUser):
    cfg = get_settings()
    p = current_provider()
    if p is not None:
        ok = (p.name, p.model) in _verified
        return {"provider": p.name, "connected": True, "model": p.model, "live_verified": ok,
                "message": "The connection was tested and works." if ok else "A provider is configured, but the live connection has not been tested yet."}
    msg = "AI is off. Set AI_PROVIDER=groq and GROQ_API_KEY in backend/.env to turn it on (Groq has a free tier)." if cfg.ai_provider == "none" else \
        "A provider is selected but its API key is missing in backend/.env."
    return {"provider": cfg.ai_provider, "connected": False, "model": None, "live_verified": False, "message": msg}


@router.get("/models", response_model=s.ModelsOut)
def models(user: CurrentUser):
    """The providers that have a key and the models each offers, for the chat's model menu."""
    cfg = get_settings()
    options = get_model_options()
    return {"default_provider": cfg.ai_provider if options else None, "providers": options}


@router.post("/check", response_model=s.CheckOut)
def check_connection(user: CurrentUser, body: s.ModelChoice | None = None):
    """A real, tiny request to the provider so you can see whether the key works. Costs a few tokens; stores nothing."""
    body = body or s.ModelChoice()
    p = current_provider(body.provider, body.model)
    if p is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI provider is connected. Set AI_PROVIDER and a key in backend/.env")
    try:
        r = p.complete(system="Reply with the single word OK.", messages=[{"role": "user", "content": [{"type": "text", "text": "ping"}]}], tools=[])
    except ProviderError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
    ok = bool(r.text.strip())
    if ok:
        _verified.add((p.name, p.model))
    return {"ok": ok, "provider": p.name, "model": p.model, "message": "The provider answered. The connection works." if ok else "The provider answered with nothing. Try another model"}


@router.post("/project-autofill", response_model=s.AutofillOut)
def project_autofill(body: s.AutofillIn, user: CurrentUser, client: Annotated[gh.GitHubClient, Depends(get_github)]):
    """Suggest project fields from a GitHub repo and/or a description. Read-only: nothing is saved."""
    p = current_provider(body.provider, body.model)
    if p is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI provider is connected. Set AI_PROVIDER and a key in backend/.env")
    try:
        return autofill.suggest(p, client, body.repo_url, body.description)
    except autofill.AutofillError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    except gh.GitHubError as e:
        raise HTTPException(_GH_STATUS.get(e.code, 502), e.message) from None
    except ProviderError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None


@router.get("/tools", response_model=list[s.ToolOut])
def list_tools(user: CurrentUser):
    """Everything the assistant is allowed to do. Write tools only create proposals that you approve."""
    return [{**t.spec(), "kind": t.kind} for t in tools.TOOLS.values()]


# ------------------------------ chat ------------------------------

@router.post("/chat", response_model=s.ChatOut)
def chat(body: s.ChatIn, user: CurrentUser, db: DbSession):
    try:
        return svc.chat(db, user, current_provider(body.provider, body.model), body.message, body.conversation_id)
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
