"""Thin wrapper around ntfy's HTTP publish API.

Docs: https://docs.ntfy.sh/publish/

Publishing is a plain HTTP POST to {NTFY_SERVER}/{NTFY_TOPIC} with the message
body as plain text and metadata (title, priority, click URL, tags, action
buttons) as headers. No SDK needed.
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("ntfy")

NTFY_SERVER = os.environ["NTFY_SERVER"].rstrip("/")
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "").strip()


def _ascii_safe(value: str) -> str:
    """ntfy (like HTTP generally) expects header values to be ASCII/Latin-1.
    Company/title names could contain other characters (accents, em-dashes,
    emoji) — rather than let a 500 error block a reminder, drop anything
    that can't be represented so the notification still goes out.
    """
    return value.encode("ascii", errors="ignore").decode("ascii")


def send_ntfy(
    title: str,
    message: str,
    priority: int = 3,
    click_url: Optional[str] = None,
    tags: Optional[str] = None,
) -> bool:
    """Publish one ntfy notification. Returns True on success, False on any
    failure — never raises, so callers (the scheduler tick) can safely decide
    not to mark a reminder as sent when this returns False.
    """
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"

    headers = {
        "X-Title": _ascii_safe(title),
        "X-Priority": str(priority),
    }
    if click_url:
        headers["X-Click"] = click_url
    if tags:
        headers["X-Tags"] = tags
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

    try:
        response = httpx.post(
            url,
            content=message.encode("utf-8"),
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("ntfy publish failed: %s", exc)
        return False
