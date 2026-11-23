from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import DailyChallenge, EmailNotification, User


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def _user(db) -> User:
    u = User(email="me@example.com", password_hash="x", display_name="Me")
    db.add(u)
    db.commit()
    return u


def test_completed_challenge_requires_evidence(db):
    u = _user(db)
    db.add(DailyChallenge(user_id=u.id, date=date(2026, 1, 1), mode="new_project",
                          planned_task="x", status="completed"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_excused_challenge_requires_reason(db):
    u = _user(db)
    db.add(DailyChallenge(user_id=u.id, date=date(2026, 1, 1), mode="new_project",
                          planned_task="x", status="excused"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_one_challenge_per_day(db):
    u = _user(db)
    for _ in range(2):
        db.add(DailyChallenge(user_id=u.id, date=date(2026, 1, 1), mode="new_project",
                              planned_task="x"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_email_idempotency_key(db):
    u = _user(db)
    for _ in range(2):
        db.add(EmailNotification(user_id=u.id, type="daily_plan", period_key="2026-01-01"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_datetimes_round_trip_as_utc(db):
    u = _user(db)
    db.expire_all()
    fresh = db.get(User, u.id)
    assert fresh.created_at.tzinfo is not None
