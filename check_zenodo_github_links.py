#!/usr/bin/env python3
"""Check all Zenodo/Figshare-only artifacts for GitHub links in API responses.

Scans metadata.related_identifiers, metadata.description, and
metadata.notes for GitHub URLs. Reports hit rates by conference.
"""

import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
import yaml

DATA_FILE = Path(__file__).resolve().parent.parent / "reprodb-pipeline-results/output/website_data/_data/all_results_cache.yml"

session = requests.Session()
session.headers["Accept"] = "application/json"


def extract_zenodo_id(url: str) -> str | None:
    """Extract numeric record ID from a Zenodo URL."""
    url = str(url)
    # https://zenodo.org/records/14639575 or /record/14639575
    m = re.search(r"zenodo\.org/records?/(\d+)", url)
    if m:
        return m.group(1)
    # https://doi.org/10.5281/zenodo.14639575
    m = re.search(r"10\.5281/zenodo\.(\d+)", url)
    if m:
        return m.group(1)
    return None


def extract_figshare_id(url: str) -> str | None:
    """Extract article ID from a Figshare URL."""
    url = str(url)
    m = re.search(r"figshare\.com/articles/[^/]+/(\d+)", url)
    if m:
        return m.group(1)
    return None


def find_github_urls(text: str) -> list[str]:
    """Extract GitHub repo URLs from free text."""
    return re.findall(r"https?://github\.com/[^\s<\"'&;)]+", text)


def normalise_repo_url(url: str) -> str | None:
    url = url.split("?")[0].split("#")[0].rstrip("/").rstrip(".,;:)")
    if url.endswith(".git"):
        url = url[:-4]
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if m:
        return f"https://github.com/{m.group(1)}/{m.group(2)}"
    return None


def check_zenodo(record_id: str) -> dict:
    """Query Zenodo API and report where GitHub URLs are found."""
    result = {"source": "zenodo", "id": record_id, "found_in": [], "github_urls": set()}
    try:
        resp = session.get(f"https://zenodo.org/api/records/{record_id}", timeout=15)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 5))
            time.sleep(wait)
            resp = session.get(f"https://zenodo.org/api/records/{record_id}", timeout=15)
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result
        record = resp.json()
        meta = record.get("metadata", {})

        # 1. related_identifiers
        for ri in meta.get("related_identifiers", []):
            ident = ri.get("identifier", "")
            if "github.com/" in ident:
                base = normalise_repo_url(ident)
                if base:
                    result["github_urls"].add(base)
                    if "related_identifiers" not in result["found_in"]:
                        result["found_in"].append("related_identifiers")

        # 2. description
        desc = meta.get("description", "")
        for url in find_github_urls(desc):
            base = normalise_repo_url(url)
            if base and base not in result["github_urls"]:
                result["github_urls"].add(base)
                if "description" not in result["found_in"]:
                    result["found_in"].append("description")

        # 3. notes
        notes = meta.get("notes", "")
        for url in find_github_urls(notes):
            base = normalise_repo_url(url)
            if base and base not in result["github_urls"]:
                result["github_urls"].add(base)
                if "notes" not in result["found_in"]:
                    result["found_in"].append("notes")

        # 4. alternate identifiers
        for ai in meta.get("alternate_identifiers", []):
            ident = ai.get("identifier", "")
            if "github.com/" in ident:
                base = normalise_repo_url(ident)
                if base and base not in result["github_urls"]:
                    result["github_urls"].add(base)
                    if "alternate_identifiers" not in result["found_in"]:
                        result["found_in"].append("alternate_identifiers")

    except Exception as e:
        result["error"] = str(e)

    return result


