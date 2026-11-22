from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from .artists_file import read_artists_file
from .config import Config
from .deezer import DeezerClient, DeezerError
from .discord import (
    BATCH_SIZE, Discord, DiscordError, ambiguity_embed, problems_embed, summary_embeds,
)
from .models import Release, Resolution
from .resolver import resolve
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class CycleResult:
    posted: list[Release] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    alerts: list[Resolution] = field(default_factory=list)


def _to_release(album: dict, res: Resolution) -> Release:
    return Release(
        album_id=album["id"],
        artist_id=res.artist_id,
        artist_name=res.name or res.label,
        title=album.get("title", "Untitled"),
        record_type=album.get("record_type", "release"),
        release_date=album.get("release_date") or "",
        cover=album.get("cover_xl") or album.get("cover_big") or album.get("cover"),
        link=album.get("link") or f"https://www.deezer.com/album/{album['id']}",
    )


def run_cycle(cfg: Config, store: Store, deezer: DeezerClient, discord: Discord | None,
              dry_run: bool = False, today: date | None = None) -> CycleResult:
    """Check every artist once and post what is new."""
    result = CycleResult()
    year = str((today or date.today()).year)

    try:
        entries = read_artists_file(cfg.artists_file)
    except OSError as exc:
        result.issues.append(f"Cannot read the artist file `{cfg.artists_file}`: {exc}")
        entries = []
    log.info("Checking %d artist(s).", len(entries))

    # 1. Resolve names to Deezer artist IDs (cached).
    resolved: dict[int, Resolution] = {}
    for entry in entries:
        try:
            res = resolve(entry, deezer, store)
        except DeezerError as exc:
            result.issues.append(f"Could not look up **{entry.label}**: {exc}")
            continue
        if res.status == "not_found":
            log.warning("%s: %s", entry.label, res.reason)
            if res.needs_alert:
                result.alerts.append(res)
            continue
        if res.ambiguous:
            log.warning("%s: ambiguous. %s", entry.label, res.reason)
            if res.needs_alert:
                result.alerts.append(res)
        resolved.setdefault(res.artist_id, res)

    # 2. Find releases that we have not seen.
    pending: dict[int, Release] = {}
    for artist_id, res in resolved.items():
        try:
            albums = deezer.artist_albums(artist_id)
        except DeezerError as exc:
            result.issues.append(f"Could not fetch releases for **{res.name}** (ID {artist_id}): {exc}")
            continue
        first_run = not store.artist_initialized(artist_id)
        for album in albums:
            rel = _to_release(album, res)
            if store.has_release(rel.album_id) or rel.album_id in pending:
                continue
            if first_run and not rel.release_date.startswith(year):
                if not dry_run:
                    store.add_release(rel, "seeded")  # old release: remember, do not post
                continue
            pending[rel.album_id] = rel
        if first_run and not dry_run:
            store.mark_initialized(artist_id)

    releases = sorted(pending.values(), key=lambda r: (r.release_date, r.artist_name, r.title))
    log.info("%d new release(s) to post.", len(releases))

    # 3. Post them. A release is saved as posted only after Discord accepts it.
    if dry_run:
        for rel in releases:
            log.info("[dry run] %s - %s (%s, %s) %s",
                     rel.artist_name, rel.title, rel.record_type, rel.release_date, rel.link)
        result.posted = releases
    else:
        for start in range(0, len(releases), BATCH_SIZE):
            batch = releases[start:start + BATCH_SIZE]
            try:
                discord.send_releases(batch)
            except DiscordError as exc:
                result.issues.append(f"Discord rejected a release post: {exc}. Will retry next run.")
                break
            for rel in batch:
                store.add_release(rel, "posted")
            result.posted.extend(batch)

    # 3b. Send one grouped text summary of what was posted.
    if result.posted:
        if dry_run:
            for embed in summary_embeds(result.posted):
                log.info("[dry run] %s\n%s", embed["title"], embed["description"])
        else:
            try:
                discord.send_summary(result.posted)
            except DiscordError as exc:
                # The cards are already posted and saved, so do not undo that.
                result.issues.append(f"Discord rejected the summary: {exc}")

    # 4. Report problems and ambiguous matches.
    for res in result.alerts:
        if res.status == "not_found":
            result.issues.append(
                f"No Deezer artist found for **{res.label}**: {res.reason} "
                "Fix the name, or pin an ID with `Name | ID`."
            )
    if (result.issues or result.alerts) and not dry_run:
        embeds = [ambiguity_embed(r) for r in result.alerts if r.status == "ok"]
        if result.issues:
            embeds.append(problems_embed(result.issues))
        try:
            discord.send_embeds(embeds)
        except DiscordError as exc:
            log.error("Could not send the problem report to Discord: %s", exc)
        else:
            for res in result.alerts:
                store.mark_warned(res.key)
    for issue in result.issues:
        log.warning("Issue: %s", issue)
    return result
