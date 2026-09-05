"""SQLAlchemy engine/session setup.

Connects via Supabase's Supavisor Session Pooler (port 5432), not the Direct
Connection endpoint — Render's outbound networking is IPv4-only, and Supabase's
Direct Connection is IPv6 by default (would need Supabase's paid IPv4 add-on).
The Session Pooler is IPv4-compatible and behaves like a normal persistent
connection, which is what this long-lived FastAPI app needs.

DATABASE_URL should look like:
    postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]

# pool_pre_ping avoids handing out dead connections after Supabase or the
# pooler recycles one during Render's idle periods.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