def check_figshare(article_id: str) -> dict:
    """Query Figshare API and report where GitHub URLs are found."""
    result = {"source": "figshare", "id": article_id, "found_in": [], "github_urls": set()}
    try:
        resp = session.get(f"https://api.figshare.com/v2/articles/{article_id}", timeout=15)
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result
        record = resp.json()

        # 1. references
        for ref in record.get("references", []):
            if isinstance(ref, str) and "github.com/" in ref:
                base = normalise_repo_url(ref)
                if base:
                    result["github_urls"].add(base)
                    if "references" not in result["found_in"]:
                        result["found_in"].append("references")

        # 2. related_materials
        for rm in record.get("related_materials", []):
            ident = rm.get("identifier", "")
            if "github.com/" in ident:
                base = normalise_repo_url(ident)
                if base and base not in result["github_urls"]:
                    result["github_urls"].add(base)
                    if "related_materials" not in result["found_in"]:
                        result["found_in"].append("related_materials")

        # 3. description
        desc = record.get("description", "")
        for url in find_github_urls(desc):
            base = normalise_repo_url(url)
            if base and base not in result["github_urls"]:
                result["github_urls"].add(base)
                if "description" not in result["found_in"]:
                    result["found_in"].append("description")

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    if not DATA_FILE.exists():
        print(f"Data file not found: {DATA_FILE}")
        sys.exit(1)

    print(f"Loading {DATA_FILE}...")
    with open(DATA_FILE) as f:
        data = yaml.safe_load(f)

    # Collect Zenodo/Figshare-only artifacts (no GitHub URL in any field)
    tasks = []  # (conf, title, platform, platform_id, url)
    for conf, artifacts in data.items():
        for art in artifacts:
            has_github = False
            zenodo_url = None
            figshare_url = None
            for key in ["repository_url", "artifact_url", "github_url", "second_repository_url"]:
                url = art.get(key, "") or ""
                urls = url if isinstance(url, list) else [url]
                for u in urls:
                    u = str(u)
                    if "github.com" in u:
                        has_github = True
                    if "zenodo" in u and not zenodo_url:
                        zenodo_url = u
                    if "figshare" in u and not figshare_url:
                        figshare_url = u
            if has_github:
                continue
            title = art.get("title", "Unknown")[:60]
            if zenodo_url:
                zid = extract_zenodo_id(zenodo_url)
                if zid:
                    tasks.append((conf, title, "zenodo", zid, zenodo_url))
            elif figshare_url:
                fid = extract_figshare_id(figshare_url)
                if fid:
                    tasks.append((conf, title, "figshare", fid, figshare_url))

    print(f"Found {len(tasks)} Zenodo/Figshare-only artifacts to check\n")

    # Check each one
    by_conf = defaultdict(lambda: {"total": 0, "found": 0, "found_in": defaultdict(int)})
    total_found = 0
    total_errors = 0
    all_discovered = []

    for i, (conf, title, platform, pid, url) in enumerate(tasks, 1):
        if platform == "zenodo":
            result = check_zenodo(pid)
        else:
            result = check_figshare(pid)

        cname = conf.split("_")[0] if "_" in conf else conf
        by_conf[cname]["total"] += 1

        if result.get("error"):
            total_errors += 1
        elif result["github_urls"]:
            total_found += 1
            by_conf[cname]["found"] += 1
            for loc in result["found_in"]:
                by_conf[cname]["found_in"][loc] += 1
            all_discovered.append((cname, title, result["found_in"], list(result["github_urls"])))

        if i % 50 == 0 or i == len(tasks):
            print(f"  Progress: {i}/{len(tasks)} checked, {total_found} with GitHub links, {total_errors} errors")

        # Rate limit: ~10 req/s
        time.sleep(0.1)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY: {total_found}/{len(tasks)} artifacts have discoverable GitHub links ({100*total_found/len(tasks):.1f}%)")
    print(f"Errors: {total_errors}")
    print(f"\nBy conference:")
    print(f"{'Conference':<20} {'Total':>6} {'Found':>6} {'Rate':>6}  Sources")
    print(f"{'-'*20} {'-'*6} {'-'*6} {'-'*6}  {'-'*30}")
    for cname in sorted(by_conf, key=lambda c: -by_conf[c]["found"]):
        info = by_conf[cname]
        rate = 100 * info["found"] / info["total"] if info["total"] else 0
        sources = ", ".join(f"{k}={v}" for k, v in sorted(info["found_in"].items(), key=lambda x: -x[1]))
        print(f"{cname:<20} {info['total']:>6} {info['found']:>6} {rate:>5.1f}%  {sources}")

    print(f"\nDiscovered GitHub repos:")
    for cname, title, found_in, urls in sorted(all_discovered):
        print(f"  [{cname}] {title}")
        for u in urls:
            print(f"    -> {u}  (via {', '.join(found_in)})")


if __name__ == "__main__":
    main()
