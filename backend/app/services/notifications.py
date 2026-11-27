"""E-mail reminders: daily plan, overdue nudge, weekly report.

Rules (the honest ones):
  * A row in `email_notifications` is `sent` ONLY after the mail server accepted the message. A failure is stored as `failed`
    with a plain-language reason. "Nothing to say" is stored as `skipped`; no empty e-mail is ever sent.
  * One e-mail per type per period (date, or ISO week for the weekly report). The unique key makes the scheduler safe to run
    twice, restart, or be called by n8n as well.
  * All user-written text is HTML-escaped. Nothing secret is ever put in an e-mail.
"""
from datetime import datetime, time, timedelta, timezone
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import user_now, user_today
from app.models import EmailNotification, User, UserSettings
from app.services import challenges, planner, prefs
from app.services.mailer import Mailer, MailError

MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=10)
TYPES = ("daily_plan", "overdue", "weekly_report")
KIND_LABEL = {"task": "Task", "lesson": "Lesson", "video": "Video", "topic": "Roadmap", "habit": "Habit", "project": "Project"}
NOT_CONFIGURED = "E-mail isn't configured on the server (set EMAIL_PROVIDER=smtp and the SMTP settings)"


class RuleError(ValueError):
    pass


def get_settings_row(db: Session, user: User) -> UserSettings:
    return prefs.settings_row(db, user)


# ============================== content ==============================


def _list_html(items: list[dict]) -> str:
    rows = ""
    for i in items:
        sub = f" ({escape(i['subtitle'])})" if i.get("subtitle") else ""
        rows += f"<li><b>{escape(KIND_LABEL.get(i['kind'], i['kind']))}</b>: {escape(i['title'])}{sub}</li>"
    return f"<ul>{rows}</ul>"


def _list_text(items: list[dict]) -> str:
    return "\n".join(f"- {KIND_LABEL.get(i['kind'], i['kind'])}: {i['title']}" for i in items)


def _wrap(title: str, body_html: str, url: str) -> str:
    return (f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:560px'><h2>{escape(title)}</h2>{body_html}"
            f"<p style='color:#64748b;font-size:12px'>Sent by your AI Learning Hub. <a href='{escape(url)}'>Open it</a></p></div>")


def render(db: Session, user: User, kind: str, now: datetime | None, frontend_url: str) -> dict | None:
    """{subject, html, text} for this type right now, or None when there is nothing worth e-mailing."""
    today = user_today(user, now)
    name = escape(user.display_name)
    if kind in ("daily_plan", "overdue"):
        plan = planner.build_day(db, user, today, now)
        chal = challenges.today_view(db, user, now)["challenge"]
        chal_open = chal is None or chal["status"] in ("planned", "in_progress")
        if kind == "daily_plan":
            items = [i for i in plan["items"] if i["status"] in ("overdue", "pending")]
            if not items and not chal_open:
                return None
            body = f"<p>Good morning {name}. You have <b>{len(items)}</b> item(s) on today's plan.</p>"
            body += _list_html(items) if items else ""
            body += "<p><b>Daily challenge:</b> not done yet. One real commit on an AI project today.</p>" if chal_open else ""
            text = f"You have {len(items)} item(s) today.\n{_list_text(items)}" + ("\nDaily challenge: not done yet." if chal_open else "")
            return {"subject": f"Your plan for {today.isoformat()}: {len(items)} to do", "html": _wrap("Today's plan", body, frontend_url), "text": text}
        late = [i for i in plan["items"] if i["status"] == "overdue"]
        pending = [i for i in plan["items"] if i["status"] == "pending"]
        if not late and not pending and not chal_open:
            return None
        body = f"<p>{name}, here is what is still open today.</p>"
        if late:
            body += f"<p><b>Overdue ({len(late)})</b></p>{_list_html(late)}"
        if pending:
            body += f"<p><b>Still to do today ({len(pending)})</b></p>{_list_html(pending)}"
        if chal_open:
            body += "<p><b>Daily challenge:</b> no commit recorded yet today.</p>"
        text = f"Still open today: {len(late)} overdue, {len(pending)} pending." + ("\nDaily challenge: no commit yet." if chal_open else "")
        subject = f"Still open today: {len(late) + len(pending)} item(s)" + (" and your daily challenge" if chal_open else "")
        return {"subject": subject, "html": _wrap("Still open today", body, frontend_url), "text": text}
    if kind == "weekly_report":
        start = today - timedelta(days=today.weekday())
        rows, tot, done = "", 0, 0
        for n in range((today - start).days + 1):
            d = start + timedelta(days=n)
            sm = planner.build_day(db, user, d, now)["summary"]
            tot += sm["total"]
            done += sm["completed"]
            rows += f"<tr><td>{d.strftime('%a %d %b')}</td><td>{sm['completed']}/{sm['total']}</td><td>{sm['percent']}%</td></tr>"
        cal = challenges.calendar(db, user, start, today, now)
        c_done = sum(x["status"] == "completed" for x in cal["days"])
        c_missed = sum(x["status"] == "missed" for x in cal["days"])
        streak = cal["stats"]["current_streak"]
        pct = (100 * done) // tot if tot else 0
        body = (f"<p>{name}, your week ({start.isoformat()} to {today.isoformat()}):</p>"
                f"<p><b>{done}</b> of <b>{tot}</b> planned items completed ({pct}%).</p>"
                f"<table cellpadding='4'><tr><th align=left>Day</th><th>Done</th><th>%</th></tr>{rows}</table>"
                f"<p><b>Daily challenge:</b> {c_done} completed, {c_missed} missed. Current streak {streak} day(s).</p>")
        text = f"Week {start.isoformat()} to {today.isoformat()}: {done}/{tot} items ({pct}%). Challenge: {c_done} done, {c_missed} missed, streak {streak}."
        return {"subject": f"Your week: {done}/{tot} done, challenge streak {streak}", "html": _wrap("Your weekly report", body, frontend_url), "text": text}
    raise RuleError("Unknown e-mail type")


