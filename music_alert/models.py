from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Resolution:
    """The result of matching one line of the artist file to a Deezer artist."""

    key: str
    label: str
    status: str  # "ok" or "not_found"
    artist_id: int | None = None
    name: str | None = None
    link: str | None = None
    fans: int = 0
    ambiguous: bool = False
    reason: str = ""
    candidates: list[dict] = field(default_factory=list)
    resolved_at: float = 0.0
    warned: bool = False

    @property
    def needs_alert(self) -> bool:
        return not self.warned and (self.status == "not_found" or self.ambiguous)


@dataclass
class Release:
    album_id: int
    artist_id: int
    artist_name: str
    title: str
    record_type: str
    release_date: str
    cover: str | None
    link: str | None
