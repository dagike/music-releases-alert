from __future__ import annotations

import json
import sqlite3
import time

from .models import Release, Resolution

SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    status TEXT NOT NULL,
    artist_id INTEGER,
    name TEXT,
    link TEXT,
    fans INTEGER NOT NULL DEFAULT 0,
    ambiguous INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    candidates_json TEXT NOT NULL DEFAULT '[]',
    resolved_at REAL NOT NULL,
    warned INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS releases (
    album_id INTEGER PRIMARY KEY,
    artist_id INTEGER NOT NULL,
    title TEXT,
    release_date TEXT,
    status TEXT NOT NULL,
    recorded_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artist_state (
    artist_id INTEGER PRIMARY KEY,
    initialized_at REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- artist cache -------------------------------------------------

    def get_artist(self, key: str) -> Resolution | None:
        row = self.db.execute("SELECT * FROM artists WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return Resolution(
            key=row["key"],
            label=row["label"],
            status=row["status"],
            artist_id=row["artist_id"],
            name=row["name"],
            link=row["link"],
            fans=row["fans"],
            ambiguous=bool(row["ambiguous"]),
            reason=row["reason"],
            candidates=json.loads(row["candidates_json"]),
            resolved_at=row["resolved_at"],
            warned=bool(row["warned"]),
        )

    def save_artist(self, res: Resolution) -> None:
        """Save a resolution. Keep the "warned" flag if nothing important changed."""
        old = self.get_artist(res.key)
        same = (
            old is not None
            and old.status == res.status
            and old.artist_id == res.artist_id
            and old.ambiguous == res.ambiguous
        )
        res.warned = bool(old.warned) if same else False
        self.db.execute(
            """INSERT OR REPLACE INTO artists
               (key, label, status, artist_id, name, link, fans, ambiguous, reason,
                candidates_json, resolved_at, warned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                res.key, res.label, res.status, res.artist_id, res.name, res.link,
                res.fans, int(res.ambiguous), res.reason, json.dumps(res.candidates),
                res.resolved_at, int(res.warned),
            ),
        )
        self.db.commit()

    def mark_warned(self, key: str) -> None:
        self.db.execute("UPDATE artists SET warned = 1 WHERE key = ?", (key,))
        self.db.commit()

    # --- releases -----------------------------------------------------

    def has_release(self, album_id: int) -> bool:
        row = self.db.execute("SELECT 1 FROM releases WHERE album_id = ?", (album_id,)).fetchone()
        return row is not None

    def add_release(self, rel: Release, status: str) -> None:
        self.db.execute(
            """INSERT OR IGNORE INTO releases
               (album_id, artist_id, title, release_date, status, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rel.album_id, rel.artist_id, rel.title, rel.release_date, status, time.time()),
        )
        self.db.commit()

    def artist_initialized(self, artist_id: int) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM artist_state WHERE artist_id = ?", (artist_id,)
        ).fetchone()
        return row is not None

    def mark_initialized(self, artist_id: int) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO artist_state (artist_id, initialized_at) VALUES (?, ?)",
            (artist_id, time.time()),
        )
        self.db.commit()
