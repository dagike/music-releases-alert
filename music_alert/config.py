from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from typing import Mapping

from .scheduler import parse_schedule

DEFAULT_SCHEDULE = "00:15,06:00,12:00,18:00"


@dataclass(frozen=True)
class Config:
    webhook_url: str
    schedule: list[time]
    request_delay_ms: int = 200
    artists_file: str = "data/artists.txt"
    db_path: str = "data/state.db"
    log_level: str = "INFO"
    run_on_start: bool = False


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    return Config(
        webhook_url=env.get("DISCORD_WEBHOOK_URL", "").strip(),
        schedule=parse_schedule(env.get("SCHEDULE", DEFAULT_SCHEDULE)),
        request_delay_ms=int(env.get("REQUEST_DELAY_MS", "200")),
        artists_file=env.get("ARTISTS_FILE", "data/artists.txt"),
        db_path=env.get("DB_PATH", "data/state.db"),
        log_level=env.get("LOG_LEVEL", "INFO").upper(),
        run_on_start=env.get("RUN_ON_START", "false").strip().lower() in ("1", "true", "yes"),
    )
