"""Authentication business rules: single-account setup, login with lockout, logout."""
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.database import utcnow
from app.models import LoginAttempt, User, UserSettings

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW = timedelta(minutes=15)
# Used to burn the same CPU time when the e-mail is unknown (prevents user enumeration by timing).
_DUMMY_HASH = hash_password("not-a-real-password-0")


class SetupAlreadyDone(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class LockedOut(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds


def setup_required(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(User)) == 0


def create_first_user(
    db: Session, *, email: str, password: str, display_name: str, timezone: str
) -> User:
    """Create the one and only account.

    Guarded twice: an application check, and a database guarantee — the first user is always
    inserted with id=1, so a concurrent second setup request fails on the primary key even if
    both passed the check at the same moment.
    """
    if not setup_required(db):
        raise SetupAlreadyDone()
    user = User(
        id=1,
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=display_name,
        timezone=timezone,
    )
    user.settings = UserSettings(reminder_email=email.lower())
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SetupAlreadyDone() from exc
    return user


def _recent_failures(db: Session, email: str):
    cutoff = utcnow() - LOCKOUT_WINDOW
    return db.scalars(
        select(LoginAttempt)
        .where(LoginAttempt.email == email, LoginAttempt.attempted_at >= cutoff)
        .order_by(LoginAttempt.attempted_at)
    ).all()


def authenticate(db: Session, *, email: str, password: str, ip: str | None) -> User:
    email = email.lower()
    failures = _recent_failures(db, email)
    if len(failures) >= MAX_FAILED_ATTEMPTS:
        unlock_at = failures[0].attempted_at + LOCKOUT_WINDOW
        raise LockedOut(max(1, int((unlock_at - utcnow()).total_seconds())))

    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        db.add(LoginAttempt(email=email, ip=ip))
        db.commit()
        raise InvalidCredentials()

    db.execute(delete(LoginAttempt).where(LoginAttempt.email == email))
    db.commit()
    return user


def revoke_sessions(db: Session, user: User) -> None:
    """Invalidate every issued token for this user (logout)."""
    user.session_version += 1
    db.commit()
