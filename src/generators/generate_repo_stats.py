"""
Generate repository statistics (stars, forks, etc.) for the website.

Collects stats from GitHub/Zenodo/Figshare for all scraped artifacts and writes:
  - _data/repo_stats.yml              — per-conference/year aggregates (for website)
  - assets/data/repo_stats_detail.json — per-repo detail (for analysis/figures)

Usage:
  python generate_repo_stats.py --conf_regex '.*20[12][0-9]' --output_dir ../reprodb.github.io
"""

import argparse
import logging
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from ..scrapers.parse_results_md import get_ae_results
from ..utils.collect_artifact_stats import figshare_stats, github_stats, zenodo_stats
from ..utils.conference import conf_area as _conf_area
from ..utils.conference import parse_conf_year as extract_conference_name
from ..utils.io import load_json, load_yaml, save_json, save_yaml
from ..utils.test_artifact_repositories import check_artifact_exists

logger = logging.getLogger(__name__)


def collect_stats_for_results(results, url_keys=None):
    """Collect repository stats for all artifacts.

    Expands multi-valued URL fields, deduplicates URLs, then fetches
    GitHub/Zenodo/Figshare stats in parallel.  Returns a list of
    per-URL stat dicts.
    """
    if url_keys is None:
        url_keys = ["repository_url", "artifact_url", "github_url", "second_repository_url", "bitbucket_url"]

    # First pass: extract ALL URLs from list-valued fields and create expanded artifact entries
    # This ensures we collect stats for every artifact location, not just the first
    expanded_artifacts = {}
    for conf_year, artifacts in results.items():
        expanded_artifacts[conf_year] = []
        for artifact in artifacts:
            # Collect all URLs from this artifact (including multi-valued fields)
            all_urls_by_key = {}

            # Add single-valued URL fields
            for url_key in url_keys:
                if url_key in artifact and artifact[url_key]:
                    all_urls_by_key[url_key] = [artifact[url_key]]

            # Add URLs from list-valued fields (artifact_urls, additional_urls, etc.)
            for list_key in ["artifact_urls", "additional_urls"]:
                if list_key in artifact and isinstance(artifact[list_key], list):
                    for url in artifact[list_key]:
                        if isinstance(url, str) and url:
                            # Map back to single key: artifact_urls -> artifact_url
                            flat_key = list_key.rstrip("s")
                            if flat_key not in all_urls_by_key:
                                all_urls_by_key[flat_key] = []
                            if url not in all_urls_by_key[flat_key]:
                                all_urls_by_key[flat_key].append(url)

            # Create separate artifact entry for each URL to process
            if all_urls_by_key:
                for url_key, urls in all_urls_by_key.items():
                    for url in urls:
                        artifact_copy = {
                            k: v for k, v in artifact.items() if k not in ["artifact_urls", "additional_urls"]
                        }
                        artifact_copy[url_key] = url
                        expanded_artifacts[conf_year].append(artifact_copy)
            else:
                # No URLs found, keep original artifact
                expanded_artifacts[conf_year].append(artifact)

    results = expanded_artifacts

    # Filter url_keys to only those that actually appear in the data
    present_keys = set()
    for artifacts in results.values():
        for artifact in artifacts:
            for key in url_keys:
                if key in artifact and artifact[key]:
                    present_keys.add(key)
    url_keys = [k for k in url_keys if k in present_keys]
    if not url_keys:
        logger.warning("  Warning: No URL keys found in artifact data. No repository stats to collect.")
        return []
    logger.info(f"  Scanning URL fields: {', '.join(url_keys)}")

    # Check which URLs exist
    results, _, _ = check_artifact_exists(results, url_keys)

    # Build deduplicated list of (url, conf_name, year, title) tuples to fetch
    fetch_tasks = []
    seen_urls: set[str] = set()
    for conf_year, artifacts in results.items():
        conf_name, year = extract_conference_name(conf_year)
        if year is None:
            continue
        for artifact in artifacts:
            for url_key in url_keys:
                url = artifact.get(url_key, "")
                exists_key = f"{url_key}_exists"
                if not artifact.get(exists_key, False) or not url:
                    continue
                url_normalized = url.rstrip("/")
                if url_normalized in seen_urls:
                    continue
                seen_urls.add(url_normalized)
                fetch_tasks.append((url, conf_name, year, artifact.get("title", "Unknown")))

    max_workers = 8
    logger.info(f"  Collecting stats for {len(fetch_tasks)} unique URLs ({max_workers} workers)")

    def _fetch_stats(url):
        """Fetch stats for a single URL (thread-safe via disk cache)."""
        try:
            if "github.com/" in url:
                return github_stats(url), "github"
            if "zenodo" in url:
                return zenodo_stats(url), "zenodo"
            if "figshare" in url:
                return figshare_stats(url), "figshare"
        except Exception as e:
            logger.error(f"  Error collecting stats for {url}: {e}")
        return None, "unknown"

    all_stats = []
    stats_collected = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        pending = {pool.submit(_fetch_stats, url): (url, conf, yr, title) for url, conf, yr, title in fetch_tasks}
        for i, future in enumerate(as_completed(pending), 1):
            url, conf_name, year, title = pending[future]
            stats, source = future.result()
            if stats:
                stats_collected += 1
                entry = {
                    "conference": conf_name,
                    "year": year,
                    "title": title,
                    "url": url,
                    "source": source,
                }
                entry.update(stats)
                all_stats.append(entry)
            if i % 100 == 0 or i == len(fetch_tasks):
                logger.info(f"  Progress: {i}/{len(fetch_tasks)} URLs fetched, {stats_collected} stats collected")

    return all_stats


