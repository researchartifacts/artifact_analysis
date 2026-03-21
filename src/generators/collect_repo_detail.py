#!/usr/bin/env python3
"""
collect_repo_detail.py — Collect per-repo stars/forks for CDF analysis.

Reads all_results_cache.yml to find GitHub URLs, queries the GitHub API
for each, and writes repo_stats_detail.json with per-repo data.

Usage:
    python -m src.generators.collect_repo_detail \
        --cache_yml ../researchartifacts.github.io/_data/all_results_cache.yml \
        --output repo_stats_detail.json
"""

import argparse
import json
import os
import re
import time

import requests
import yaml

from ..utils.conference import conf_area, parse_conf_year as _parse_conf_year
from ..scrapers.sys_sec_scrape import _github_headers


def _normalize_repo(url):
    """Extract owner/repo from a GitHub URL."""
    if "github.com/" not in url:
        return None
    repo = url.split("github.com/")[1]
    for suffix in ("/tree/", "/blob/", "/pkgs/", "/releases", "/wiki", "/issues"):
        if suffix in repo:
            repo = repo.split(suffix)[0]
    repo = repo.rstrip("/").removesuffix(".git")
    # Must be owner/repo format
    parts = repo.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def collect(cache_path, output_path):
    with open(cache_path) as f:
        data = yaml.safe_load(f)

    headers = _github_headers()
    session = requests.Session()
    session.headers.update(headers)

    # Collect all unique (repo, conf, year, title) tuples
    entries = []
    seen_repos = set()
    for conf_year, artifacts in data.items():
        conf, year = _parse_conf_year(conf_year)
        if conf is None:
            continue
        area = conf_area(conf)
        if area == "unknown":
            print(f"  Skipping unknown conference: {conf}")
            continue
        for a in artifacts:
            github_url = None
            for field in ["repository_url", "artifact_url"]:
                url = a.get(field, "")
                if url and "github.com" in url:
                    github_url = url
                    break
            if not github_url:
                continue
            repo = _normalize_repo(github_url)
            if not repo:
                continue
            # Deduplicate by (repo, year) — same repo may appear in multiple fields
            key = (repo.lower(), year)
            if key in seen_repos:
                continue
            seen_repos.add(key)
            entries.append({
                "repo": repo,
                "conference": conf,
                "year": year,
                "area": area,
                "title": a.get("title", ""),
            })

    print(f"Found {len(entries)} unique GitHub repos to query")

    results = []
    errors = 0
    for i, entry in enumerate(entries):
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i+1}/{len(entries)} ({errors} errors)")
        repo = entry["repo"]
        api_url = f"https://api.github.com/repos/{repo}"
        try:
            resp = session.get(api_url, timeout=30)
        except requests.RequestException as e:
            print(f"  Network error for {repo}: {e}")
            errors += 1
            continue

        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset_time = int(resp.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_time - int(time.time()), 0) + 5
            print(f"  Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            resp = session.get(api_url, timeout=30)

        if resp.status_code == 200:
            d = resp.json()
            results.append({
                "repo": repo,
                "conference": entry["conference"],
                "year": entry["year"],
                "area": entry["area"],
                "title": entry["title"],
                "stars": d.get("stargazers_count", 0),
                "forks": d.get("forks_count", 0),
                "language": d.get("language", ""),
                "description": d.get("description", ""),
                "pushed_at": d.get("pushed_at", ""),
            })
        elif resp.status_code in (404, 451):
            # Repo deleted or DMCA'd — record with 0 stars/forks
            results.append({
                "repo": repo,
                "conference": entry["conference"],
                "year": entry["year"],
                "area": entry["area"],
                "title": entry["title"],
                "stars": 0,
                "forks": 0,
                "language": "",
                "description": "(not found)",
                "pushed_at": "",
            })
            errors += 1
        else:
            print(f"  HTTP {resp.status_code} for {repo}")
            errors += 1

    print(f"\nDone: {len(results)} repos collected, {errors} errors")

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache_yml", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    collect(args.cache_yml, args.output)


if __name__ == "__main__":
    main()
