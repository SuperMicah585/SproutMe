# SMS neighborhood filter (LLM + structured JSON)

Deployed in `services/sms_agent.py` on PythonAnywhere; mirror on Railway.

## Shape

```json
{
  "neighborhood": "Capitol Hill",
  "city": "Seattle",
  "venues": ["Chop Suey (Seattle)", "Q Nightclub (Seattle)"],
  "confidence": "high"
}
```

`venues` must be an exact subset of the candidate venue strings passed in.

## Flow
1. `search_events` accepts `neighborhood` (also peeled from user text / `q`).
2. After city filter, unique venues (≤220) go to a JSON-mode LLM call.
3. Events are kept only if their venue is in the returned list.
4. Result is cached in-memory per `(city, neighborhood)` for the worker lifetime (~0.2s on hit vs ~3s cold).

## Speed
- Cold: one extra model call (~2–4s). Prefer `OPENAI_NEIGHBORHOOD_MODEL=gpt-4.1-mini` on Railway/PA.
- Warm: cache hit, no LLM.
- Not run unless a neighborhood/area is named.

## Prompt / tool
- Tool param: `neighborhood`
- System prompt tells the agent to pass `neighborhood` + `city` and copy cards.
