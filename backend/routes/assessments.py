"""CRUD endpoints for OAs."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..database import get_db
from ..models import Assessment
from ..schemas import AssessmentCreate, AssessmentOut, AssessmentUpdate
from ..services.reminders import sync_reminder_state

router = APIRouter(prefix="/api/assessments", tags=["assessments"])


def _get_or_404(db: Session, assessment_id: uuid.UUID) -> Assessment:
    obj = db.get(Assessment, assessment_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return obj


@router.get("", response_model=list[AssessmentOut])
def list_assessments(
    status_filter: Optional[Literal["upcoming", "past", "completed"]] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Assessment)
    now = datetime.now(timezone.utc)

    if status_filter == "upcoming":
        query = query.filter(Assessment.completed.is_(False), Assessment.assessment_time >= now)
    elif status_filter == "past":
        query = query.filter(Assessment.completed.is_(False), Assessment.assessment_time < now)
    elif status_filter == "completed":
        query = query.filter(Assessment.completed.is_(True))

    return query.order_by(Assessment.assessment_time.asc()).all()


@router.post("", response_model=AssessmentOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
def create_assessment(payload: AssessmentCreate, db: Session = Depends(get_db)):
    obj = Assessment(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)

    # Immediately evaluate: if any reminder windows already passed (OA
    # created late), mark them moot now rather than waiting for the next tick.
    sync_reminder_state(db, obj)
    db.refresh(obj)
    return obj


@router.get("/{assessment_id}", response_model=AssessmentOut)
def get_assessment(assessment_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_or_404(db, assessment_id)


@router.put("/{assessment_id}", response_model=AssessmentOut, dependencies=[Depends(require_api_key)])
def update_assessment(assessment_id: uuid.UUID, payload: AssessmentUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, assessment_id)

    updates = payload.model_dump(exclude_unset=True)
    time_changed = "assessment_time" in updates and updates["assessment_time"] != obj.assessment_time

    for field, value in updates.items():
        setattr(obj, field, value)

    if time_changed:
        # Reset sent-flags whose trigger window is now in the future so they
        # fire again; leave alone any whose window is still in the past
        # (moot either way — the tick logic marks those sent-without-notifying
        # on its next run, same as the "created late" case).
        for sent_field, hours in (
            ("reminder_24_sent_at", 24),
            ("reminder_6_sent_at", 6),
            ("reminder_2_sent_at", 2),
        ):
            trigger_time = obj.assessment_time - timedelta(hours=hours)
            if trigger_time > datetime.now(timezone.utc):
                setattr(obj, sent_field, None)

    db.commit()
    db.refresh(obj)

    if time_changed:
        # Handles the case where the new time is close enough that some
        # windows are already-passed again (same "created late" handling).
        sync_reminder_state(db, obj)
        db.refresh(obj)

    return obj


@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
def delete_assessment(assessment_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = _get_or_404(db, assessment_id)
    db.delete(obj)
    db.commit()


@router.post("/{assessment_id}/complete", response_model=AssessmentOut, dependencies=[Depends(require_api_key)])
def complete_assessment(assessment_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = _get_or_404(db, assessment_id)
    obj.completed = True
    obj.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj
