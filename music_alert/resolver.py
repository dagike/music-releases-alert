from __future__ import annotations

import logging
import time

from .artists_file import ArtistEntry, normalize
from .deezer import DeezerClient, DeezerError
from .models import Resolution
from .store import Store

OK_TTL = 30 * 24 * 3600  # look up a good match again after 30 days
NOT_FOUND_TTL = 24 * 3600  # try a missing artist again after 1 day
# Two artists with the exact same name count as ambiguous when the runner-up
# has at least this share of the top artist's fans.
RUNNER_UP_RATIO = 0.10

log = logging.getLogger(__name__)


def _candidate(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "name": item.get("name", ""),
        "fans": item.get("nb_fan") or 0,
        "link": item.get("link") or f"https://www.deezer.com/artist/{item.get('id')}",
    }


def _from_candidate(entry: ArtistEntry, cand: dict, candidates: list[dict], now: float,
                    ambiguous: bool = False, reason: str = "") -> Resolution:
    return Resolution(
        key=entry.key, label=entry.label, status="ok", artist_id=cand["id"],
        name=cand["name"], link=cand["link"], fans=cand["fans"], ambiguous=ambiguous,
        reason=reason, candidates=candidates, resolved_at=now,
    )


def lookup(entry: ArtistEntry, deezer: DeezerClient, now: float) -> Resolution:
    """Ask Deezer who this entry is. Raises DeezerError on a lookup problem."""
    if entry.artist_id is not None:  # pinned ID: no ambiguity possible
        data = deezer.get_artist(entry.artist_id)
        if data is None:
            return Resolution(
                key=entry.key, label=entry.label, status="not_found", resolved_at=now,
                reason=f"No Deezer artist has ID {entry.artist_id}.",
            )
        cand = _candidate(data)
        return _from_candidate(entry, cand, [cand], now)

    results = deezer.search_artist(entry.name or "")
    candidates = [_candidate(r) for r in results]
    if not candidates:
        return Resolution(
            key=entry.key, label=entry.label, status="not_found", resolved_at=now,
            reason=f"Deezer search returned no artists for '{entry.name}'.",
        )

    wanted = normalize(entry.name or "")
    exact = sorted(
        (c for c in candidates if normalize(c["name"]) == wanted),
        key=lambda c: c["fans"],
        reverse=True,
    )
    if not exact:
        top = candidates[0]
        reason = f"No exact name match. Used the closest result, '{top['name']}'."
        return _from_candidate(entry, top, candidates, now, True, reason)

    top = exact[0]
    if len(exact) > 1 and exact[1]["fans"] >= RUNNER_UP_RATIO * top["fans"]:
        reason = f"{len(exact)} artists share the exact name '{entry.name}'. Used the one with most fans."
        return _from_candidate(entry, top, candidates, now, True, reason)
    return _from_candidate(entry, top, candidates, now)


def resolve(entry: ArtistEntry, deezer: DeezerClient, store: Store,
            now: float | None = None) -> Resolution:
    """Return a cached resolution, or look it up and cache it."""
    now = time.time() if now is None else now
    cached = store.get_artist(entry.key)
    if cached is not None:
        ttl = OK_TTL if cached.status == "ok" else NOT_FOUND_TTL
        if now - cached.resolved_at < ttl:
            return cached
    try:
        fresh = lookup(entry, deezer, now)
    except DeezerError:
        if cached is not None and cached.status == "ok":
            log.warning("Lookup for %s failed. Using the older cached match.", entry.label)
            return cached
        raise
    store.save_artist(fresh)
    return fresh
