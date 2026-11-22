from __future__ import annotations

import logging
import time
from typing import Callable

import requests

from .models import Release, Resolution

BOT_NAME = "Release Alerts"
BATCH_SIZE = 10  # Discord allows 10 embeds per message
COLOR_RELEASE = 0xA238FF
COLOR_WARNING = 0xF0B232
COLOR_ERROR = 0xED4245

log = logging.getLogger(__name__)


class DiscordError(Exception):
    pass


def _type_label(record_type: str) -> str:
    record_type = (record_type or "release").lower()
    return {"ep": "EP", "compile": "Compilation"}.get(record_type, record_type.capitalize())


def release_embed(rel: Release) -> dict:
    embed: dict = {
        "title": rel.title[:256],
        "author": {"name": rel.artist_name[:256]},
        "color": COLOR_RELEASE,
        "fields": [
            {"name": "Type", "value": _type_label(rel.record_type), "inline": True},
            {"name": "Release date", "value": rel.release_date or "Unknown", "inline": True},
        ],
    }
    if rel.link:
        embed["url"] = rel.link
        embed["description"] = rel.link
    if rel.cover:
        embed["image"] = {"url": rel.cover}
    return embed


def ambiguity_embed(res: Resolution) -> dict:
    lines = [
        res.reason,
        f"Using **{res.name}** (ID {res.artist_id}, {res.fans:,} fans): {res.link}",
    ]
    others = [c for c in res.candidates if c["id"] != res.artist_id][:4]
    if others:
        lines.append("Other candidates:")
        lines += [f"- {c['name']} (ID {c['id']}, {c['fans']:,} fans) {c['link']}" for c in others]
    lines.append(f"If this is wrong, change the line in your artist file to `{res.label} | <correct ID>`.")
    return {
        "title": f"Ambiguous match: {res.label}",
        "description": "\n".join(lines)[:4000],
        "color": COLOR_WARNING,
    }


def problems_embed(lines: list[str]) -> dict:
    text = "\n".join(f"- {line}" for line in lines)
    if len(text) > 4000:
        text = text[:3990] + "\n..."
    return {"title": "Problems during release check", "description": text, "color": COLOR_ERROR}


class Discord:
    def __init__(self, webhook_url: str, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.url = webhook_url
        self.session = session or requests.Session()
        self._sleep = sleep

    def _post(self, embeds: list[dict]) -> None:
        payload = {"username": BOT_NAME, "embeds": embeds}
        for attempt in range(1, 6):
            try:
                response = self.session.post(self.url, json=payload, timeout=15)
            except requests.RequestException as exc:
                if attempt == 5:
                    raise DiscordError(f"network error: {exc}") from exc
                self._sleep(2 * attempt)
                continue
            if response.status_code == 429:
                try:
                    wait = float(response.json().get("retry_after", 2))
                except ValueError:
                    wait = 2.0
                self._sleep(wait + 0.1)
                continue
            if response.status_code >= 500 and attempt < 5:
                self._sleep(2 * attempt)
                continue
            if not response.ok:
                raise DiscordError(f"HTTP {response.status_code}: {response.text[:200]}")
            self._sleep(0.5)  # stay under Discord's webhook rate limit
            return
        raise DiscordError("gave up after repeated rate limits")

    def send_releases(self, releases: list[Release]) -> None:
        self._post([release_embed(r) for r in releases])

    def send_embeds(self, embeds: list[dict]) -> None:
        for start in range(0, len(embeds), BATCH_SIZE):
            self._post(embeds[start:start + BATCH_SIZE])
