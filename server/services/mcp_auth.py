"""Signed session tokens for ChatGPT MCP SMS login."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

# 0 = never expires (reuse for the whole ChatGPT thread).
SESSION_TTL_SECONDS = 0


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
    # exp=0 means never expire. Non-zero is unix expiry (legacy).
    try:
        ttl = int(ttl_seconds or 0)
    except (TypeError, ValueError):
        ttl = 0
    exp = 0 if ttl <= 0 else int(time.time()) + ttl
    payload = f"{phone}|{exp}"
    sig = hmac.new(_secret_bytes(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    raw = f"{payload}|{sig}"
    token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return {
        "session_token": token,
        "expires_at": None if exp == 0 else exp,
        "expires_in": None if exp == 0 else ttl,
        "phone": phone,
    }


def resolve_session(token: str):
    """Return E.164 phone if token is valid, else None."""
    if not token or not isinstance(token, str):
        return None
    try:
        padded = token + ("=" * (-len(token) % 4))
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        phone, exp_s, sig = raw.rsplit("|", 2)
        exp = int(exp_s)
        if exp != 0 and exp < int(time.time()):
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
