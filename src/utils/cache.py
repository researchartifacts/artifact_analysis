"""Shared disk-based cache backed by hashed JSON files.

Every cached value is stored as ``{"ts": <unix-epoch>, "body": <payload>}``,
optionally with an ``"etag"`` field for conditional HTTP requests.
"""

import hashlib
import json
import logging
import os
import time

logger = logging.getLogger(__name__)


def cache_path(base_dir: str, key: str, namespace: str = "default") -> str:
    """Return the file path for *key* inside *base_dir*/*namespace*/."""
    ns_dir = os.path.join(base_dir, namespace)
    os.makedirs(ns_dir, exist_ok=True)
    hashed = hashlib.sha256(key.encode()).hexdigest()
    return os.path.join(ns_dir, hashed)


def read_cache(base_dir: str, key: str, ttl: int, namespace: str = "default") -> str | None:
    """Return cached body if fresh (younger than *ttl* seconds), else ``None``."""
    path = cache_path(base_dir, key, namespace)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            entry = json.load(f)
        if time.time() - entry.get("ts", 0) < ttl:
            return entry.get("body")
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None


def write_cache(
    base_dir: str,
    key: str,
    body: str,
    namespace: str = "default",
    etag: str | None = None,
) -> None:
    """Write *body* to the cache, optionally storing an HTTP ETag."""
    path = cache_path(base_dir, key, namespace)
    entry: dict = {"ts": time.time(), "body": body}
    if etag:
        entry["etag"] = etag
    with open(path, "w") as f:
        json.dump(entry, f)


def read_cache_entry(base_dir: str, key: str, namespace: str = "default") -> dict | None:
    """Return the full cache entry dict regardless of TTL, or ``None``."""
    path = cache_path(base_dir, key, namespace)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def refresh_cache_ts(base_dir: str, key: str, namespace: str = "default") -> None:
    """Touch the timestamp of a cache entry without changing its body."""
    path = cache_path(base_dir, key, namespace)
    try:
        with open(path) as f:
            entry = json.load(f)
        entry["ts"] = time.time()
        with open(path, "w") as f:
            json.dump(entry, f)
    except (json.JSONDecodeError, KeyError, OSError):
        pass
