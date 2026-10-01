"""Public API / ChatGPT Actions helpers."""
from __future__ import annotations

from datetime import date

from services.public_api import (
    filter_events,
    find_artist_shows,
    parse_date_window,
)


CATALOG = [
    {
        "id": 1,
        "event_name": "Bassvictim",
        "headliner": "Bassvictim",
        "venue": "Showbox SoDo",
        "city": "Seattle, WA",
        "genre": "bass",
        "raw_date": "2026/10/03",
        "date": "Sat 10/3",
        "ticket_info": "$25",
        "event_url": "https://example.com/bass",
    },
    {
        "id": 2,
        "event_name": "House Night",
        "headliner": "Local",
        "venue": "Q Nightclub",
        "city": "Seattle, WA",
        "genre": "house",
        "raw_date": "2026/10/03",
        "date": "Sat 10/3",
        "ticket_info": "$20",
        "event_url": "https://example.com/house",
    },
    {
        "id": 3,
        "event_name": "Nicky Romero",
        "headliner": "Nicky Romero",
        "venue": "Showbox",
        "city": "Seattle, WA",
        "genre": "edm",
        "raw_date": "2026/10/03",
        "date": "Sat 10/3",
        "ticket_info": "$40",
        "event_url": "https://example.com/nicky",
    },
]


def test_parse_saturday_window():
    start, end = parse_date_window("saturday", today=date(2026, 9, 28))
    assert start == date(2026, 10, 3)
    assert end == date(2026, 10, 3)


def test_search_house_saturday():
    result = filter_events(CATALOG, city="Seattle", genre="house", date="saturday", limit=5)
    # monkey: filter uses date.today(); force via raw_date match by calling with exact day
    result = filter_events(CATALOG, city="Seattle", genre="house", date="2026-10-03", limit=5)
    names = [e["event_name"] for e in result["data"]]
    assert "House Night" in names
    assert "Nicky Romero" not in names


def test_find_artist():
    result = find_artist_shows(CATALOG, artist="Bassvictim", city="Seattle", limit=3)
    assert result["data"]
    assert result["data"][0]["event_name"] == "Bassvictim"
    assert result["miss_reason"] is None


def test_find_artist_miss():
    result = find_artist_shows(CATALOG, artist="Nobodyhere", city="Seattle")
    assert not result["data"]
    assert result["miss_reason"]


if __name__ == "__main__":
    test_parse_saturday_window()
    test_search_house_saturday()
    test_find_artist()
    test_find_artist_miss()
    # relative saturday against frozen helper: patch today by using exact date path above
    from services import public_api as pa

    real = pa._today
    pa._today = lambda: date(2026, 9, 28)
    try:
        result = filter_events(CATALOG, city="Seattle", genre="house", date="saturday", limit=5)
        assert any(e["event_name"] == "House Night" for e in result["data"])
        assert not any(e["event_name"] == "Nicky Romero" for e in result["data"])
    finally:
        pa._today = real
    print("PASS public api chatgpt helpers")
