"""Pydantic request/response schemas + input validation."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _require_timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError(
            "assessment_time must include a timezone offset (e.g. "
            "'2026-09-08T10:00:00+05:30'), not a naive datetime."
        )
    return value


class AssessmentBase(BaseModel):
    company: str
    title: str
    assessment_time: datetime
    link: Optional[str] = None
    notes: Optional[str] = None
    remind_24h: bool = True
    remind_6h: bool = True
    remind_2h: bool = True

    @field_validator("company", "title")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("assessment_time")
    @classmethod
    def _tz_aware(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value)

    @field_validator("link")
    @classmethod
    def _valid_link(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        value = value.strip()
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("link must start with http:// or https://")
        return value


class AssessmentCreate(AssessmentBase):
    pass


class AssessmentUpdate(BaseModel):
    """All fields optional — PUT applies only the fields provided."""

    company: Optional[str] = None
    title: Optional[str] = None
    assessment_time: Optional[datetime] = None
    link: Optional[str] = None
    notes: Optional[str] = None
    remind_24h: Optional[bool] = None
    remind_6h: Optional[bool] = None
    remind_2h: Optional[bool] = None

    @field_validator("company", "title")
    @classmethod
    def _not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("assessment_time")
    @classmethod
    def _tz_aware(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return value
        return _require_timezone_aware(value)

    @field_validator("link")
    @classmethod
    def _valid_link(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value.strip() == "":
            return None
        value = value.strip()
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("link must start with http:// or https://")
        return value


class AssessmentOut(AssessmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reminder_24_sent_at: Optional[datetime] = None
    reminder_6_sent_at: Optional[datetime] = None
    reminder_2_sent_at: Optional[datetime] = None
    completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
