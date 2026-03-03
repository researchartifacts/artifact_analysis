#!/usr/bin/env python3
"""
Generate artifact DOI citation counts via OpenAlex and write per-artifact metadata.

Outputs:
  assets/data/artifact_citations.json
  assets/data/artifact_citations_summary.json

Usage:
  python generate_artifact_citations.py --data_dir ../researchartifacts.github.io
"""

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict


DOI_REGEX = re.compile(r"10\.[0-9]{4,9}/[-._;()/:A-Za-z0-9]+")


def normalize_title(title: str) -> str:
    if not title:
        return ""
    normalized = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(normalized.split())


def extract_doi(url: str) -> str:
    if not url:
        return ""
    match = DOI_REGEX.search(url)
    return match.group(0).rstrip(".,);").lower() if match else ""


def extract_zenodo_record_id(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"zenodo\.org/(?:record|records)/(\d+)", url, re.I)
    if m:
        return m.group(1)
    m = re.search(r"zenodo\.org/badge/latestdoi/(\d+)", url, re.I)
    if m:
        return m.group(1)
    return ""


def fetch_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "researchartifacts-citations/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def fetch_zenodo_doi(record_id: str, cache: dict) -> str:
    if record_id in cache:
        return cache[record_id]
    url = f"https://zenodo.org/api/records/{record_id}"
    doi = ""
    try:
        payload = fetch_json(url, timeout=30)
        doi = (payload.get("metadata", {}) or {}).get("doi", "") or ""
        doi = doi.lower().strip()
    except Exception:
        doi = ""
    cache[record_id] = doi
    return doi


def fetch_openalex_citations(doi: str, cache: dict) -> tuple[int | None, str]:
    if doi in cache:
        return cache[doi]
    url = "https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="")
    last_err = ""
    for attempt in range(4):
        try:
            payload = fetch_json(url, timeout=25)
            cited = payload.get("cited_by_count")
            cited_val = cited if isinstance(cited, int) else None
            cache[doi] = (cited_val, "")
            return cache[doi]
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.6 * (attempt + 1))
    cache[doi] = (None, last_err)
    return cache[doi]


def generate(data_dir: str) -> None:
    artifacts_path = os.path.join(data_dir, "assets", "data", "artifacts.json")
    out_path = os.path.join(data_dir, "assets", "data", "artifact_citations.json")
    summary_path = os.path.join(data_dir, "assets", "data", "artifact_citations_summary.json")

    if not os.path.exists(artifacts_path):
        print(f"Error: {artifacts_path} not found. Run generate_statistics.py first.")
        return

    with open(artifacts_path, "r") as f:
        artifacts = json.load(f)

    zenodo_cache = {}
    openalex_cache = {}

    entries = []
    seen_doi = set()
    for artifact in artifacts:
        title = artifact.get("title", "")
        if not title:
            continue
        urls = [artifact.get("artifact_url", ""), artifact.get("repository_url", "")]

        doi = ""
        source = ""
        for url in urls:
            doi = extract_doi(url)
            if doi:
                source = "url"
                break

        if not doi:
            for url in urls:
                record_id = extract_zenodo_record_id(url)
                if record_id:
                    doi = fetch_zenodo_doi(record_id, zenodo_cache)
                    if doi:
                        source = "zenodo_api"
                        break

        cited_by = None
        err = ""
        if doi:
            cited_by, err = fetch_openalex_citations(doi, openalex_cache)
            seen_doi.add(doi)

        entries.append({
            "title": title,
            "normalized_title": normalize_title(title),
            "conference": artifact.get("conference", ""),
            "year": artifact.get("year", ""),
            "doi": doi,
            "doi_source": source,
            "cited_by_count": cited_by,
            "openalex_error": err,
        })

    # Summaries
    total = len(entries)
    with_doi = sum(1 for e in entries if e.get("doi"))
    resolved = sum(1 for e in entries if isinstance(e.get("cited_by_count"), int))
    cited = sum(1 for e in entries if isinstance(e.get("cited_by_count"), int) and e["cited_by_count"] > 0)

    by_year = defaultdict(lambda: {"n": 0, "resolved": 0, "cited": 0, "sum_cites": 0})
    for e in entries:
        y = e.get("year")
        if isinstance(y, int):
            by_year[y]["n"] += 1
            if isinstance(e.get("cited_by_count"), int):
                by_year[y]["resolved"] += 1
                by_year[y]["sum_cites"] += e["cited_by_count"]
                if e["cited_by_count"] > 0:
                    by_year[y]["cited"] += 1

    summary = {
        "total_artifacts": total,
        "unique_dois": len(seen_doi),
        "artifacts_with_doi": with_doi,
        "openalex_resolved": resolved,
        "artifacts_with_citations": cited,
        "by_year": {str(k): v for k, v in sorted(by_year.items())},
    }

    with open(out_path, "w") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path} ({len(entries)} entries)")
    print(f"Wrote {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate artifact citation stats via OpenAlex")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to researchartifacts.github.io")
    args = parser.parse_args()
    generate(args.data_dir)


if __name__ == "__main__":
    main()
