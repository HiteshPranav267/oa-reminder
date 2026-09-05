from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.models import Assessment
from backend.services import reminders as reminders_module
from backend.services.reminders import check_reminders, sync_reminder_state

IST = ZoneInfo("Asia/Kolkata")


def _make_assessment(**overrides) -> Assessment:
    defaults = dict(
        company="TestCo",
        title="Test OA",
        assessment_time=datetime.now(timezone.utc) + timedelta(days=2),
        remind_24h=True,
        remind_6h=True,
        remind_2h=True,
        completed=False,
    )
    defaults.update(overrides)
    return Assessment(**defaults)


# ---------------------------------------------------------------------------
# Pure trigger-time math — the user's worked example: OA at 10:00 AM IST.
# ---------------------------------------------------------------------------

def test_trigger_times_worked_example():
    oa_time = datetime(2026, 9, 8, 10, 0, tzinfo=IST)

    trigger_24h = oa_time - timedelta(hours=24)
    trigger_6h = oa_time - timedelta(hours=6)
    trigger_2h = oa_time - timedelta(hours=2)

    assert trigger_24h.astimezone(IST) == datetime(2026, 9, 7, 10, 0, tzinfo=IST)
    assert trigger_6h.astimezone(IST) == datetime(2026, 9, 8, 4, 0, tzinfo=IST)
    assert trigger_2h.astimezone(IST) == datetime(2026, 9, 8, 8, 0, tzinfo=IST)


def test_timezone_boundary_crossing_midnight_utc():
    # 12:30 AM IST is 7:00 PM UTC the *previous* day — a good boundary case
    # since IST and UTC disagree on which calendar day it is.
    oa_time = datetime(2026, 9, 8, 0, 30, tzinfo=IST)
    trigger_24h = oa_time - timedelta(hours=24)

    assert trigger_24h.astimezone(timezone.utc) == oa_time.astimezone(timezone.utc) - timedelta(hours=24)
    assert trigger_24h.astimezone(IST) == datetime(2026, 9, 7, 0, 30, tzinfo=IST)


# ---------------------------------------------------------------------------
# sync_reminder_state — the "created/moved close to start time" logic.
# ---------------------------------------------------------------------------

def test_sync_marks_nothing_when_far_in_future(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: sent.append(1) or True)

    obj = _make_assessment(assessment_time=datetime.now(timezone.utc) + timedelta(hours=30))
    db_session.add(obj)
    db_session.commit()

    sync_reminder_state(db_session, obj)

    assert obj.reminder_24_sent_at is None
    assert obj.reminder_6_sent_at is None
    assert obj.reminder_2_sent_at is None
    assert sent == []


def test_sync_marks_24h_and_6h_moot_when_created_3h_out(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: sent.append(1) or True)

    obj = _make_assessment(assessment_time=datetime.now(timezone.utc) + timedelta(hours=3))
    db_session.add(obj)
    db_session.commit()

    sync_reminder_state(db_session, obj)

    assert obj.reminder_24_sent_at is not None
    assert obj.reminder_6_sent_at is not None
    assert obj.reminder_2_sent_at is None  # still in the future, will fire normally later
    assert sent == []  # moot marks are silent, no notification


def test_sync_sends_immediate_when_created_minutes_out(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: sent.append(1) or True)

    obj = _make_assessment(assessment_time=datetime.now(timezone.utc) + timedelta(minutes=5))
    db_session.add(obj)
    db_session.commit()

    sync_reminder_state(db_session, obj)

    assert obj.reminder_24_sent_at is not None
    assert obj.reminder_6_sent_at is not None
    assert obj.reminder_2_sent_at is not None
    assert sent == [1]  # exactly one immediate catch-up notification


def test_sync_respects_disabled_reminders(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: sent.append(1) or True)

    obj = _make_assessment(
        assessment_time=datetime.now(timezone.utc) + timedelta(minutes=5),
        remind_24h=False,
        remind_6h=False,
        remind_2h=False,
    )
    db_session.add(obj)
    db_session.commit()

    sync_reminder_state(db_session, obj)

    # Nothing enabled -> nothing marked, and no notification (respecting the
    # user's explicit choice to turn every reminder off for this OA).
    assert obj.reminder_24_sent_at is None
    assert obj.reminder_6_sent_at is None
    assert obj.reminder_2_sent_at is None
    assert sent == []


