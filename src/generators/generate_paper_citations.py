#!/usr/bin/env python3
"""
Generate paper citation counts from Google Scholar.

Uses a single source (Google Scholar via the scholarly library) to ensure
all citation counts are comparable. Results are cached to disk so the
enricher can be run in batches — if Scholar blocks us we stop, and on the
next run cached papers are skipped automatically.

Reads:
  assets/data/artifacts.json           — paper titles, conferences, badges

Outputs:
  assets/data/paper_citations.json          — per-paper citation data
  assets/data/paper_citations_summary.json  — aggregate summary

Usage:
  # Full run (will stop gracefully if blocked):
  python3 -m src.generators.generate_paper_citations \\
      --data_dir ../reprodb.github.io

  # Report what's cached without making any API calls:
  python3 -m src.generators.generate_paper_citations \\
      --data_dir ../reprodb.github.io --cache_only

  # Custom cache TTL (default: 90 days):
  python3 -m src.generators.generate_paper_citations \\
      --data_dir ../reprodb.github.io --cache_ttl_days 90
"""

import argparse
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from src.utils.cache import _MISSING, read_cache, write_cache
from src.utils.conference import normalize_title
from src.utils.io import load_json, save_json

logger = logging.getLogger(__name__)
# ── Configuration ────────────────────────────────────────────────────────────
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "paper_citations"
CACHE_NS = "scholar"  # single namespace — one source

SCHOLAR_DELAY = 3.0  # seconds between queries (conservative)
SCHOLAR_BATCH_SIZE = 15  # pause after this many NEW queries
SCHOLAR_BATCH_PAUSE = 45  # seconds to pause between batches
MAX_CONSECUTIVE_ERRORS = 3  # stop after this many errors in a row
# ─────────────────────────────────────────────────────────────────────────────


def log(msg: str) -> None:
    logger.info(msg)


# ── Disk Cache ───────────────────────────────────────────────────────────────


def _cache_key(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode()).hexdigest()


# ── Google Scholar lookup ────────────────────────────────────────────────────

_scholarly_ready = None


def _ensure_scholarly():
    """Import and optionally configure scholarly. Returns True if available."""
    global _scholarly_ready
    if _scholarly_ready is not None:
        return _scholarly_ready
    try:
        from scholarly import scholarly as _  # noqa: F401

        _scholarly_ready = True
        # Try setting up FreeProxies for CAPTCHA rotation
        try:
            from scholarly._proxy_generator import ProxyGenerator

            pg = ProxyGenerator()
            if pg.FreeProxies(timeout=3, wait_time=60):
                from scholarly import scholarly

                scholarly.use_proxy(pg)
                log("  [Scholar] FreeProxies configured")
            else:
                log("  [Scholar] FreeProxies unavailable — direct connection")
        except Exception:
            log("  [Scholar] Proxy setup skipped — direct connection")
    except ImportError:
        log("ERROR: scholarly not installed.  pip install scholarly")
        _scholarly_ready = False
    return _scholarly_ready


def scholar_lookup(title: str) -> dict | None:
    """Query Google Scholar for citation count. Returns result dict or None."""
    from scholarly import scholarly

    time.sleep(SCHOLAR_DELAY)
    results = scholarly.search_pubs(title)
    pub = next(results, None)
    if not pub:
        return None

    # Verify match quality (Jaccard ≥ 0.5 on word sets)
    bib = pub.get("bib", {})
    pub_title = bib.get("title", "")
    norm_q = set(normalize_title(title).split())
    norm_r = set(normalize_title(pub_title).split())
    if norm_q and norm_r:
        jaccard = len(norm_q & norm_r) / len(norm_q | norm_r)
        if jaccard < 0.5:
            return None

    return {
        "cited_by_count": pub.get("num_citations", 0),
        "scholar_title": pub_title,
        "scholar_year": bib.get("pub_year"),
    }


# ── Main Generation ──────────────────────────────────────────────────────────


