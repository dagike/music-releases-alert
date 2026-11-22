from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime

from . import kuma
from .artists_file import read_artists_file
from .config import Config, load_config
from .deezer import DeezerClient, DeezerError
from .discord import Discord
from .resolver import resolve
from .run import run_cycle
from .scheduler import next_run
from .store import Store

log = logging.getLogger("music_alert")


def resolve_only(cfg: Config, store: Store, deezer: DeezerClient) -> int:
    """Print how each line of the artist file resolves. Sends nothing."""
    for entry in read_artists_file(cfg.artists_file):
        try:
            res = resolve(entry, deezer, store)
        except DeezerError as exc:
            print(f"ERROR      {entry.label}: {exc}")
            continue
        if res.status == "not_found":
            print(f"NOT FOUND  {entry.label}: {res.reason}")
            continue
        tag = "AMBIGUOUS " if res.ambiguous else "OK        "
        print(f"{tag} {entry.label} -> {res.name} (ID {res.artist_id}, {res.fans:,} fans)")
        if res.ambiguous:
            print(f"           {res.reason}")
            for cand in res.candidates[:5]:
                print(f"           - {cand['name']} (ID {cand['id']}, {cand['fans']:,} fans)")
    return 0


def checked_run(cfg: Config, store: Store, deezer: DeezerClient, discord: Discord) -> bool:
    """Run one cycle, then send an Uptime Kuma heartbeat (if configured)."""
    started = time.monotonic()
    try:
        result = run_cycle(cfg, store, deezer, discord)
    except Exception as exc:  # keep the server alive whatever happens in one run
        log.exception("Run failed.")
        kuma.push(cfg.kuma_push_url, False, f"Run failed: {exc}")
        return False
    msg = f"OK: {len(result.posted)} posted, {len(result.issues)} issue(s)"
    kuma.push(cfg.kuma_push_url, True, msg, int((time.monotonic() - started) * 1000))
    return True


def serve(cfg: Config, store: Store, deezer: DeezerClient, discord: Discord) -> None:
    def safe_run() -> None:
        checked_run(cfg, store, deezer, discord)

    if cfg.run_on_start:
        safe_run()
    last = datetime.now()
    while True:
        target = next_run(last, cfg.schedule)
        log.info("Next run at %s (server time).", target.strftime("%Y-%m-%d %H:%M"))
        while True:
            remaining = (target - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 30))  # short steps survive clock changes
        safe_run()
        last = max(datetime.now(), target)


def main() -> int:
    parser = argparse.ArgumentParser(prog="music_alert", description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one check, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="check once, log what would be posted, post and save nothing")
    parser.add_argument("--resolve-only", action="store_true",
                        help="match the artist file to Deezer IDs and print the result")
    args = parser.parse_args()

    cfg = load_config()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(message)s")

    offline = args.dry_run or args.resolve_only
    if not cfg.webhook_url and not offline:
        log.error("DISCORD_WEBHOOK_URL is not set.")
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(cfg.db_path)), exist_ok=True)
    store = Store(cfg.db_path)
    deezer = DeezerClient(delay_ms=cfg.request_delay_ms)
    discord = Discord(cfg.webhook_url) if cfg.webhook_url else None

    if args.resolve_only:
        return resolve_only(cfg, store, deezer)
    if args.dry_run:
        run_cycle(cfg, store, deezer, discord, dry_run=True)
        return 0
    if args.once:
        return 0 if checked_run(cfg, store, deezer, discord) else 1

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # clean stop in Docker
    serve(cfg, store, deezer, discord)
    return 0


if __name__ == "__main__":
    sys.exit(main())
