"""Signed session tokens for ChatGPT MCP SMS login."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

SESSION_TTL_SECONDS = 7 * 24 * 3600


def _secret_bytes():
    secret = (os.environ.get("MCP_SESSION_SECRET") or os.environ.get("AGENT_API_KEY") or "").strip()
    if not secret:
        # Dev fallback — production should set MCP_SESSION_SECRET or AGENT_API_KEY.
        secret = "sproutme-dev-session"
    return secret.encode("utf-8")


def issue_session(phone: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> dict:
    phone = (phone or "").strip()
    if not phone:
        raise ValueError("phone required")
    exp = int(time.time()) + int(ttl_seconds)
    payload = f"{phone}|{exp}"
    sig = hmac.new(_secret_bytes(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    raw = f"{payload}|{sig}"
    token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return {"session_token": token, "expires_at": exp, "expires_in": int(ttl_seconds), "phone": phone}


def resolve_session(token: str):
    """Return E.164 phone if token is valid, else None."""
    if not token or not isinstance(token, str):
        return None
    try:
        padded = token + ("=" * (-len(token) % 4))
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        phone, exp_s, sig = raw.rsplit("|", 2)
        exp = int(exp_s)
        if exp < int(time.time()):
            return None
        payload = f"{phone}|{exp}"
        expected = hmac.new(_secret_bytes(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expected, sig):
            return None
        return phone
    except Exception:
        return None


def favorite_key(event):
    if not event:
        return None
    return (
        (event.get("event_name") or "").strip().lower(),
        (event.get("venue") or "").strip().lower(),
        (event.get("date") or "").strip().lower(),
    )


def favorite_keys(favorites):
    keys = set()
    for event in favorites or []:
        key = favorite_key(event)
        if key and key[0]:
            keys.add(key)
    return keys