def period_key(user: User, kind: str, now: datetime | None) -> str:
    today = user_today(user, now)
    if kind == "weekly_report":
        y, w, _ = today.isocalendar()
        return f"{y}-W{w:02d}"
    return today.isoformat()


# ============================== sending ==============================


def _row(db: Session, user: User, kind: str, key: str) -> EmailNotification | None:
    return db.scalar(select(EmailNotification).where(EmailNotification.user_id == user.id, EmailNotification.type == kind,
                                                     EmailNotification.period_key == key))


def send(db: Session, user: User, kind: str, mailer: Mailer | None, frontend_url: str, now: datetime | None = None, *, force: bool = False) -> EmailNotification:
    """Send one e-mail and record the outcome. Without `force` an already-sent period is returned untouched."""
    if kind not in TYPES:
        raise RuleError("Unknown e-mail type")
    now = now or datetime.now(timezone.utc)
    s = get_settings_row(db, user)
    key = period_key(user, kind, now)
    row = _row(db, user, kind, key)
    if row and row.status == "sent" and not force:
        return row
    if row is None:
        row = EmailNotification(user_id=user.id, type=kind, period_key=key, status="pending", attempts=0)
        db.add(row)
    row.recipient = s.reminder_email

    def done(status: str, error: str | None = None) -> EmailNotification:
        row.status, row.error, row.updated_at = status, error, now  # updated_at doubles as "time of the last attempt" for retry pacing
        db.commit()
        return row

    if mailer is None:
        return done("skipped", NOT_CONFIGURED)
    if not s.reminder_email:
        return done("skipped", "No reminder e-mail address is set")
    content = render(db, user, kind, now, frontend_url)
    if content is None:
        return done("skipped", "Nothing to report, so no e-mail was sent")
    row.subject, row.body_html, row.provider, row.attempts = content["subject"], content["html"], mailer.provider, row.attempts + 1
    try:
        row.provider_message_id = mailer.send(s.reminder_email, content["subject"], content["html"], content["text"])
    except MailError as e:
        return done("failed", str(e))
    row.sent_at = now
    return done("sent")


def send_test(db: Session, user: User, mailer: Mailer | None, now: datetime | None = None) -> EmailNotification:
    now = now or datetime.now(timezone.utc)
    s = get_settings_row(db, user)
    row = EmailNotification(user_id=user.id, type="test", period_key=now.isoformat(), status="pending", attempts=1, recipient=s.reminder_email,
                            subject="Test e-mail from your AI Learning Hub", provider=mailer.provider if mailer else None)
    db.add(row)
    if mailer is None:
        row.status, row.error = "skipped", NOT_CONFIGURED
    elif not s.reminder_email:
        row.status, row.error = "skipped", "No reminder e-mail address is set"
    else:
        try:
            row.provider_message_id = mailer.send(s.reminder_email, row.subject, "<p>If you can read this, e-mail reminders work.</p>",
                                                  "If you can read this, e-mail reminders work.")
            row.status, row.sent_at = "sent", now
        except MailError as e:
            row.status, row.error = "failed", str(e)
    db.commit()
    return row


# ============================== scheduling ==============================


def _at(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def due_types(user: User, now: datetime) -> list[str]:
    s, local = user.settings, user_now(user, now)
    if s is None or not s.email_enabled:
        return []
    out = []
    if local.time() >= _at(s.reminder_time):
        out.append("daily_plan")
    if s.overdue_reminders_enabled and local.time() >= _at(s.overdue_reminder_time):
        out.append("overdue")
    if s.weekly_report_enabled and local.weekday() == s.weekly_report_day and local.time() >= _at(s.weekly_report_time):
        out.append("weekly_report")
    return out


def run_due(db: Session, mailer: Mailer | None, frontend_url: str, now: datetime | None = None) -> list[EmailNotification]:
    """Send whatever is due for every user. Safe to call every minute: a type already handled this period is left alone, and a failed
    one is retried (at most MAX_ATTEMPTS, no sooner than RETRY_AFTER apart)."""
    now = now or datetime.now(timezone.utc)
    handled: list[EmailNotification] = []
    for user in db.scalars(select(User)).all():
        for kind in due_types(user, now):
            row = _row(db, user, kind, period_key(user, kind, now))
            if row is not None:
                recent = now - row.updated_at.replace(tzinfo=timezone.utc) < RETRY_AFTER
                if row.status != "failed" or row.attempts >= MAX_ATTEMPTS or recent:
                    continue
            handled.append(send(db, user, kind, mailer, frontend_url, now))
    return handled
