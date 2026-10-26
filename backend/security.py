"""security.py -- encrypt API keys at rest, mask them for display.

AES-256-GCM with a random 12-byte nonce per write. The master key is the
APP_ENCRYPTION_KEY environment variable (32 random bytes, base64).
Generate one:  python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _master() -> bytes:
    raw = base64.b64decode(os.environ["APP_ENCRYPTION_KEY"])
    if len(raw) != 32:
        raise ValueError("APP_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return raw


def encrypt_secret(plain: str) -> dict:
    nonce = os.urandom(12)
    ct = AESGCM(_master()).encrypt(nonce, plain.encode(), None)   # tag is appended to ct
    return {"ciphertext": base64.b64encode(ct).decode(), "iv": base64.b64encode(nonce).decode()}


def decrypt_secret(doc: dict) -> str:
    ct = base64.b64decode(doc["ciphertext"])
    nonce = base64.b64decode(doc["iv"])
    return AESGCM(_master()).decrypt(nonce, ct, None).decode()


def save_provider_key(db, provider: str, plain: str) -> None:
    """Called by the admin 'API Keys' screen. Never log `plain`."""
    now = datetime.now(timezone.utc)
    enc = encrypt_secret(plain.strip())
    db.provider_keys.update_one(
        {"provider": provider},
        {"$set": {**enc, "last4": plain.strip()[-4:], "rotated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


def get_provider_key(db, provider: str, env_fallback: str | None = None) -> str | None:
    """Key stored in admin wins. The environment variable is a development fallback."""
    doc = db.provider_keys.find_one({"provider": provider})
    if doc:
        return decrypt_secret(doc)
    return os.environ.get(env_fallback) if env_fallback else None


def public_key_view(db, provider: str) -> dict:
    """What the browser may see: never the key."""
    doc = db.provider_keys.find_one({"provider": provider}, {"_id": 0, "last4": 1, "created_at": 1, "rotated_at": 1})
    return {"set": bool(doc), "masked": f"•••• {doc['last4']}" if doc else None,
            "created_at": doc and doc.get("created_at"), "rotated_at": doc and doc.get("rotated_at")}
