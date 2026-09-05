"""The reminder engine.

Two entry points:
  - `sync_reminder_state(db, assessment)` — called right after an assessment
    is created, or after its assessment_time changes. Marks any reminder
    whose trigger window has *already* passed as "sent" without actually
    notifying (a 24h-before notice is meaningless if there are only 3 hours
    left) — see the "OA created late" edge cases in the project plan. If this
    results in every reminder being moot, sends one immediate catch-up
    notification instead of leaving the user with no notice at all.

  - `check_reminders(db)` — called by the GitHub Actions cron tick (and can
    be called any time). For every pending assessment, sends whichever
    24h/6h/2h reminders are due and unsent. Because `sync_reminder_state`
    already marked born-moot reminders as sent at creation/update time, any
    reminder this function finds due-and-unsent is a *genuinely timely* one
    (or a catch-up after a downtime gap) — either way it deserves a real
    notification.

Never send a "hours before" style message once the assessment's start time
has itself already passed (e.g. after a long outage) — that reminder is
marked sent silently instead, same as a born-moot one.
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import Assessment
from .ntfy import send_ntfy

logger = logging.getLogger("reminders")

IST = ZoneInfo("Asia/Kolkata")

# (hours_before, sent_at column name, enabled column name, kind label)
OFFSETS = [
    (24, "reminder_24_sent_at", "remind_24h", "24h"),
    (6, "reminder_6_sent_at", "remind_6h", "6h"),
    (2, "reminder_2_sent_at", "remind_2h", "2h"),
]


def _as_utc(dt: datetime) -> datetime:
    """Postgres/psycopg always hands back tz-aware UTC datetimes, but defend
    against a naive one anyway (e.g. SQLite in tests doesn't round-trip
    tzinfo) rather than let a comparison crash the whole tick."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_time(dt_utc: datetime) -> str:
    return dt_utc.astimezone(IST).strftime("%I:%M %p").lstrip("0")


def _build_message(kind: str, assessment: Assessment) -> tuple[str, str, int, str]:
    """Returns (title, body, priority, tags)."""
    time_str = _fmt_time(_as_utc(assessment.assessment_time))
    lines_notes = f"\nNotes:\n{assessment.notes}\n" if assessment.notes else ""
    lines_link = f"\nOpen OA:\n{assessment.link}" if assessment.link else ""

    if kind == "24h":
        title = "OA TOMORROW"
        body = (
            f"{assessment.company}\n{assessment.title}\n\n"
            f"Tomorrow at {time_str}\n"
            f"{lines_notes}{lines_link}"
        ).strip()
        return title, body, 4, "calendar"

    if kind == "6h":
        title = "OA IN 6 HOURS"
        body = f"{assessment.company}\n{assessment.title}\n\n{time_str} today{lines_link}".strip()
        return title, body, 4, "clock3"

    if kind == "2h":
        title = "OA IN 2 HOURS"
        body = f"{assessment.company}\n{assessment.title}\n\n{time_str}\nGet ready.{lines_link}".strip()
        return title, body, 5, "rotating_light"

    # "immediate" catch-up: OA created (or moved) so close to start that none
    # of the normal windows had a chance to fire on time.
    title = "OA STARTING SOON"
    body = f"{assessment.company}\n{assessment.title}\n\n{time_str} today\nCheck the details now.{lines_link}".strip()
    return title, body, 5, "rotating_light"


def sync_reminder_state(db: Session, assessment: Assessment) -> None:
    """Call right after INSERT, or after an UPDATE that changed assessment_time."""
    now = datetime.now(timezone.utc)
    newly_mooted = []

    assessment_time = _as_utc(assessment.assessment_time)

    for hours, sent_col, enabled_col, kind in OFFSETS:
        if not getattr(assessment, enabled_col):
            continue
        if getattr(assessment, sent_col) is not None:
            continue
        trigger_time = assessment_time - timedelta(hours=hours)
        if now >= trigger_time:
            setattr(assessment, sent_col, now)
            newly_mooted.append(kind)

    db.commit()

    # "Exhausted" means every *enabled* reminder is now accounted for (sent or
    # moot) — a disabled reminder's perpetually-null sent_at shouldn't block
    # the immediate catch-up notification.
    all_exhausted = all(
        not getattr(assessment, enabled_col) or getattr(assessment, sent_col) is not None
        for _, sent_col, enabled_col, _ in OFFSETS
    )
    if newly_mooted and all_exhausted:
        title, body, priority, tags = _build_message("immediate", assessment)
        ok = send_ntfy(title, body, priority, click_url=assessment.link, tags=tags)
        logger.info(
            "immediate catch-up notification for assessment %s: sent=%s (windows %s already passed)",
            assessment.id, ok, newly_mooted,
        )


def check_reminders(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    summary = {"checked": 0, "sent": 0, "moot": 0, "skipped": 0, "failed": 0}

    rows = (
        db.query(Assessment)
        .filter(Assessment.completed.is_(False))
        .all()
    )

    for row in rows:
        summary["checked"] += 1
        row_time = _as_utc(row.assessment_time)
        already_started = now >= row_time

        for hours, sent_col, enabled_col, kind in OFFSETS:
            if getattr(row, sent_col) is not None:
                continue
            if not getattr(row, enabled_col):
                continue
            trigger_time = row_time - timedelta(hours=hours)
            if now < trigger_time:
                continue  # not due yet

            if already_started:
                # Too late for an "in N hours" message to make sense.
                db.execute(
                    update(Assessment)
                    .where(Assessment.id == row.id, getattr(Assessment, sent_col).is_(None))
                    .values(**{sent_col: now})
                )
                db.commit()
                summary["moot"] += 1
                logger.info("assessment %s (%s): %s reminder moot, OA already started", row.id, row.title, kind)
                continue

            title, body, priority, tags = _build_message(kind, row)
            ok = send_ntfy(title, body, priority, click_url=row.link, tags=tags)
            if ok:
                result = db.execute(
                    update(Assessment)
                    .where(Assessment.id == row.id, getattr(Assessment, sent_col).is_(None))
                    .values(**{sent_col: now})
                )
                db.commit()
                if result.rowcount:
                    summary["sent"] += 1
                    logger.info("assessment %s (%s): %s reminder sent", row.id, row.title, kind)
                else:
                    # Another concurrent tick already sent+marked this one.
                    summary["skipped"] += 1
                    logger.info("assessment %s (%s): %s reminder already sent by a concurrent tick", row.id, row.title, kind)
            else:
                logger.warning("assessment %s (%s): %s reminder ntfy send failed; will retry next tick", row.id, row.title, kind)
                summary["failed"] += 1

    return summary
