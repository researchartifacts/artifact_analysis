"""Content-hash skip cache for idempotent stages.

A stage is skipped when:
1. Every declared input file exists and has the same SHA-256 as the last
   successful run.
2. The stage's module source file has the same SHA-256 as last time.
3. Every declared output exists.
4. If the stage declares a ``ttl`` (seconds), the cache entry must be
   younger than that.  This forces periodic re-runs for stages that
   fetch live data (e.g. GitHub stats) whose per-URL caches expire.

Cache entries live in ``<output_dir>/_build/.cache/<stage>.hash`` as plain
text — one ``key=value`` line each — so they survive cleanly across pipeline
runs but are easy to inspect or delete by hand.

Only stages that opt in (by declaring ``inputs`` in :class:`src.stages.Stage`)
are eligible for skipping.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import time
from pathlib import Path

from src.stages import Stage

logger = logging.getLogger(__name__)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _module_source_path(module_name: str) -> Path | None:
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError):
        return None
    if spec is None or spec.origin is None or spec.origin == "built-in":
        return None
    return Path(spec.origin)


def _resolve_paths(paths: tuple[str, ...], output_dir: Path) -> list[Path]:
    """Resolve relative paths against ``output_dir``; keep absolute paths as-is."""
    resolved = []
    for p in paths:
        path = Path(p)
        if not path.is_absolute():
            path = output_dir / path
        resolved.append(path)
    return resolved


def compute_key(stage: Stage, output_dir: Path) -> str | None:
    """Return a content-hash key for ``stage`` or ``None`` if any input is missing."""
    h = hashlib.sha256()
    h.update(stage.name.encode())

    src = _module_source_path(stage.module)
    if src is None or not src.is_file():
        return None
    h.update(b"code:")
    h.update(_hash_file(src).encode())

    for path in _resolve_paths(stage.inputs, output_dir):
        if not path.is_file():
            return None
        h.update(b"in:")
        h.update(str(path).encode())
        h.update(b"=")
        h.update(_hash_file(path).encode())

    return h.hexdigest()


def _cache_file(stage: Stage, output_dir: Path) -> Path:
    return output_dir / "_build" / ".cache" / f"{stage.name}.hash"


def should_skip(stage: Stage, output_dir: Path) -> bool:
    """Return True if a previous run with identical inputs already produced
    every declared output file.

    When the stage declares a ``ttl``, the cache entry must also be younger
    than that many seconds — otherwise the stage re-runs even if inputs are
    unchanged (so that live-data stages periodically refresh).
    """
    if not stage.inputs:
        return False
    cache_file = _cache_file(stage, output_dir)
    if not cache_file.is_file():
        return False

    # TTL check: if the cache entry is older than the stage's TTL, force re-run.
    if stage.ttl is not None:
        age = time.time() - cache_file.stat().st_mtime
        if age >= stage.ttl:
            logger.info(
                "↻ %s: cache expired (%.1f days old, ttl=%.1f days)",
                stage.name,
                age / 86400,
                stage.ttl / 86400,
            )
            return False

    key = compute_key(stage, output_dir)
    if key is None or cache_file.read_text().strip() != key:
        return False
    for path in _resolve_paths(stage.outputs, output_dir):
        # Directory outputs (trailing /) just need to exist.
        if path.suffix == "" and str(path).endswith("/"):
            if not path.is_dir():
                return False
        elif not path.exists():
            return False
    return True


def mark_done(stage: Stage, output_dir: Path) -> None:
    """Record a successful run so a subsequent identical run can be skipped."""
    if not stage.inputs:
        return
    key = compute_key(stage, output_dir)
    if key is None:
        return
    cache_file = _cache_file(stage, output_dir)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(key + "\n")


def invalidate(stage: Stage, output_dir: Path) -> None:
    """Remove the cache entry for ``stage``, forcing a re-run next time."""
    cache_file = _cache_file(stage, output_dir)
    if cache_file.is_file():
        cache_file.unlink()
