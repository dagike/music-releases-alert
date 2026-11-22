from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(name: str) -> str:
    """Lowercase, strip accents, and collapse spaces so names compare fairly."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.casefold().replace("&", " and ")
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class ArtistEntry:
    name: str | None = None
    artist_id: int | None = None

    @property
    def key(self) -> str:
        if self.artist_id is not None:
            return f"id:{self.artist_id}"
        return f"name:{normalize(self.name or '')}"

    @property
    def label(self) -> str:
        return self.name or f"deezer:{self.artist_id}"


_ID_ONLY = re.compile(r"^deezer:\s*(\d+)$", re.IGNORECASE)
_COMMENT = re.compile(r"\s+#.*$")


def parse_line(raw: str) -> ArtistEntry | None:
    line = _COMMENT.sub("", raw.strip()).strip()
    if not line or line.startswith("#"):
        return None
    match = _ID_ONLY.match(line)
    if match:
        return ArtistEntry(artist_id=int(match.group(1)))
    if "|" in line:
        name, _, id_part = line.rpartition("|")
        if id_part.strip().isdigit() and name.strip():
            return ArtistEntry(name=name.strip(), artist_id=int(id_part.strip()))
    return ArtistEntry(name=line)


def parse_artists(text: str) -> list[ArtistEntry]:
    entries: dict[str, ArtistEntry] = {}
    for raw in text.splitlines():
        entry = parse_line(raw)
        if entry and entry.key not in entries:
            entries[entry.key] = entry
    return list(entries.values())


def read_artists_file(path: str) -> list[ArtistEntry]:
    with open(path, encoding="utf-8-sig") as handle:
        return parse_artists(handle.read())
