# Railway cold-start notes (events list)

Set frontend `VITE_API_URL` to:

`https://sproutme-api-production.up.railway.app`

(Production `sproutme-please.com` was still bundled against PythonAnywhere when checked.)

## Apply on the API service

These changes are already on PythonAnywhere `sproutMe.py`. Mirror them on Railway:

1. Writable file cache (`/tmp/...` on Railway; home path on PA).
2. `_spawn_web_cache_warm()` at import time (after helper defs) so catalog + score indexes preload.
3. `GET /events/cities` — tiny city list (optional; frontend geo now uses a static list).
4. Keep at least one Railway replica awake — sleep wake is often 3–8s by itself.

Frontend (this PR): race IP geo (~900ms cap) **before** the first `/events?city=Seattle` so cold start is one city-scoped request, not unfiltered catalog + facets + refetch.
