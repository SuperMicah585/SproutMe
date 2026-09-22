import re
import unittest

SHOW_RATING_RE = re.compile(
    r"(?:"
    r"\b(sprout(?:me)?\s+score|show\s+score|show\s+rating)\b|"
    r"\b(rating|score)\b.{0,40}\b(show|gig|event|night|one)\b|"
    r"\b(this|that|the)\s+(show|gig|event|one)\b.{0,40}\b(rating|score)\b|"
    r"\b(why|how).{0,24}\b(this |that |the )?(score|rated|ranking|rate)\b|"
    r"\b(break\s*down|explain).{0,24}\b(score|rating)\b|"
    r"\b(what'?s|what is|whats|how'?s|how is|tell me)\b.{0,32}\b(the )?(rating|score)\b"
    r")",
    re.I,
)
VENUE_RANK_RE = re.compile(
    r"\b(best|top|most popular|highest rated|favorite|go-to)\b.{0,48}\b(venues?|clubs?|rooms?|spots?)\b"
    r"|\b(venues?|clubs?)\b.{0,24}\b(best|most popular|highest rated)\b",
    re.I,
)


def is_show_rating(text: str) -> bool:
    if not SHOW_RATING_RE.search(text or ""):
        return False
    if VENUE_RANK_RE.search(text or ""):
        return False
    return True


def format_blurb(name: str, score: float, parts: dict) -> str:
    total = int(round(min(max(float(score or 0), 0), 1) * 100))
    labels = {"artist": "Artist", "hot": "Heat", "venue": "Room", "timing": "Timing"}
    bits = []
    for key in ("artist", "hot", "venue", "timing"):
        if key not in parts:
            continue
        value = float(parts[key])
        if key == "timing" and value <= 0:
            continue
        bits.append(f"{labels[key]} {int(round(value * 100))}")
    line = f"{name}: SproutMe {total}"
    if bits:
        line += " — " + ", ".join(bits)
    return line + "."


class ShowRatingRoutingTests(unittest.TestCase):
    def test_show_rating_phrases(self):
        for text in (
            "What's the rating for this show",
            "whats the score",
            "why this score",
            "sprout score",
            "how did you rate this",
            "break down the score",
        ):
            self.assertTrue(is_show_rating(text), text)

    def test_venue_phrases_stay_venue(self):
        for text in (
            "what about the reviews",
            "how's Vice",
            "highest rated venues in Seattle",
            "is the Fox Theater good",
        ):
            self.assertFalse(is_show_rating(text), text)

    def test_blurb(self):
        self.assertEqual(
            format_blurb("Shpongle", 0.98, {"artist": 0.96, "hot": 1.0, "venue": 0.963}),
            "Shpongle: SproutMe 98 — Artist 96, Heat 100, Room 96.",
        )


if __name__ == "__main__":
    unittest.main()
