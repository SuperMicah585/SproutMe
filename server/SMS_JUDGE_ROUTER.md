# SMS LLM judge (every message)

Deployed on PythonAnywhere (`services/sms_agent.py`, `sproutMe.py`). Mirror on Railway.

## Flow
1. STOP / HELP / RESET bypass the judge.
2. Every other inbound SMS hits a JSON-mode judge (`OPENAI_JUDGE_MODEL`, default `gpt-4.1-mini`, ~0.6–1.0s).
3. `fast_tools` → existing venue shortcuts + tool agent (`MAX_TOOL_ROUNDS`).
4. `deep_lookup` → interim SMS (“Looking that up — give me a minute.” / verify variant) via `progress_callback`, then tool agent with deep addendum + `MAX_TOOL_ROUNDS_DEEP`.

## Judge JSON shape
```json
{
  "route": "fast_tools" | "deep_lookup",
  "confidence": "high" | "medium" | "low",
  "reason": "...",
  "intent": "search_shows" | "venue_info" | "artist_info" | "verify_claim" | "plan_night" | "meta" | "other",
  "city": null,
  "neighborhood": null,
  "genre": null,
  "date_phrase": null,
  "artist": null,
  "venue": null,
  "deep_why": null
}
```

Hints are injected into the main system prompt as “Router notes” (never invent shows from them).
