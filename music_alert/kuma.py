from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


def push(url: str, ok: bool, msg: str, ping_ms: int | None = None,
         session: requests.Session | None = None) -> bool:
    """Send a heartbeat to an Uptime Kuma push monitor. Never raises.

    Does nothing when `url` is empty, so the feature is optional.
    """
    if not url:
        return False
    params: dict = {"status": "up" if ok else "down", "msg": msg[:200]}
    if ping_ms is not None:
        params["ping"] = ping_ms
    try:
        response = (session or requests).get(url, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Uptime Kuma push failed: %s", exc)
        return False
    return True
