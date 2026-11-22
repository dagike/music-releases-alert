from music_alert.discord import summary_embeds
from music_alert.models import Release


def rel(album_id, artist, title, date="2026-01-01", link="https://deezer/album/1"):
    return Release(album_id, 1, artist, title, "album", date, "https://img", link)


def test_groups_by_artist_sorted_and_has_no_image():
    embeds = summary_embeds([
        rel(1, "justice", "B", "2026-05-01", "https://d/b"),
        rel(2, "Genesis", "Z", "2026-02-01", "https://d/z"),
        rel(3, "justice", "A", "2026-01-01", "https://d/a"),
    ])
    assert len(embeds) == 1
    text = embeds[0]["description"]
    assert text.index("**Genesis**") < text.index("**justice**")
    assert text.index("[A]") < text.index("[B]")
    assert "[Z](https://d/z) · 2026-02-01" in text
    assert "image" not in embeds[0]
    assert embeds[0]["title"] == "New releases (3)"


def test_brackets_escaped_and_missing_date_and_link():
    text = summary_embeds([
        rel(1, "A", "Song [Live]", "", "https://d/1"),
        rel(2, "A", "No Link", "2026-01-01", None),
    ])[0]["description"]
    assert "[Song \\[Live\\]](https://d/1) · Unknown" in text
    assert "- No Link · 2026-01-01" in text


def test_empty_gives_no_embeds():
    assert summary_embeds([]) == []


def test_splits_at_artist_boundaries_under_limit():
    releases = [rel(i * 10 + n, f"Artist {i}", f"Title {n}") for i in range(6) for n in range(5)]
    embeds = summary_embeds(releases, limit=500)
    assert len(embeds) > 1
    assert all(len(e["description"]) <= 500 for e in embeds)
    assert embeds[0]["title"].endswith(f"(part 1/{len(embeds)})")
    for artist_number in range(6):  # each artist appears in exactly one chunk
        hits = [e for e in embeds if f"**Artist {artist_number}**" in e["description"]]
        assert len(hits) == 1
    assert sum(e["description"].count("- [") for e in embeds) == 30


def test_one_huge_artist_is_split_with_repeated_header():
    releases = [rel(i, "Big", f"Title {i}") for i in range(40)]
    embeds = summary_embeds(releases, limit=400)
    assert len(embeds) > 1
    assert all(len(e["description"]) <= 400 for e in embeds)
    assert embeds[1]["description"].startswith("**Big** (cont.)")
    assert sum(e["description"].count("- [") for e in embeds) == 40
