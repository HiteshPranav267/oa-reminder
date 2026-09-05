"""Stage 3 verification endpoint — confirms ntfy delivery works end-to-end
before the scheduler is built on top of it."""
from fastapi import APIRouter, Depends

from ..auth import require_api_key
from ..services.ntfy import send_ntfy

router = APIRouter(prefix="/api/ntfy", tags=["ntfy"])


@router.post("/test", dependencies=[Depends(require_api_key)])
def test_notification():
    ok = send_ntfy(
        title="OA Reminder - Test",
        message="If you're seeing this, ntfy is wired up correctly. 🎉",
        priority=3,
        tags="white_check_mark",
    )
    return {"sent": ok}