def aggregate_stats(all_stats):
    """Aggregate per-conference and per-year statistics."""
    # Per-conference aggregates
    by_conf = defaultdict(
        lambda: {
            "github_repos": 0,
            "total_stars": 0,
            "total_forks": 0,
            "max_stars": 0,
            "max_forks": 0,
            "zenodo_repos": 0,
            "total_views": 0,
            "total_downloads": 0,
            "years": defaultdict(lambda: {"github_repos": 0, "stars": 0, "forks": 0}),
            "all_github_entries": [],
        }
    )

    by_year = defaultdict(
        lambda: {
            "github_repos": 0,
            "total_stars": 0,
            "total_forks": 0,
            "max_stars": 0,
            "max_forks": 0,
            "zenodo_repos": 0,
            "total_views": 0,
            "total_downloads": 0,
        }
    )

    overall = {
        "github_repos": 0,
        "total_stars": 0,
        "total_forks": 0,
        "max_stars": 0,
        "max_forks": 0,
        "zenodo_repos": 0,
        "total_views": 0,
        "total_downloads": 0,
        "avg_stars": 0,
        "avg_forks": 0,
    }

    for s in all_stats:
        conf = s["conference"]
        year = s["year"]

        if s["source"] == "github":
            stars = s.get("github_stars", 0) or 0
            forks = s.get("github_forks", 0) or 0

            by_conf[conf]["github_repos"] += 1
            by_conf[conf]["total_stars"] += stars
            by_conf[conf]["total_forks"] += forks
            by_conf[conf]["max_stars"] = max(by_conf[conf]["max_stars"], stars)
            by_conf[conf]["max_forks"] = max(by_conf[conf]["max_forks"], forks)
            by_conf[conf]["years"][year]["github_repos"] += 1
            by_conf[conf]["years"][year]["stars"] += stars
            by_conf[conf]["years"][year]["forks"] += forks
            by_conf[conf]["all_github_entries"].append(
                {
                    "title": s.get("title", "Unknown"),
                    "url": s.get("url", ""),
                    "conference": conf,
                    "year": year,
                    "area": _conf_area(conf),
                    "stars": stars,
                    "forks": forks,
                    "description": (s.get("description", "") or "")[:120],
                    "language": s.get("language", "") or "",
                    "name": s.get("name", ""),
                    "pushed_at": s.get("pushed_at", ""),
                }
            )

            by_year[year]["github_repos"] += 1
            by_year[year]["total_stars"] += stars
            by_year[year]["total_forks"] += forks
            by_year[year]["max_stars"] = max(by_year[year]["max_stars"], stars)
            by_year[year]["max_forks"] = max(by_year[year]["max_forks"], forks)

            overall["github_repos"] += 1
            overall["total_stars"] += stars
            overall["total_forks"] += forks
            overall["max_stars"] = max(overall["max_stars"], stars)
            overall["max_forks"] = max(overall["max_forks"], forks)

        elif s["source"] == "zenodo":
            views = s.get("zenodo_views", 0) or 0
            downloads = s.get("zenodo_downloads", 0) or 0

            by_conf[conf]["zenodo_repos"] += 1
            by_conf[conf]["total_views"] += views
            by_conf[conf]["total_downloads"] += downloads

            by_year[year]["zenodo_repos"] += 1
            by_year[year]["total_views"] += views
            by_year[year]["total_downloads"] += downloads

            overall["zenodo_repos"] += 1
            overall["total_views"] += views
            overall["total_downloads"] += downloads

    if overall["github_repos"] > 0:
        overall["avg_stars"] = round(overall["total_stars"] / overall["github_repos"], 1)
        overall["avg_forks"] = round(overall["total_forks"] / overall["github_repos"], 1)

    # Convert to serializable format
    conf_stats = []
    for conf_name in sorted(by_conf.keys()):
        d = by_conf[conf_name]
        avg_stars = round(d["total_stars"] / d["github_repos"], 1) if d["github_repos"] > 0 else 0
        avg_forks = round(d["total_forks"] / d["github_repos"], 1) if d["github_repos"] > 0 else 0
        year_list = []
        for yr in sorted(d["years"].keys()):
            yd = d["years"][yr]
            year_list.append(
                {
                    "year": yr,
                    "github_repos": yd["github_repos"],
                    "stars": yd["stars"],
                    "forks": yd["forks"],
                    "avg_stars": round(yd["stars"] / yd["github_repos"], 1) if yd["github_repos"] > 0 else 0,
                    "avg_forks": round(yd["forks"] / yd["github_repos"], 1) if yd["github_repos"] > 0 else 0,
                }
            )
        # Top 5 repos by stars
        top_repos = sorted(d["all_github_entries"], key=lambda x: x["stars"], reverse=True)[:5]
        conf_stats.append(
            {
                "name": conf_name,
                "github_repos": d["github_repos"],
                "total_stars": d["total_stars"],
                "total_forks": d["total_forks"],
                "avg_stars": avg_stars,
                "avg_forks": avg_forks,
                "max_stars": d["max_stars"],
                "max_forks": d["max_forks"],
                "years": year_list,
                "top_repos": top_repos,
            }
        )

    year_stats = []
    for yr in sorted(by_year.keys()):
        d = by_year[yr]
        avg_stars = round(d["total_stars"] / d["github_repos"], 1) if d["github_repos"] > 0 else 0
        avg_forks = round(d["total_forks"] / d["github_repos"], 1) if d["github_repos"] > 0 else 0
        year_stats.append(
            {
                "year": yr,
                "github_repos": d["github_repos"],
                "total_stars": d["total_stars"],
                "total_forks": d["total_forks"],
                "avg_stars": avg_stars,
                "avg_forks": avg_forks,
                "max_stars": d["max_stars"],
                "max_forks": d["max_forks"],
            }
        )

    overall["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Per-repo detail: all GitHub entries with individual star/fork counts
    all_github_detail = []
    for conf_name in sorted(by_conf.keys()):
        all_github_detail.extend(by_conf[conf_name]["all_github_entries"])

    return {
        "overall": overall,
        "by_conference": conf_stats,
        "by_year": year_stats,
        "all_github_repos": all_github_detail,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate repository statistics.")
    parser.add_argument("--conf_regex", type=str, default=".*20[12][0-9]", help="Regex for conference names/years")
    parser.add_argument("--output_dir", type=str, default=None, help="Website repo root directory")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch all stats instead of only new artifacts")
    args = parser.parse_args()

    # Try to load the cached results written by generate_statistics.py to
    # avoid re-scraping every results.md file.
    cache_path = None
    if args.output_dir:
        cache_path = os.path.join(args.output_dir, "_data", "all_results_cache.yml")
    if not cache_path or not os.path.exists(cache_path):
        # Fallback: repo root .cache directory
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_path = os.path.join(repo_root, ".cache", "all_results_cache.yml")

    if os.path.exists(cache_path):
        logger.info(f"Loading cached results from {cache_path}...")
        all_results = load_yaml(cache_path) or {}
        # Filter by conf_regex (cache may contain more conferences)
        all_results = {k: v for k, v in all_results.items() if re.search(args.conf_regex, k)}
        logger.info(
            f"Loaded {sum(len(v) for v in all_results.values())} artifacts across {len(all_results)} conference-years (from cache)"
        )
    else:
        logger.info("Collecting artifact results (no cache found, scraping)...")
        sys_results = get_ae_results(args.conf_regex, "sys")
        sec_results = get_ae_results(args.conf_regex, "sec")
        all_results = {**sys_results, **sec_results}
        logger.info(
            f"Found {sum(len(v) for v in all_results.values())} artifacts across {len(all_results)} conference-years"
        )

    # Load existing repo stats from the website (historical data).
    # Only fetch stats for NEW artifacts not already in the historical data,
    # unless --refresh is used which forces a full re-fetch.
    existing_stats = []
    existing_urls = set()
    if not args.refresh and args.output_dir:
        build_dir = os.path.join(args.output_dir, "_build")
        detail_path = os.path.join(build_dir, "repo_stats_detail.json")
        # Fall back to legacy location for backward compatibility
        if not os.path.exists(detail_path):
            detail_path = os.path.join(args.output_dir, "assets", "data", "repo_stats_detail.json")
        if os.path.exists(detail_path):
            raw_existing = load_json(detail_path)
            # Normalize existing entries to the format collect_stats_for_results produces
            for entry in raw_existing:
                if "source" not in entry:
                    url_lower = (entry.get("url", "") or "").lower()
                    if "github" in url_lower:
                        entry["source"] = "github"
                    elif "zenodo" in url_lower:
                        entry["source"] = "zenodo"
                    elif "figshare" in url_lower:
                        entry["source"] = "figshare"
                    else:
                        entry["source"] = "github"  # detail JSON is GitHub-only
                if "github_stars" not in entry and "stars" in entry:
                    entry["github_stars"] = entry["stars"]
                if "github_forks" not in entry and "forks" in entry:
                    entry["github_forks"] = entry["forks"]
            existing_stats = raw_existing
            existing_urls = {s.get("url", "").rstrip("/") for s in existing_stats}
            logger.info(f"Loaded {len(existing_stats)} existing repo stats ({len(existing_urls)} unique URLs)")

    if args.refresh:
        logger.info("--refresh: fetching stats for ALL artifacts")

    # Determine which artifacts are new (not in existing stats)
    new_results = {}
    total_artifacts = 0
    for conf_year, artifacts in all_results.items():
        new_arts = []
        for art in artifacts:
            total_artifacts += 1
            if not args.refresh:
                # Check all URL fields for this artifact
                has_existing = False
                for url_key in [
                    "repository_url",
                    "artifact_url",
                    "github_url",
                    "second_repository_url",
                    "bitbucket_url",
                ]:
                    url = art.get(url_key, "")
                    # Handle list-valued URL fields (e.g. artifact_url can be a list)
                    urls = url if isinstance(url, list) else [url] if url else []
                    for u in urls:
                        if isinstance(u, str) and u.rstrip("/") in existing_urls:
                            has_existing = True
                            break
                    if has_existing:
                        break
                if has_existing:
                    continue
            new_arts.append(art)
        if new_arts:
            new_results[conf_year] = new_arts

    new_count = sum(len(v) for v in new_results.values())
    logger.info(
        f"Total artifacts: {total_artifacts}, already have stats: {total_artifacts - new_count}, new to fetch: {new_count}"
    )

    if new_count > 0:
        logger.info(f"Collecting repository statistics for {new_count} artifacts...")
        new_stats = collect_stats_for_results(new_results)
        logger.info(f"Collected stats for {len(new_stats)} repositories")
        all_stats = existing_stats + new_stats
    else:
        logger.info("No new artifacts — reusing existing stats")
        all_stats = existing_stats

    logger.info("Aggregating statistics...")
    aggregated = aggregate_stats(all_stats)

    logger.info(
        f"Overall: {aggregated['overall']['github_repos']} GitHub repos, "
        f"{aggregated['overall']['total_stars']} total stars, "
        f"{aggregated['overall']['total_forks']} total forks"
    )

    if args.output_dir:
        data_dir = os.path.join(args.output_dir, "_data")
        assets_dir = os.path.join(args.output_dir, "assets", "data")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(assets_dir, exist_ok=True)
        out_path = os.path.join(data_dir, "repo_stats.yml")
        yaml_data = {k: v for k, v in aggregated.items() if k != "all_github_repos"}
        save_yaml(out_path, yaml_data)
        logger.info(f"Written to {out_path}")

        # Write per-repo detail JSON for CDF generation
        # Sort by URL for stable ordering across runs (ThreadPoolExecutor
        # returns results in non-deterministic completion order).
        detail_repos = sorted(
            aggregated.get("all_github_repos", []),
            key=lambda e: (e.get("conference", ""), e.get("year", 0), e.get("url", "")),
        )
        build_dir = os.path.join(data_dir, "..", "_build")
        os.makedirs(build_dir, exist_ok=True)
        detail_path = os.path.join(build_dir, "repo_stats_detail.json")
        save_json(detail_path, detail_repos)
        logger.info(f"Written per-repo detail ({len(aggregated.get('all_github_repos', []))} repos) to {detail_path}")

        # Write repo_stats_yearly.json — per-year stats split by area (all/systems/security)
        # Used by website repo_stats pages as a downloadable data file
        yearly_path = os.path.join(assets_dir, "repo_stats_yearly.json")
        conf_stats = aggregated.get("by_conference", [])
        # Build area lookup from artifacts_by_conference if available
        abc_path = os.path.join(data_dir, "artifacts_by_conference.yml")
        area_lookup = {}
        if os.path.exists(abc_path):
            abc = load_yaml(abc_path) or []
            for c in abc:
                area_lookup[c.get("name", "")] = c.get("category", "")
        yearly_by_year = defaultdict(
            lambda: {"all": defaultdict(list), "systems": defaultdict(list), "security": defaultdict(list)}
        )
        for cs in conf_stats:
            area = area_lookup.get(cs["name"], _conf_area(cs["name"]))
            for yr_data in cs.get("years", []):
                yr = yr_data["year"]
                repos = yr_data.get("github_repos", 0)
                avg_s = yr_data.get("avg_stars", 0)
                avg_f = yr_data.get("avg_forks", 0)
                for bucket in ["all", area] if area in ("systems", "security") else ["all"]:
                    yearly_by_year[yr][bucket]["repos_list"].append(repos)
                    yearly_by_year[yr][bucket]["stars_list"].append(avg_s)
                    yearly_by_year[yr][bucket]["forks_list"].append(avg_f)
        yearly_json = []
        for yr in sorted(yearly_by_year.keys()):
            entry = {"year": yr}
            for bucket in ("all", "systems", "security"):
                rl = yearly_by_year[yr][bucket]["repos_list"]
                sl = yearly_by_year[yr][bucket]["stars_list"]
                fl = yearly_by_year[yr][bucket]["forks_list"]
                if rl:
                    total_repos = sum(rl)
                    total_stars = sum(r * s for r, s in zip(rl, sl))
                    total_forks = sum(r * f for r, f in zip(rl, fl))
                    entry[bucket] = {
                        "repos": total_repos,
                        "avg_stars": round(total_stars / total_repos, 1) if total_repos else 0,
                        "avg_forks": round(total_forks / total_repos, 1) if total_repos else 0,
                        "min_stars": round(min(sl), 1),
                        "max_stars": round(max(sl), 1),
                        "min_forks": round(min(fl), 1),
                        "max_forks": round(max(fl), 1),
                    }
            yearly_json.append(entry)
        save_json(yearly_path, yearly_json)
        logger.info(f"Written yearly stats ({len(yearly_json)} years) to {yearly_path}")

        # ---- Historical time-series tracking ----
        # Append a dated snapshot for each fetched artifact so we can track
        # stars/forks/views/downloads over time across monthly runs.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        history_load_path = os.path.join(build_dir, "repo_stats_history.json")
        # Fall back to legacy location for loading existing history
        if not os.path.exists(history_load_path):
            legacy_history = os.path.join(assets_dir, "repo_stats_history.json")
            if os.path.exists(legacy_history):
                history_load_path = legacy_history
        # Always write to _build/
        history_write_path = os.path.join(build_dir, "repo_stats_history.json")

        # Load existing history
        history = {}
        if os.path.exists(history_load_path):
            history = load_json(history_load_path)
            logger.info(f"Loaded history for {len(history)} URLs")

        # Build snapshots from the raw all_stats (which have full metric detail)
        updated = 0
        for s in all_stats:
            url = s.get("url", "").rstrip("/")
            if not url:
                continue

            source = s.get("source", "")
            if not source:
                url_lower = url.lower()
                if "github" in url_lower:
                    source = "github"
                elif "zenodo" in url_lower:
                    source = "zenodo"
                elif "figshare" in url_lower:
                    source = "figshare"
                else:
                    source = "unknown"

            # Build the snapshot — only time-varying metrics
            snapshot = {"date": today}
            if source == "github":
                snapshot["stars"] = s.get("github_stars", s.get("stars", 0)) or 0
                snapshot["forks"] = s.get("github_forks", s.get("forks", 0)) or 0
            elif source in ("zenodo", "figshare"):
                snapshot["views"] = s.get("zenodo_views", s.get("views", 0)) or 0
                snapshot["downloads"] = s.get("zenodo_downloads", s.get("downloads", 0)) or 0

            if url not in history:
                history[url] = {
                    "meta": {
                        "conference": s.get("conference", ""),
                        "year": s.get("year", 0),
                        "area": _conf_area(s.get("conference", "")),
                        "title": s.get("title", ""),
                        "source": source,
                    },
                    "snapshots": [],
                }

            snapshots = history[url]["snapshots"]
            # Replace if we already have a snapshot for today, otherwise append
            if snapshots and snapshots[-1].get("date") == today:
                snapshots[-1] = snapshot
            else:
                snapshots.append(snapshot)
            updated += 1

        save_json(history_write_path, history)
        logger.info(f"Written history ({len(history)} URLs, {updated} snapshots updated) to {history_write_path}")

    return aggregated


if __name__ == "__main__":
    from src.utils.logging_config import setup_logging

    setup_logging()

    main()
