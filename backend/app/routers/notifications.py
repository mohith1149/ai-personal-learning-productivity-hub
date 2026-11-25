"""E-mail reminder settings, history, preview and manual send. Login required. `/automation/run-due` (n8n) uses the automation key."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.config import get_settings
from app.core.deps import CurrentUser, DbSession, require_automation_key
from app.models import EmailNotification
from app.schemas import notifications as s
from app.services import mailer as mail
from app.services import notifications as svc

router = APIRouter(prefix="/notifications", tags=["notifications"])
automation_router = APIRouter(prefix="/automation", tags=["automation"])


def get_mailer() -> mail.Mailer | None:
    """Replaced in tests. None when the server has no e-mail credentials."""
    return mail.build_mailer(get_settings())


MailerDep = Annotated["mail.Mailer | None", Depends(get_mailer)]


def _settings_out(db, user, mailer) -> dict:
    row = svc.get_settings_row(db, user)
    db.commit()
    out = {k: getattr(row, k) for k in s.SettingsOut.model_fields if k != "server_ready"}
    return {**out, "server_ready": mailer is not None}


@router.get("/settings", response_model=s.SettingsOut)
def get_notification_settings(user: CurrentUser, db: DbSession, mailer: MailerDep):
    return _settings_out(db, user, mailer)


@router.patch("/settings", response_model=s.SettingsOut)
def update_notification_settings(body: s.SettingsUpdate, user: CurrentUser, db: DbSession, mailer: MailerDep):
    row = svc.get_settings_row(db, user)
    data = body.model_dump(exclude_unset=True)
    if data.get("email_enabled") and not (data.get("reminder_email") or row.reminder_email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a reminder e-mail address before turning reminders on")
    for k, v in data.items():
        if k != "reminder_email" or v is not None:
            setattr(row, k, v)
    db.commit()
    return _settings_out(db, user, mailer)


@router.get("", response_model=list[s.NotificationOut])
def history(user: CurrentUser, db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 30):
    stmt = select(EmailNotification).where(EmailNotification.user_id == user.id).order_by(EmailNotification.id.desc()).limit(limit)
    return db.scalars(stmt).all()


@router.get("/preview/{kind}", response_model=s.PreviewOut)
def preview(kind: str, user: CurrentUser, db: DbSession):
    """What this e-mail would say right now. Sends nothing and records nothing."""
    if kind not in svc.TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown e-mail type")
    c = svc.render(db, user, kind, None, get_settings().frontend_url)
    return {"subject": c and c["subject"], "html": c and c["html"], "would_send": c is not None}


@router.post("/test", response_model=s.NotificationOut)
def test(user: CurrentUser, db: DbSession, mailer: MailerDep):
    return svc.send_test(db, user, mailer)


@router.post("/run/{kind}", response_model=s.NotificationOut)
def run(kind: str, user: CurrentUser, db: DbSession, mailer: MailerDep):
    """Send this e-mail now (once per day/week; a repeat returns the earlier result)."""
    if kind not in svc.TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown e-mail type")
    return svc.send(db, user, kind, mailer, get_settings().frontend_url)


@automation_router.post("/run-due", response_model=s.RunDueOut, dependencies=[Depends(require_automation_key)])
def run_due(db: DbSession, mailer: MailerDep):
    """For n8n (or any scheduler): send whatever is due for everyone. Idempotent."""
    rows = svc.run_due(db, mailer, get_settings().frontend_url)
    count = lambda st: sum(r.status == st for r in rows)  # noqa: E731
    return {"handled": len(rows), "sent": count("sent"), "failed": count("failed"), "skipped": count("skipped")}
