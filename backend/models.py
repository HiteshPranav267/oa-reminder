"""SQLAlchemy ORM model, mirroring schema.sql's `assessments` table."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Text, func

from .database import Base
from .db_types import GUID


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)

    company = Column(String, nullable=False)
    title = Column(String, nullable=False)
    assessment_time = Column(DateTime(timezone=True), nullable=False)
    link = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    remind_24h = Column(Boolean, nullable=False, default=True)
    remind_6h = Column(Boolean, nullable=False, default=True)
    remind_2h = Column(Boolean, nullable=False, default=True)

    reminder_24_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_6_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_2_sent_at = Column(DateTime(timezone=True), nullable=True)

    completed = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