def generate(data_dir: str, cache_ttl: int, cache_only: bool) -> None:
    artifacts_path = os.path.join(data_dir, "assets", "data", "artifacts.json")
    out_path = os.path.join(data_dir, "assets", "data", "paper_citations.json")

    log("=" * 60)
    log("Paper Citation Enricher  (source: Google Scholar)")
    log("=" * 60)

    # Load artifacts
    if not os.path.exists(artifacts_path):
        log(f"Error: {artifacts_path} not found.")
        return
    artifacts = load_json(artifacts_path)
    log(f"✓ {len(artifacts)} artifacts loaded")

    # Deduplicate by normalized title
    seen: set[str] = set()
    unique: list[dict] = []
    for a in artifacts:
        norm = normalize_title(a.get("title", ""))
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(a)
    log(f"✓ {len(unique)} unique papers")

    # Count cache state
    cached_hits = 0
    cached_miss_neg = 0  # negative cache (empty string = looked up, not found)
    uncached = 0
    for a in unique:
        c = read_cache(str(CACHE_DIR), _cache_key(a["title"]), cache_ttl, CACHE_NS)
        if c is _MISSING:
            uncached += 1
        elif c == "":
            cached_miss_neg += 1
        else:
            cached_hits += 1
    log(f"  Cache: {cached_hits} hits, {cached_miss_neg} negative, {uncached} uncached")

    if cache_only:
        log("  Mode: CACHE ONLY (no API calls)")
    else:
        log(f"  Mode: LIVE (will query Scholar for {uncached + cached_miss_neg} papers)")
        if not _ensure_scholarly():
            return

    # Process
    entries = []
    found = 0
    errors = 0
    new_queries = 0
    consecutive_errors = 0
    stopped_early = False

    for i, a in enumerate(unique):
        title = a.get("title", "")
        norm = normalize_title(title)

        # Try cache first
        cached = read_cache(str(CACHE_DIR), _cache_key(title), cache_ttl, CACHE_NS)
        if cached is not _MISSING and cached != "":
            # Cache hit with data
            entry = {
                "title": title,
                "normalized_title": norm,
                "conference": a.get("conference", ""),
                "year": a.get("year", 0),
                "category": a.get("category", ""),
                "badges": a.get("badges", []),
                "cited_by_count": cached.get("cited_by_count"),
                "source": "scholar",
                "error": "",
            }
            entries.append(entry)
            found += 1
            continue

        if cache_only:
            # No data, skip
            entry = {
                "title": title,
                "normalized_title": norm,
                "conference": a.get("conference", ""),
                "year": a.get("year", 0),
                "category": a.get("category", ""),
                "badges": a.get("badges", []),
                "cited_by_count": None,
                "source": "",
                "error": "not_cached",
            }
            entries.append(entry)
            errors += 1
            continue

        # Negative cache — previously looked up but not found.
        # In cache_only=False mode, skip it (don't re-query).
        if cached == "":
            entry = {
                "title": title,
                "normalized_title": norm,
                "conference": a.get("conference", ""),
                "year": a.get("year", 0),
                "category": a.get("category", ""),
                "badges": a.get("badges", []),
                "cited_by_count": None,
                "source": "",
                "error": "not_found",
            }
            entries.append(entry)
            errors += 1
            continue

        # Live query
        try:
            result = scholar_lookup(title)
            consecutive_errors = 0
            new_queries += 1

            if result:
                write_cache(str(CACHE_DIR), _cache_key(title), json.dumps(result), CACHE_NS)
                entry = {
                    "title": title,
                    "normalized_title": norm,
                    "conference": a.get("conference", ""),
                    "year": a.get("year", 0),
                    "category": a.get("category", ""),
                    "badges": a.get("badges", []),
                    "cited_by_count": result["cited_by_count"],
                    "source": "scholar",
                    "error": "",
                }
                entries.append(entry)
                found += 1
            else:
                write_cache(str(CACHE_DIR), _cache_key(title), json.dumps(""), CACHE_NS)  # negative cache
                entry = {
                    "title": title,
                    "normalized_title": norm,
                    "conference": a.get("conference", ""),
                    "year": a.get("year", 0),
                    "category": a.get("category", ""),
                    "badges": a.get("badges", []),
                    "cited_by_count": None,
                    "source": "",
                    "error": "not_found",
                }
                entries.append(entry)
                errors += 1

            # Batch pause
            if new_queries > 0 and new_queries % SCHOLAR_BATCH_SIZE == 0:
                log(
                    f"  [{i + 1}/{len(unique)}] found={found} new_queries={new_queries}"
                    f" — pausing {SCHOLAR_BATCH_PAUSE}s"
                )
                time.sleep(SCHOLAR_BATCH_PAUSE)

        except Exception as e:
            consecutive_errors += 1
            err_str = str(e).lower()
            is_block = "captcha" in err_str or "429" in err_str or "blocked" in err_str or "maxtries" in err_str

            if is_block and consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log(
                    f"\n⚠ Scholar blocked after {consecutive_errors} consecutive errors"
                    f" — stopping. Run again later to continue."
                )
                stopped_early = True
                # Remaining papers get error entries
                for j in range(i, len(unique)):
                    rem = unique[j]
                    entries.append(
                        {
                            "title": rem.get("title", ""),
                            "normalized_title": normalize_title(rem.get("title", "")),
                            "conference": rem.get("conference", ""),
                            "year": rem.get("year", 0),
                            "category": rem.get("category", ""),
                            "badges": rem.get("badges", []),
                            "cited_by_count": None,
                            "source": "",
                            "error": "blocked",
                        }
                    )
                    errors += 1
                break
            if is_block:
                wait = 30 * consecutive_errors
                log(f"  [Scholar] Blocked ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}), waiting {wait}s...")
                time.sleep(wait)
                # Add error entry for this paper, continue to next
                entry = {
                    "title": title,
                    "normalized_title": norm,
                    "conference": a.get("conference", ""),
                    "year": a.get("year", 0),
                    "category": a.get("category", ""),
                    "badges": a.get("badges", []),
                    "cited_by_count": None,
                    "source": "",
                    "error": "blocked",
                }
                entries.append(entry)
                errors += 1
            else:
                log(f"  [Scholar] Error: {type(e).__name__}: {e}")
                write_cache(str(CACHE_DIR), _cache_key(title), json.dumps(""), CACHE_NS)
                entry = {
                    "title": title,
                    "normalized_title": norm,
                    "conference": a.get("conference", ""),
                    "year": a.get("year", 0),
                    "category": a.get("category", ""),
                    "badges": a.get("badges", []),
                    "cited_by_count": None,
                    "source": "",
                    "error": str(e),
                }
                entries.append(entry)
                errors += 1

        if (i + 1) % 100 == 0:
            log(f"  [{i + 1}/{len(unique)}] found={found} queries={new_queries} errors={errors}")

    # Write results
    log(f"\n✓ Processed {len(entries)} papers")
    log(f"  Found: {found}/{len(entries)} ({100 * found / max(1, len(entries)):.1f}%)")
    log(f"  New queries: {new_queries}")
    log(f"  Errors: {errors}")
    if stopped_early:
        log("  ⚠ Stopped early due to blocking — run again later to fill gaps")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    save_json(out_path, entries)
    log(f"✓ Written {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich papers with Google Scholar citation counts")
    parser.add_argument(
        "--data_dir",
        type=str,
        required=True,
        help="Path to reprodb.github.io",
    )
    parser.add_argument(
        "--cache_ttl_days",
        type=int,
        default=90,
        help="Cache TTL in days (default: 90)",
    )
    parser.add_argument(
        "--cache_only",
        action="store_true",
        default=False,
        help="Only use cached results — no API calls",
    )
    args = parser.parse_args()
    generate(args.data_dir, args.cache_ttl_days * 86_400, args.cache_only)


if __name__ == "__main__":
    from src.utils.logging_config import setup_logging

    setup_logging()

    main()
