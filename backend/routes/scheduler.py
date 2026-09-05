"""The reminder-tick endpoint, called externally by GitHub Actions cron
(~every 10 min) instead of running an in-process scheduler. See the project
plan's "Cost" section for why: it decouples reminder delivery from Render's
uptime and needs no keep-alive workaround.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..database import get_db
from ..services.reminders import check_reminders

logger = logging.getLogger("scheduler")

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.post("/tick", dependencies=[Depends(require_api_key)])
def tick(db: Session = Depends(get_db)):
    # If Supabase is temporarily unreachable, don't 500 — report it and let
    # the next GitHub Actions run (≤~10 min later) retry. Nothing gets marked
    # sent unless it actually was, so this is always safe to retry.
    try:
        return check_reminders(db)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this must never crash the tick
        logger.exception("scheduler tick failed")
        return {"error": str(exc), "checked": 0, "sent": 0, "moot": 0, "skipped": 0, "failed": 0}
