"""Assistant memory: short facts and preferences the user can read and delete. The assistant can only add one through an approved action."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AIMemory, User

KINDS = ("preference", "fact", "goal")
MAX_MEMORIES = 100


class NotFound(Exception):
    pass


class RuleError(ValueError):
    pass


class Conflict(Exception):
    pass


def list_memories(db: Session, user: User) -> list[AIMemory]:
    return list(db.scalars(select(AIMemory).where(AIMemory.user_id == user.id).order_by(AIMemory.id.desc())))


def add_memory(db: Session, user: User, content: str, kind: str = "preference", source: str = "user") -> AIMemory:
    content = content.strip()
    if kind not in KINDS:
        raise RuleError(f"kind must be one of {', '.join(KINDS)}")
    if not 3 <= len(content) <= 500:
        raise RuleError("A memory must be 3 to 500 characters")
    if db.scalar(select(AIMemory.id).where(AIMemory.user_id == user.id, func.lower(AIMemory.content) == content.lower())):
        raise Conflict("That is already remembered")
    if (db.scalar(select(func.count()).select_from(AIMemory).where(AIMemory.user_id == user.id)) or 0) >= MAX_MEMORIES:
        raise RuleError(f"At most {MAX_MEMORIES} memories are kept. Delete some first")
    m = AIMemory(user_id=user.id, kind=kind, content=content, source=source)
    db.add(m)
    db.commit()
    return m


def delete_memory(db: Session, user: User, memory_id: int) -> None:
    m = db.scalar(select(AIMemory).where(AIMemory.id == memory_id, AIMemory.user_id == user.id))
    if m is None:
        raise NotFound("Memory not found")
    db.delete(m)
    db.commit()
