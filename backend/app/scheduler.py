"""In-process scheduler: once a minute, send whatever e-mail is due. Only runs when SCHEDULER_MODE=internal.
Use SCHEDULER_MODE=n8n to drive the same logic from n8n via POST /api/automation/run-due instead (never both)."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.database import SessionLocal
from app.services import mailer as mail
from app.services import notifications

log = logging.getLogger("hub.scheduler")


def tick() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        try:
            rows = notifications.run_due(db, mail.build_mailer(settings), settings.frontend_url)
            if rows:
                log.info("e-mail run: %s", ", ".join(f"{r.type}={r.status}" for r in rows))
        except Exception:  # never let one bad run kill the scheduler
            log.exception("e-mail run failed")
            db.rollback()


def start() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(tick, "interval", minutes=1, id="email-due", max_instances=1, coalesce=True)
    sched.start()
    return sched
