"""E-mail reminders: content, honesty of statuses, idempotency, timing, retries, settings, endpoints (with a fake mail server)."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models import EmailNotification, User
from app.routers.notifications import get_mailer
from app.services import mailer as mail
from app.services import notifications as svc

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
URL = "http://localhost:5173"
KOLKATA = ZoneInfo("Asia/Kolkata")


class FakeMailer:
    provider = "smtp"

    def __init__(self, fail: str | None = None):
        self.sent: list[tuple] = []
        self.fail = fail

    def send(self, to, subject, html, text):
        if self.fail:
            raise mail.MailError(self.fail)
        self.sent.append((to, subject, html, text))
        return f"<id{len(self.sent)}@fake>"


def local(h, m=0, day=2, month=12):  # a Tuesday in Asia/Kolkata, as UTC
    return datetime(2026, month, day, h, m, tzinfo=KOLKATA).astimezone(timezone.utc)


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    yield client
    app.dependency_overrides.pop(get_mailer, None)


def use(m):
    app.dependency_overrides[get_mailer] = lambda: m


def the_user(db) -> User:
    return db.scalars(select(User)).one()


def add_task(c, title, due):
    r = c.post("/api/tasks", json={"title": title, "due_date": due})
    assert r.status_code == 201, r.text


# ---------------- sending and honesty ----------------

def test_a_plan_email_is_sent_once_and_recorded_as_sent_only_after_the_server_accepted(c, db):
    add_task(c, "Write the retrieval step", "2026-12-02")
    user, m = the_user(db), FakeMailer()
    row = svc.send(db, user, "daily_plan", m, URL, local(7))
    assert (row.status, row.recipient, row.attempts) == ("sent", "me@example.com", 1) and row.provider_message_id == "<id1@fake>"
    assert len(m.sent) == 1 and "Write the retrieval step" in m.sent[0][2]
    again = svc.send(db, user, "daily_plan", m, URL, local(9))
    assert again.id == row.id and len(m.sent) == 1                      # same day: no second e-mail


def test_a_mail_server_failure_is_recorded_as_failed_with_a_reason_not_sent(c, db):
    add_task(c, "Task", "2026-12-02")
    row = svc.send(db, the_user(db), "daily_plan", FakeMailer(fail="The mail server rejected the username or password."), URL, local(7))
    assert row.status == "failed" and "password" in row.error and row.sent_at is None and row.attempts == 1


def test_no_mail_configuration_is_skipped_with_a_reason_never_sent(c, db):
    add_task(c, "Task", "2026-12-02")
    row = svc.send(db, the_user(db), "daily_plan", None, URL, local(7))
    assert row.status == "skipped" and "isn't configured" in row.error and row.sent_at is None


def test_nothing_to_report_means_no_email(c, db):
    m = FakeMailer()
    assert c.post("/api/challenges/excuse", json={"reason": "Day off, travelling"}).status_code == 200   # today's challenge handled, plan empty
    row = svc.send(db, the_user(db), "overdue", m, URL)
    assert row.status == "skipped" and "Nothing to report" in row.error and m.sent == []
    assert svc.send(db, the_user(db), "daily_plan", m, URL).status == "skipped"


def test_an_open_daily_challenge_alone_is_worth_an_email(c, db):
    m = FakeMailer()
    row = svc.send(db, the_user(db), "overdue", m, URL)
    assert row.status == "sent" and "daily challenge" in m.sent[0][1].lower()


def test_text_you_wrote_is_escaped_in_the_email(c, db):
    add_task(c, "<script>alert(1)</script>", "2026-12-02")
    m = FakeMailer()
    svc.send(db, the_user(db), "daily_plan", m, URL, local(7))
    assert "<script>" not in m.sent[0][2] and "&lt;script&gt;" in m.sent[0][2]


def test_a_failed_send_can_be_retried_and_then_succeeds_without_a_duplicate_row(c, db):
    add_task(c, "Task", "2026-12-02")
    user = the_user(db)
    svc.send(db, user, "daily_plan", FakeMailer(fail="down"), URL, local(7))
    row = svc.send(db, user, "daily_plan", FakeMailer(), URL, local(7, 30))
    assert row.status == "sent" and row.attempts == 2
    assert len(db.scalars(select(EmailNotification)).all()) == 1


def test_weekly_report_summarises_the_week(c, db):
    add_task(c, "Task", "2026-12-02")
    m = FakeMailer()
    row = svc.send(db, the_user(db), "weekly_report", m, URL, local(18, day=6))
    assert row.status == "sent" and row.period_key == "2026-W49" and "Your week" in m.sent[0][1] and "Daily challenge" in m.sent[0][2]


# ---------------- timing and the scheduler ----------------

def enable(c, **kw):
    r = c.patch("/api/notifications/settings", json={"email_enabled": True, "reminder_email": "me@example.com", **kw})
    assert r.status_code == 200, r.text


def test_nothing_is_due_until_reminders_are_switched_on(c, db):
    assert svc.due_types(the_user(db), local(23)) == []


def test_due_types_follow_the_users_local_time(c, db):
    enable(c)
    db.expire_all()
    u = the_user(db)
    assert svc.due_types(u, local(6, 59)) == []
    assert svc.due_types(u, local(7)) == ["daily_plan"]
    assert svc.due_types(u, local(18)) == ["daily_plan", "overdue"]
    assert svc.due_types(u, local(18, day=6)) == ["daily_plan", "overdue", "weekly_report"]   # Sunday


def test_a_user_can_turn_off_overdue_and_weekly_emails(c, db):
    enable(c, overdue_reminders_enabled=False, weekly_report_enabled=False)
    db.expire_all()
    assert svc.due_types(the_user(db), local(18, day=6)) == ["daily_plan"]


def test_run_due_sends_each_type_once_even_when_called_every_minute(c, db):
    add_task(c, "Task", "2026-12-02")
    enable(c)
    db.expire_all()
    m = FakeMailer()
    first = svc.run_due(db, m, URL, local(18))
    assert sorted(r.type for r in first) == ["daily_plan", "overdue"] and len(m.sent) == 2
    assert svc.run_due(db, m, URL, local(18, 1)) == [] and len(m.sent) == 2


def test_run_due_retries_a_failed_send_only_after_a_pause_and_only_three_times(c, db):
    add_task(c, "Task", "2026-12-02")
    enable(c, overdue_reminders_enabled=False)
    db.expire_all()
    bad = FakeMailer(fail="down")
    t = local(7)
    assert svc.run_due(db, bad, URL, t)[0].status == "failed"
    assert svc.run_due(db, bad, URL, t + timedelta(minutes=2)) == []                   # too soon
    assert svc.run_due(db, bad, URL, t + timedelta(minutes=11))[0].attempts == 2
    assert svc.run_due(db, bad, URL, t + timedelta(minutes=22))[0].attempts == 3
    assert svc.run_due(db, bad, URL, t + timedelta(minutes=40)) == []                  # gave up
    good = FakeMailer()
    assert svc.run_due(db, good, URL, t + timedelta(minutes=60)) == [] and good.sent == []


def test_the_next_day_gets_a_new_email(c, db):
    add_task(c, "Task", "2026-12-02")
    add_task(c, "Task 2", "2026-12-03")
    enable(c, overdue_reminders_enabled=False)
    db.expire_all()
    m = FakeMailer()
    svc.run_due(db, m, URL, local(7))
    svc.run_due(db, m, URL, local(7, day=3))
    assert len(m.sent) == 2


# ---------------- HTTP ----------------

@pytest.mark.parametrize("method, path", [("get", "/api/notifications"), ("get", "/api/notifications/settings"), ("patch", "/api/notifications/settings"),
                                          ("get", "/api/notifications/preview/daily_plan"), ("post", "/api/notifications/test"),
                                          ("post", "/api/notifications/run/daily_plan")])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_settings_default_off_and_report_whether_the_server_can_send(c):
    use(None)
    s = c.get("/api/notifications/settings").json()
    assert s["email_enabled"] is False and s["reminder_email"] == "me@example.com" and s["server_ready"] is False
    use(FakeMailer())
    assert c.get("/api/notifications/settings").json()["server_ready"] is True


@pytest.mark.parametrize("body", [{"reminder_time": "25:00"}, {"reminder_time": "7:00"}, {"weekly_report_day": 7}, {"reminder_email": "nope"}, {"surprise": 1}])
def test_settings_reject_bad_values(c, body):
    assert c.patch("/api/notifications/settings", json=body).status_code == 422


def test_settings_save_and_persist(c):
    r = c.patch("/api/notifications/settings", json={"email_enabled": True, "reminder_time": "06:45", "weekly_report_day": 0}).json()
    assert (r["email_enabled"], r["reminder_time"], r["weekly_report_day"]) == (True, "06:45", 0)
    assert c.get("/api/notifications/settings").json()["reminder_time"] == "06:45"


def test_test_email_endpoint_reports_the_real_outcome(c):
    use(FakeMailer())
    assert c.post("/api/notifications/test").json()["status"] == "sent"
    use(FakeMailer(fail="The mail server rejected the username or password."))
    r = c.post("/api/notifications/test").json()
    assert r["status"] == "failed" and "password" in r["error"]
    use(None)
    assert c.post("/api/notifications/test").json()["status"] == "skipped"
    assert [x["type"] for x in c.get("/api/notifications").json()] == ["test", "test", "test"]


def test_preview_sends_and_records_nothing(c):
    m = FakeMailer()
    use(m)
    add_task(c, "Task", datetime.now(KOLKATA).date().isoformat())
    p = c.get("/api/notifications/preview/daily_plan").json()
    assert p["would_send"] is True and "Task" in p["html"]
    assert m.sent == [] and c.get("/api/notifications").json() == []
    assert c.get("/api/notifications/preview/bogus").status_code == 404


def test_run_endpoint_is_idempotent_for_a_day(c):
    m = FakeMailer()
    use(m)
    add_task(c, "Task", datetime.now(KOLKATA).date().isoformat())
    a = c.post("/api/notifications/run/daily_plan").json()
    b = c.post("/api/notifications/run/daily_plan").json()
    assert a["status"] == "sent" and a["id"] == b["id"] and len(m.sent) == 1
    assert c.post("/api/notifications/run/bogus").status_code == 404


def test_automation_endpoint_needs_the_key(client, monkeypatch):
    monkeypatch.setenv("AUTOMATION_API_KEY", "")
    get_settings.cache_clear()
    assert client.post("/api/automation/run-due").status_code == 503              # no key configured
    monkeypatch.setenv("AUTOMATION_API_KEY", "k" * 24)
    get_settings.cache_clear()
    try:
        assert client.post("/api/automation/run-due").status_code == 401
        assert client.post("/api/automation/run-due", headers={"X-Automation-Key": "wrong"}).status_code == 401
        client.post("/api/auth/setup", json=SETUP)
        use(FakeMailer())
        r = client.post("/api/automation/run-due", headers={"X-Automation-Key": "k" * 24})
        assert r.status_code == 200 and set(r.json()) == {"handled", "sent", "failed", "skipped"}
    finally:
        app.dependency_overrides.pop(get_mailer, None)
        monkeypatch.delenv("AUTOMATION_API_KEY")
        get_settings.cache_clear()


def test_mailer_is_built_only_with_smtp_and_credentials():
    class S:
        email_provider, smtp_host, smtp_port, smtp_username, smtp_password, email_from = "smtp", "h", 587, "u", "p", None
    assert mail.build_mailer(S).sender == "u"
    S.smtp_password = None
    assert mail.build_mailer(S) is None
    S.smtp_password, S.email_provider = "p", "none"
    assert mail.build_mailer(S) is None
