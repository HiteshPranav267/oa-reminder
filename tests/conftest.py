import sys
from pathlib import Path

from dotenv import load_dotenv

# So `backend.*` imports work when pytest is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# backend.database reads DATABASE_URL etc. at import time; .env supplies
# real-looking values so imports succeed. Tests never touch that engine —
# they use their own in-memory SQLite DB (see db_session fixture below).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend.models import Assessment, Base  # noqa: E402,F401


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
