from datetime import date

import pytest

from music_alert.config import Config
from music_alert.deezer import DeezerError
from music_alert.discord import DiscordError
from music_alert.run import run_cycle
from music_alert.scheduler import parse_schedule
from music_alert.store import Store

TODAY = date(2026, 11, 22)


class FakeDeezer:
    def __init__(self, search=None, artists=None, albums=None, album_errors=None):
        self.search = search or {}
        self.artists = artists or {}
        self.albums = albums or {}
        self.album_errors = album_errors or {}
        self.search_calls = 0

    def search_artist(self, query):
        self.search_calls += 1
        return self.search.get(query, [])

    def get_artist(self, artist_id):
        return self.artists.get(artist_id)

    def artist_albums(self, artist_id):
        if artist_id in self.album_errors:
            raise DeezerError(self.album_errors[artist_id])
        return self.albums.get(artist_id, [])


class FakeDiscord:
    def __init__(self, fail=False, fail_summary=False):
        self.fail = fail
        self.fail_summary = fail_summary
        self.release_batches = []
        self.summaries = []
        self.embeds = []

    def send_summary(self, releases):
        if self.fail_summary:
            raise DiscordError("summary boom")
        self.summaries.append(list(releases))

    def send_releases(self, releases):
        if self.fail:
            raise DiscordError("boom")
        self.release_batches.append(list(releases))

    def send_embeds(self, embeds):
        self.embeds.extend(embeds)


def artist(id, name, fans=1000):
    return {"id": id, "name": name, "nb_fan": fans, "link": f"https://deezer/artist/{id}"}


def album(id, title, date_, kind="album"):
    return {"id": id, "title": title, "release_date": date_, "record_type": kind,
            "cover_xl": f"https://img/{id}.jpg", "link": f"https://deezer/album/{id}"}


@pytest.fixture
def setup(tmp_path):
    artists_file = tmp_path / "artists.txt"
    cfg = Config(webhook_url="x", schedule=parse_schedule("06:00"), artists_file=str(artists_file))
    store = Store(":memory:")
    return cfg, store, artists_file


def test_first_run_posts_only_this_year_then_nothing_repeats(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Justice\n")
    deezer = FakeDeezer(
        search={"Justice": [artist(1, "Justice")]},
        albums={1: [album(10, "Old", "2020-01-01"), album(11, "New", "2026-03-01", "ep")]},
    )
    discord = FakeDiscord()

    first = run_cycle(cfg, store, deezer, discord, today=TODAY)
    assert [r.title for r in first.posted] == ["New"]
    assert store.has_release(10)  # old one remembered as seeded

    second = run_cycle(cfg, store, deezer, discord, today=TODAY)
    assert second.posted == []
    assert len(discord.release_batches) == 1

    # A release that appears later is posted, even when it is not from this year.
    deezer.albums[1].append(album(12, "Later", "2026-11-20", "single"))
    third = run_cycle(cfg, store, deezer, discord, today=TODAY)
    assert [r.title for r in third.posted] == ["Later"]


def test_failed_post_is_retried_next_run(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Justice\n")
    deezer = FakeDeezer(search={"Justice": [artist(1, "Justice")]},
                        albums={1: [album(11, "New", "2026-03-01")]})

    failed = run_cycle(cfg, store, deezer, FakeDiscord(fail=True), today=TODAY)
    assert failed.posted == [] and failed.issues
    assert not store.has_release(11)

    ok = run_cycle(cfg, store, deezer, FakeDiscord(), today=TODAY)
    assert [r.title for r in ok.posted] == ["New"]


def test_dry_run_changes_nothing(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Justice\n")
    deezer = FakeDeezer(search={"Justice": [artist(1, "Justice")]},
                        albums={1: [album(11, "New", "2026-03-01"), album(10, "Old", "2020-01-01")]})
    result = run_cycle(cfg, store, deezer, None, dry_run=True, today=TODAY)
    assert [r.title for r in result.posted] == ["New"]
    assert not store.has_release(10) and not store.has_release(11)
    assert not store.artist_initialized(1)


def test_ambiguous_match_warns_once_and_uses_cache(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Genesis\n")
    deezer = FakeDeezer(
        search={"Genesis": [artist(1, "Genesis", 5000), artist(2, "Genesis", 4000)]},
        albums={1: []},
    )
    discord = FakeDiscord()
    run_cycle(cfg, store, deezer, discord, today=TODAY)
    assert len(discord.embeds) == 1 and "Ambiguous" in discord.embeds[0]["title"]

    run_cycle(cfg, store, deezer, discord, today=TODAY)
    assert len(discord.embeds) == 1  # no repeat warning
    assert deezer.search_calls == 1  # second run used the cache


def test_clear_winner_is_not_ambiguous(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Genesis\n")
    deezer = FakeDeezer(search={"Genesis": [artist(1, "Genesis", 500000), artist(2, "Genesis", 40)]})
    discord = FakeDiscord()
    run_cycle(cfg, store, deezer, discord, today=TODAY)
    assert discord.embeds == []


def test_not_found_and_fetch_errors_are_reported(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Nobody Here\nJustice\ndeezer:99\n")
    deezer = FakeDeezer(
        search={"Justice": [artist(1, "Justice")]},
        album_errors={1: "Deezer error 4: Quota limit exceeded"},
    )
    discord = FakeDiscord()
    result = run_cycle(cfg, store, deezer, discord, today=TODAY)
    text = " ".join(result.issues)
    assert "Nobody Here" in text and "Quota" in text and "deezer:99" in text
    assert len(discord.embeds) == 1 and discord.embeds[0]["title"].startswith("Problems")


def test_same_album_under_two_artists_posts_once(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("A | 1\nB | 2\n")
    deezer = FakeDeezer(
        artists={1: artist(1, "A"), 2: artist(2, "B")},
        albums={1: [album(50, "Collab", "2026-05-05")], 2: [album(50, "Collab", "2026-05-05")]},
    )
    result = run_cycle(cfg, store, deezer, FakeDiscord(), today=TODAY)
    assert len(result.posted) == 1


def test_summary_sent_once_with_only_posted_releases(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Justice\n")
    deezer = FakeDeezer(
        search={"Justice": [artist(1, "Justice")]},
        albums={1: [album(10, "Old", "2020-01-01"), album(11, "New", "2026-03-01")]},
    )
    discord = FakeDiscord()
    run_cycle(cfg, store, deezer, discord, today=TODAY)
    assert [[r.title for r in s] for s in discord.summaries] == [["New"]]

    run_cycle(cfg, store, deezer, discord, today=TODAY)  # nothing new: no summary
    assert len(discord.summaries) == 1


def test_no_summary_when_card_post_fails(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Justice\n")
    deezer = FakeDeezer(search={"Justice": [artist(1, "Justice")]},
                        albums={1: [album(11, "New", "2026-03-01")]})
    discord = FakeDiscord(fail=True)
    run_cycle(cfg, store, deezer, discord, today=TODAY)
    assert discord.summaries == []


def test_summary_failure_is_an_issue_and_keeps_releases_marked(setup):
    cfg, store, artists_file = setup
    artists_file.write_text("Justice\n")
    deezer = FakeDeezer(search={"Justice": [artist(1, "Justice")]},
                        albums={1: [album(11, "New", "2026-03-01")]})
    result = run_cycle(cfg, store, deezer, FakeDiscord(fail_summary=True), today=TODAY)
    assert any("summary" in issue for issue in result.issues)
    assert store.has_release(11)  # not posted again next run
