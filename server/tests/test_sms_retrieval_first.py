"""Regression checks for retrieval-first SMS (slots → intent → evidence → compose)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from services.sms_agent import SmsAgent
from services.sms_session import load_slots_from_messages


CATALOG = [
    {
        "id": 1,
        "event_name": "Bassvictim",
        "headliner": "Bassvictim",
        "venue": "Showbox SoDo",
        "city": "Seattle, WA",
        "genre": "bass",
        "raw_date": "2026/09/30",
        "date": "Wed 9/30",
        "ticket_info": "$25 | 21+",
        "event_url": "https://example.com/bassvictim",
    },
    {
        "id": 2,
        "event_name": "House Night with Local DJs",
        "headliner": "Local DJs",
        "venue": "Q Nightclub",
        "city": "Seattle, WA",
        "genre": "house",
        "raw_date": "2026/10/03",
        "date": "Sat 10/3",
        "ticket_info": "$20 | 21+",
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
        "ticket_info": "$40 | 21+",
        "event_url": "https://example.com/nicky",
    },
    {
        "id": 4,
        "event_name": "Nighthawk",
        "headliner": "Nighthawk",
        "venue": "Kremwerk",
        "city": "Seattle, WA",
        "genre": "house",
        "raw_date": "2026/10/03",
        "date": "Sat 10/3",
        "ticket_info": "$15 | 21+",
        "event_url": "https://example.com/nighthawk",
    },
    {
        "id": 5,
        "event_name": "Reload",
        "headliner": "Reload",
        "venue": "The Vera Project",
        "city": "Seattle, WA",
        "genre": "bass",
        "raw_date": "2026/10/10",
        "date": "Sat 10/10",
        "ticket_info": "$18 | All ages",
        "event_url": "https://example.com/reload",
    },
    {
        "id": 6,
        "event_name": "BOO Seattle",
        "headliner": "BOO Seattle",
        "venue": "Various",
        "city": "Seattle, WA",
        "genre": "bass",
        "raw_date": "2026/10/31",
        "date": "Sat 10/31",
        "ticket_info": "TBA",
        "event_url": "https://example.com/boo",
    },
    {
        "id": 7,
        "event_name": "VNV Nation",
        "headliner": "VNV Nation",
        "venue": "Showbox",
        "city": "Seattle, WA",
        "genre": "industrial",
        "raw_date": "2026/03/15",
        "date": "Sun 3/15",
        "ticket_info": "$35",
        "event_url": "https://example.com/vnv",
    },
]


class _FakeSpotify:
    enabled = False

    def lookup_artist(self, *args, **kwargs):
        return {}


def _build_agent():
    store = {}

    def get_conv(phone):
        row = store.get(phone)
        return {"data": row} if row else {"data": {}}

    def save_conv(phone, messages, started_at, global_rules=None, update_rules=False):
        store[phone] = {
            "messages": messages,
            "started_at": started_at,
            "global_rules": global_rules or "",
        }

    agent = SmsAgent(
        openai_api_key="sk-test",
        model="gpt-test",
        list_events=lambda: list(CATALOG),
        get_event=lambda i: next((e for e in CATALOG if e["id"] == i), None),
        add_event=lambda d: ({}, 400),
        get_user=lambda p: {"phone_number": p, "city_list": "", "genre_list": ""},
        create_user=lambda p: {"phone_number": p},
        update_name=lambda *a: None,
        update_cities=lambda *a: None,
        update_genres=lambda *a: None,
        get_favorites=lambda p: {},
        delete_user=lambda p: None,
        get_conversation=get_conv,
        save_conversation=save_conv,
        delete_conversation=lambda p: store.pop(p, None),
        spotify=_FakeSpotify(),
    )
    agent._client = object()
    agent._clock = lambda: {
        "today": date(2026, 9, 28),
        "now": datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc),
        "weekend_start": date(2026, 10, 2),
        "weekend_end": date(2026, 10, 4),
        "weekday": 0,
    }
    return agent, store


def _flat(out):
    if isinstance(out, list):
        return "\n".join(out).lower()
    return (out or "").lower()


def test_bassvictim_and_in_two_days():
    agent, store = _build_agent()
    phone = "+15550101"
    t = _flat(agent.reply(phone, "Bassvictim seattle"))
    assert "showbox" in t and "bassvictim" in t
    t = _flat(agent.reply(phone, "it's in 2 days"))
    assert "showbox" in t or "9/30" in t


def test_house_sticky_compare():
    agent, store = _build_agent()
    phone = "+15550102"
    t = _flat(agent.reply(phone, "house Saturday Seattle"))
    assert "nicky romero" not in t
    assert "nighthawk" in t or "q nightclub" in t or "house night" in t
    t = _flat(agent.reply(phone, "compare to nighthawk"))
    assert "nighthawk" in t or "kremwerk" in t
    slots = load_slots_from_messages(store[phone]["messages"])
    assert slots.get("genre") == "house"


def test_reload_details_no_invented_vibe():
    agent, store = _build_agent()
    phone = "+15550103"
    t = _flat(agent.reply(phone, "reload details"))
    assert "vnv" not in t
    assert "atmospheric" not in t and "darkwave" not in t
    assert "catalog" in t or "listing" in t or "don't have" in t or "reload" in t


def test_strip_club_out_of_scope():
    agent, store = _build_agent()
    phone = "+15550104"
    t = _flat(agent.reply(phone, "best strip club"))
    assert "showbox" not in t
    assert "electronic" in t or "music shows" in t


def test_boo_lineup_honest_miss():
    agent, store = _build_agent()
    phone = "+15550105"
    t = _flat(agent.reply(phone, "who plays BOO / main artists"))
    assert "vnv" not in t
    assert "guess" in t or "couldn't" in t or "no separate" in t


if __name__ == "__main__":
    test_bassvictim_and_in_two_days()
    test_house_sticky_compare()
    test_reload_details_no_invented_vibe()
    test_strip_club_out_of_scope()
    test_boo_lineup_honest_miss()
    print("PASS all retrieval-first regressions")
