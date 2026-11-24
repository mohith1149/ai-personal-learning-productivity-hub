"""Request/response models for the AI foundation endpoints."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class MemoryIn(Strict):
    content: str = Field(min_length=3, max_length=500)
    kind: Literal["preference", "fact", "goal"] = "preference"


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    content: str
    source: str
    created_at: datetime


class ChatIn(Strict):
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
