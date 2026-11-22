from datetime import datetime, time

from music_alert.artists_file import normalize, parse_artists
from music_alert.scheduler import next_run, parse_schedule


def test_parse_artists_forms():
    text = """
    # a comment
    Daft Punk
    Justice | 1234   # pinned
    deezer:27
    DAFT  PUNK

    AC/DC | not-a-number
    """
    entries = parse_artists(text)
    assert [(e.name, e.artist_id) for e in entries] == [
        ("Daft Punk", None),
        ("Justice", 1234),
        (None, 27),
        ("AC/DC | not-a-number", None),
    ]


def test_normalize():
    assert normalize("  Beyoncé ") == "beyonce"
    assert normalize("Simon & Garfunkel") == "simon and garfunkel"


def test_schedule_next_run():
    schedule = parse_schedule("18:00, 00:15,06:00,12:00")
    assert schedule == [time(0, 15), time(6), time(12), time(18)]
    assert next_run(datetime(2026, 1, 1, 0, 0), schedule) == datetime(2026, 1, 1, 0, 15)
    assert next_run(datetime(2026, 1, 1, 0, 15), schedule) == datetime(2026, 1, 1, 6, 0)
    assert next_run(datetime(2026, 1, 1, 18, 0, 5), schedule) == datetime(2026, 1, 2, 0, 15)
