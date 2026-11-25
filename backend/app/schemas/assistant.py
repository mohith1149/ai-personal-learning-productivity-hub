"""Request/response models for the AI foundation endpoints."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import Strict


class StatusOut(BaseModel):
    provider: str  # "none" or the configured provider
    connected: bool  # a provider is configured and has a key
    model: str | None
    live_verified: bool  # always False until the live connection has been tested (Phase 6)
    message: str


class ToolOut(BaseModel):
    name: str
    description: str
    kind: Literal["read", "write"]
    input_schema: dict[str, Any]


class ModelChoice(Strict):
    """The model picked in the chat's menu. Both empty = the default from backend/.env."""
    provider: Literal["groq", "gemini", "anthropic"] | None = None
    model: str | None = Field(default=None, max_length=100)


class ModelProviderOut(BaseModel):
    provider: str
    label: str
    default_model: str
    models: list[str]


class ModelsOut(BaseModel):
    default_provider: str | None  # None while AI is off
    providers: list[ModelProviderOut]


class ChatIn(ModelChoice):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None


class PendingOut(BaseModel):
    id: int
    conversation_id: int
    tool_name: str
    summary: str
    input: dict[str, Any]
    status: Literal["pending", "approved", "rejected", "executed", "failed"]
    result: Any | None
    created_at: datetime
    resolved_at: datetime | None


class ChatOut(BaseModel):
    conversation_id: int
    reply: str
    pending: list[PendingOut]


class ConversationSummary(BaseModel):
    id: int
    title: str
    message_count: int
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    tool_calls: list[dict[str, Any]]
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    title: str
    messages: list[MessageOut]
    pending: list[PendingOut]


class AutofillIn(ModelChoice):
    repo_url: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=4000)


class AutofillOut(BaseModel):
    """A suggestion only. Nothing is saved; the project form shows it for the user to edit."""
    title: str
    description: str | None
    objective: str | None
    tech_stack: list[str]
    milestones: list[str]
    repo_url: str | None
    start_date: date | None
    source: Literal["repo", "description", "repo_and_description"]
    readme_used: bool


class CheckOut(BaseModel):
    ok: bool
    provider: str
    model: str
    message: str
