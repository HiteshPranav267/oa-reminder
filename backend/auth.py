"""Shared-secret API key check for mutating endpoints.

Personal single-user app: one secret (API_KEY env var), sent by the frontend
(and by the GitHub Actions cron ping, later) as the X-API-Key header. Reads
(GET) are left open since there's nothing sensitive in "OA at 10am" data.
"""
import os

from fastapi import Header, HTTPException, status

API_KEY = os.environ["API_KEY"]


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key header.",
        )
