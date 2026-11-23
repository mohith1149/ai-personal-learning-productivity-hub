import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import SESSION_COOKIE, create_access_token
from app.models import LoginAttempt, User
from app.services import auth as auth_service

SETUP = {
    "email": "Me@Example.com",
    "password": "correct-horse-9",
    "display_name": "Me",
    "timezone": "Asia/Kolkata",
}


def do_setup(client, **over):
    return client.post("/api/auth/setup", json={**SETUP, **over})


def test_status_before_and_after_setup(client):
    r = client.get("/api/auth/status")
    assert r.json() == {"setup_required": True, "authenticated": False, "user": None}
    assert do_setup(client).status_code == 201
    r = client.get("/api/auth/status").json()
    assert r["setup_required"] is False and r["authenticated"] is True
    assert r["user"]["email"] == "me@example.com"  # normalised


def test_setup_response_never_leaks_secrets(client):
    r = do_setup(client)
    body = r.text.lower()
    assert "password" not in body and "hash" not in body and "session_version" not in body
    assert set(r.json()) == {"id", "email", "display_name", "timezone"}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_password_is_hashed_in_database(client, db):
    do_setup(client)
    user = db.scalar(select(User))
    assert user.password_hash != SETUP["password"]
    assert user.password_hash.startswith("$2")  # bcrypt
    assert user.settings is not None and user.settings.reminder_email == "me@example.com"


def test_second_setup_is_rejected_and_cannot_overwrite(client, db):
    assert do_setup(client).status_code == 201
    r = do_setup(client, email="attacker@example.com", password="attacker-pass-1")
    assert r.status_code == 409
    assert db.scalar(select(User.email)) == "me@example.com"
    assert len(db.scalars(select(User)).all()) == 1
    # original credentials still work, attacker's do not
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email": SETUP["email"], "password": SETUP["password"]}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "attacker@example.com", "password": "attacker-pass-1"}).status_code == 401


def test_setup_race_is_blocked_by_database(client, db):
    """Even if two requests pass the application check together, id=1 collides."""
    do_setup(client)
    orig = auth_service.setup_required
    auth_service.setup_required = lambda _db: True  # simulate the stale check
    try:
        with pytest.raises(auth_service.SetupAlreadyDone):
            auth_service.create_first_user(
                db, email="b@example.com", password="another-pass-1", display_name="B", timezone="UTC"
            )
    finally:
        auth_service.setup_required = orig
    assert len(db.scalars(select(User)).all()) == 1


@pytest.mark.parametrize(
    "over",
    [
        {"password": "short1"},
        {"password": "alllettersonly"},
        {"password": "1234567890123"},
        {"password": " leading-space-1"},
        {"email": "not-an-email"},
        {"display_name": "   "},
        {"timezone": "Mars/Phobos"},
    ],
)
def test_setup_validation(client, over):
    assert do_setup(client, **over).status_code == 422


def test_login_before_setup_conflict(client):
    r = client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 409


def test_login_success_and_me(client):
    do_setup(client)
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "ME@example.com", "password": SETUP["password"]})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["display_name"] == "Me"


def test_wrong_password_and_unknown_email_look_identical(client):
    do_setup(client)
    client.cookies.clear()
    a = client.post("/api/auth/login", json={"email": SETUP["email"], "password": "wrong-pass-123"})
    b = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass-123"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_repeated_failures(client, db):
    do_setup(client)
    client.cookies.clear()
    for _ in range(auth_service.MAX_FAILED_ATTEMPTS):
        assert client.post("/api/auth/login", json={"email": SETUP["email"], "password": "bad-pass-1234"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": SETUP["email"], "password": "bad-pass-1234"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    # the correct password is also refused while locked out
    r = client.post("/api/auth/login", json={"email": SETUP["email"], "password": SETUP["password"]})
    assert r.status_code == 429
    assert len(db.scalars(select(LoginAttempt)).all()) == auth_service.MAX_FAILED_ATTEMPTS


def test_successful_login_clears_failures(client, db):
    do_setup(client)
    client.cookies.clear()
    for _ in range(3):
        client.post("/api/auth/login", json={"email": SETUP["email"], "password": "bad-pass-1234"})
    assert client.post("/api/auth/login", json={"email": SETUP["email"], "password": SETUP["password"]}).status_code == 200
    assert db.scalars(select(LoginAttempt)).all() == []


def test_logout_revokes_the_token_server_side(client):
    do_setup(client)
    token = client.cookies.get(SESSION_COOKIE)
    assert client.post("/api/auth/logout").status_code == 204
    # The captured token is dead even though it has not expired.
    client.cookies.clear()
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_logout_requires_authentication(client):
    do_setup(client)
    client.cookies.clear()
    assert client.post("/api/auth/logout").status_code == 401


def test_tampered_and_garbage_tokens_rejected(client):
    do_setup(client)
    good = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    for bad in (good[:-3] + "abc", "garbage", ""):
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401
    # a validly signed token for a user that does not exist
    ghost = create_access_token(999, 0)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {ghost}"}).status_code == 401


def test_cross_origin_write_blocked(client):
    r = client.post(
        "/api/auth/setup", json=SETUP, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403
    assert client.get("/api/auth/status").json()["setup_required"] is True


def test_same_origin_write_allowed(client):
    r = client.post("/api/auth/setup", json=SETUP, headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 201


def test_unique_email_constraint_at_db_level(client, db):
    do_setup(client)
    db.add(User(email="me@example.com", password_hash="x", display_name="dup"))
    with pytest.raises(IntegrityError):
        db.commit()
