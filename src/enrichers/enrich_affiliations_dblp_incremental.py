#!/usr/bin/env python3
"""
Incremental DBLP affiliation enrichment with smart prioritization.
- Skips authors that already have affiliations
- Tracks search history to avoid researching
- Prioritizes new authors (search immediately)
- Uses exponential backoff for unsuccessful searches
- Can resume from checkpoint without re-searching

Uses the pre-extracted DBLP JSON files (``src.utils.dblp_extract``)
instead of the DBLP web API.
"""

import json
import logging
import os
import re
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)
# Cache configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CACHE_DIR = os.path.join(REPO_ROOT, ".cache")
SEARCH_HISTORY_FILE = os.path.join(CACHE_DIR, "dblp_search_history.json")

# Exponential backoff configuration (in days)
BACKOFF_DEFAULT = 1  # Search unsuccessful authors again after 1 day
BACKOFF_MULTIPLIER = 2  # Double the backoff each time
BACKOFF_MAX = 30  # Cap at 30 days


def load_search_history():
    """Load search history from file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(SEARCH_HISTORY_FILE):
        try:
            with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_search_history(history):
    """Save search history to file."""
    with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def should_search_author(author_name, history):
    """
    Determine if an author should be searched based on history.

    Returns: (should_search, reason)
    """
    if author_name not in history:
        return True, "new_author"

    entry = history[author_name]
    found = entry.get("found", False)
    last_search = entry.get("last_search_ts", 0)
    attempt_count = entry.get("attempt_count", 0)

    if found:
        return False, "already_found"

    # Calculate backoff period for unsuccessful searches
    backoff_days = min(BACKOFF_DEFAULT * (BACKOFF_MULTIPLIER**attempt_count), BACKOFF_MAX)
    backoff_seconds = backoff_days * 86_400  # seconds per day

    time_since_search = time.time() - last_search

    if time_since_search >= backoff_seconds:
        return True, f"backoff_expired_{backoff_days}d"

    return False, f"backoff_active_{int((backoff_seconds - time_since_search) / 3600)}h_left"


def search_dblp_author(author_name, session=None, verbose=False):
    """Return a key for the author if found in pre-extracted DBLP data."""
    clean_name = re.sub(r"\s+\d{4}$", "", author_name).strip()
    try:
        from ..utils.dblp_extract import find_affiliation

        if find_affiliation(clean_name) is not None:
            return clean_name
    except (ImportError, Exception):
        logger.debug("DBLP extraction module not available for %s", author_name)
    return None


def fetch_affiliation_from_dblp_page(pid, session=None, verbose=False):
    """Return the affiliation for *pid* (which is the author name)."""
    try:
        from ..utils.dblp_extract import find_affiliation

        return find_affiliation(pid)
    except (ImportError, Exception):
        return None


def enrich_affiliations(
    authors_data: list[dict],
    output_path: str | None = None,
    max_searches: int | None = None,
    verbose: bool = False,
    recheck: bool = False,
    data_dir: str | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """
    Incrementally enrich author affiliations using DBLP with smart prioritization.

    Args:
        authors_data: List of author dicts from authors.json
        output_path: Path to save enriched data (if None, returns without saving)
        max_searches: Maximum number of searches to perform (for rate limiting)
        verbose: Print detailed progress
        recheck: If True, re-query all authors including those with existing affiliations
        data_dir: Website repo root for author index updates

    Returns:
        Tuple of (enriched_authors_data, stats_dict)
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "ResearchArtifacts-Affiliation-Enricher/1.0 (contact: https://github.com/researchartifacts/artifact_analysis)"
        }
    )

    # Add proxy support
    if os.environ.get("https_proxy"):
        session.proxies = {
            "http": os.environ.get("http_proxy", os.environ.get("https_proxy")),
            "https": os.environ.get("https_proxy"),
        }
        logger.info(f"Using proxy: {os.environ.get('https_proxy')}")

    # Load search history
    history = load_search_history()

    # Load author index if data_dir provided
    index_by_name = {}
    _update_index_fn = None
    _save_index_fn = None
    if data_dir:
        try:
            from src.utils.author_index import load_author_index, save_author_index, update_author_affiliation

            _, index_by_name = load_author_index(data_dir)
            _update_index_fn = update_author_affiliation

            def _save_index_fn():
                return save_author_index(data_dir, sorted(index_by_name.values(), key=lambda e: e["id"]))

            if index_by_name:
                logger.info(f"Loaded author index ({len(index_by_name)} entries)")
        except ImportError:
            logger.debug("Optional module not available, skipping enrichment")

    stats = {
        "total_authors": len(authors_data),
        "already_has_affiliation": 0,
        "new_authors_to_search": 0,
        "authors_ready_for_retry": 0,
        "authors_in_backoff": 0,
        "searches_performed": 0,
        "affiliations_found": 0,
        "new_affiliations": 0,
    }

    enriched_data = []

    logger.info(f"Total authors: {stats['total_authors']}")

    # Categorize authors
    to_search = []

    for author in authors_data:
        name = author.get("name", "")
        affiliation = author.get("affiliation", "")

        # Skip if already has good affiliation (unless rechecking)
        if not recheck and affiliation and affiliation not in ["Unknown", ""] and not affiliation.startswith("_"):
            stats["already_has_affiliation"] += 1
            enriched_data.append(author)
            continue

        # Check if should search
        should_search, reason = should_search_author(name, history)

        if should_search:
            if reason == "new_author":
                stats["new_authors_to_search"] += 1
                priority = 0  # High priority (new)
            else:  # backoff_expired
                stats["authors_ready_for_retry"] += 1
                priority = 1  # Lower priority (retry)
            to_search.append((priority, name, author))
        else:
            stats["authors_in_backoff"] += 1
            enriched_data.append(author)

    # Sort by priority (new authors first), then randomly within priority
    to_search.sort(key=lambda x: x[0])

    logger.info(f"Already have affiliation: {stats['already_has_affiliation']}")
    logger.info(f"New authors to search: {stats['new_authors_to_search']}")
    logger.info(f"Ready for retry: {stats['authors_ready_for_retry']}")
    logger.info(f"In backoff period: {stats['authors_in_backoff']}")
    logger.info(f"Total to search now: {len(to_search)}")

    if len(to_search) == 0:
        logger.info("\nNo new authors to search. All have affiliations or are in backoff period.")
        return authors_data, stats

    logger.info("\nStarting incremental DBLP enrichment...\n")

    for _priority, name, author in to_search:
        if max_searches and stats["searches_performed"] >= max_searches:
            logger.info(f"\nReached max searches limit ({max_searches})")
            enriched_data.append(author)
            continue

        stats["searches_performed"] += 1

        # Progress indicator
        if stats["searches_performed"] % 10 == 0 or verbose:
            found_rate = (
                stats["affiliations_found"] / stats["searches_performed"] * 100
                if stats["searches_performed"] > 0
                else 0
            )
            logger.info(
                f"  [{stats['searches_performed']}/{len(to_search)}] Found: {stats['affiliations_found']} ({found_rate:.1f}%)"
            )

        if verbose:
            logger.info(f"    Searching: {name}")

        # Search for author's PID
        pid = search_dblp_author(name, session, verbose=verbose)
        found_affil = False

        if pid:
            if verbose:
                logger.info(f"      Found PID: {pid}")

            # Fetch affiliation from person page
            affil = fetch_affiliation_from_dblp_page(pid, session, verbose=verbose)

            if affil:
                stats["affiliations_found"] += 1
                stats["new_affiliations"] += 1
                author["affiliation"] = affil
                # Update author index
                if name in index_by_name and _update_index_fn:
                    _update_index_fn(
                        index_by_name[name], affil, "dblp", external_id_key="dblp_pid", external_id_value=pid
                    )
                found_affil = True
                logger.info(f"    ✓ {name} → {affil}")
            elif verbose:
                logger.info("      No affiliation found on page")

        # Update search history
        if name not in history:
            history[name] = {"attempt_count": 0}

        history[name]["last_search_ts"] = time.time()
        history[name]["found"] = found_affil
        history[name]["attempt_count"] = history[name].get("attempt_count", 0) + 1

        enriched_data.append(author)

    # Save updated history
    save_search_history(history)

    # Save if output path provided
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, indent=2, ensure_ascii=False)
        logger.info(f"\n✅ Enriched data saved to {output_path}")
        # Save updated author index
        if _save_index_fn and index_by_name:
            _save_index_fn()
            logger.info("Author index updated")

    logger.info("\n📊 Summary:")
    logger.info(f"   Searches performed: {stats['searches_performed']}")
    logger.info(f"   New affiliations found: {stats['new_affiliations']}")
    logger.info(
        f"   Success rate: {stats['affiliations_found']}/{stats['searches_performed']} ({stats['affiliations_found'] / stats['searches_performed'] * 100:.1f}% if stats['searches_performed'] > 0 else 0)"
    )
    logger.info(f"   Search history saved: {SEARCH_HISTORY_FILE}")

    return enriched_data, stats


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Incremental DBLP affiliation enrichment with smart prioritization")
    parser.add_argument("--data_dir", default="../researchartifacts.github.io", help="Path to website data directory")
    parser.add_argument(
        "--max_searches", type=int, default=None, help="Maximum number of searches to perform (for rate limiting)"
    )
    parser.add_argument("--dry_run", action="store_true", help="Run without saving results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed progress")
    parser.add_argument("--clear_history", action="store_true", help="Clear search history and start fresh")
    parser.add_argument(
        "--recheck", action="store_true", help="Re-query all authors, including those with existing affiliations"
    )

    args = parser.parse_args()

    if args.clear_history and os.path.exists(SEARCH_HISTORY_FILE):
        os.remove(SEARCH_HISTORY_FILE)
        logger.info(f"Cleared search history: {SEARCH_HISTORY_FILE}")

    # Load authors.json
    authors_path = Path(args.data_dir) / "assets" / "data" / "authors.json"

    if not authors_path.exists():
        logger.error(f"Error: {authors_path} not found")
        return None

    logger.info(f"Loading {authors_path}...")
    with open(authors_path, "r", encoding="utf-8") as f:
        authors_data = json.load(f)

    # Enrich affiliations
    output_path = None if args.dry_run else authors_path
    enriched_data, stats = enrich_affiliations(
        authors_data,
        output_path=output_path,
        max_searches=args.max_searches,
        verbose=args.verbose,
        recheck=args.recheck,
        data_dir=args.data_dir,
    )

    return stats


if __name__ == "__main__":
    from src.utils.logging_config import setup_logging

    setup_logging()

    main()