# ---------------------------------------------------------------------------
# check_reminders — the tick logic.
# ---------------------------------------------------------------------------

def test_check_reminders_skips_not_due(db_session, monkeypatch):
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: True)

    # Far enough out that none of the 24h/6h/2h windows have opened yet.
    obj = _make_assessment(assessment_time=datetime.now(timezone.utc) + timedelta(hours=30))
    db_session.add(obj)
    db_session.commit()

    summary = check_reminders(db_session)
    assert summary == {"checked": 1, "sent": 0, "moot": 0, "skipped": 0, "failed": 0}


def test_check_reminders_skips_completed(db_session, monkeypatch):
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: True)

    obj = _make_assessment(
        assessment_time=datetime.now(timezone.utc) + timedelta(hours=1),
        completed=True,
    )
    db_session.add(obj)
    db_session.commit()

    summary = check_reminders(db_session)
    assert summary["checked"] == 0


def test_check_reminders_sends_when_due(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: calls.append(k) or True)

    # Simulates realistic post-creation state: 24h/6h were already handled
    # (sent or moot-marked by sync_reminder_state at creation time), and only
    # the 2h trigger has just newly opened (assessment is 1 hour away).
    now = datetime.now(timezone.utc)
    obj = _make_assessment(
        assessment_time=now + timedelta(hours=1),
        reminder_24_sent_at=now - timedelta(hours=20),
        reminder_6_sent_at=now - timedelta(hours=2),
    )
    db_session.add(obj)
    db_session.commit()

    summary = check_reminders(db_session)

    assert summary["sent"] == 1
    assert len(calls) == 1
    db_session.refresh(obj)
    assert obj.reminder_2_sent_at is not None  # newly sent by this tick
    assert obj.reminder_24_sent_at is not None  # unchanged (was pre-set)
    assert obj.reminder_6_sent_at is not None  # unchanged (was pre-set)


def test_check_reminders_does_not_resend_already_sent(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: calls.append(1) or True)

    now = datetime.now(timezone.utc)
    obj = _make_assessment(
        assessment_time=now + timedelta(hours=1),
        reminder_24_sent_at=now - timedelta(hours=20),
        reminder_6_sent_at=now - timedelta(hours=2),
    )
    db_session.add(obj)
    db_session.commit()

    check_reminders(db_session)
    assert len(calls) == 1

    # Second tick, same due window — must NOT send again.
    summary = check_reminders(db_session)
    assert summary["sent"] == 0
    assert len(calls) == 1


def test_check_reminders_marks_moot_without_sending_if_already_started(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: calls.append(1) or True)

    # Assessment start time itself is already in the past (e.g. after an outage).
    obj = _make_assessment(assessment_time=datetime.now(timezone.utc) - timedelta(minutes=5))
    db_session.add(obj)
    db_session.commit()

    summary = check_reminders(db_session)

    assert calls == []  # no "in N hours" message once it's already started
    assert summary["moot"] == 3
    db_session.refresh(obj)
    assert obj.reminder_24_sent_at is not None
    assert obj.reminder_6_sent_at is not None
    assert obj.reminder_2_sent_at is not None


def test_check_reminders_keeps_unsent_on_ntfy_failure(db_session, monkeypatch):
    monkeypatch.setattr(reminders_module, "send_ntfy", lambda *a, **k: False)

    now = datetime.now(timezone.utc)
    obj = _make_assessment(
        assessment_time=now + timedelta(hours=1),
        reminder_24_sent_at=now - timedelta(hours=20),
        reminder_6_sent_at=now - timedelta(hours=2),
    )
    db_session.add(obj)
    db_session.commit()

    summary = check_reminders(db_session)

    assert summary["failed"] == 1
    assert summary["sent"] == 0
    db_session.refresh(obj)
    assert obj.reminder_2_sent_at is None  # must be retried, not marked sent
