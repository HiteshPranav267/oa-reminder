"""FastAPI app entrypoint."""
import logging

from dotenv import load_dotenv

# Load .env for local development. In production (Render) real env vars are
# already set and there's no .env file, so this is a harmless no-op there.
load_dotenv()

# INFO-level logs (reminder send/moot/skip decisions) are useful in Render's
# log stream for diagnosing missed/duplicate notifications; the default
# level is WARNING, which would silently swallow them.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from pathlib import Path  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .routes import assessments, ntfy, scheduler  # noqa: E402

app = FastAPI(title="OA Reminder System")

app.include_router(assessments.router)
app.include_router(ntfy.router)
app.include_router(scheduler.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Mounted last, and at "/", so it doesn't shadow the /api/* routes above.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
