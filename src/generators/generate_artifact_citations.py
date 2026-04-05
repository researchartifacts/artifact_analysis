#!/usr/bin/env python3
"""
Generate artifact DOI citation counts via OpenAlex and Semantic Scholar and write per-artifact metadata.

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
# Only accept DOIs from artifact repositories (Zenodo, Figshare)
# Reject paper DOIs from publishers (ACM, IEEE, Springer, etc.)
ALLOWED_ARTIFACT_DOI_PREFIXES = (
    "10.5281/zenodo.",  # Zenodo
    "10.6084/m9.figshare.",  # Figshare
)


def log(msg: str) -> None:
    print(msg, flush=True)


def short_url(url: str, max_len: int = 120) -> str:
    if len(url) <= max_len:
        return url
    return url[: max_len - 3] + "..."


def load_local_env_file(file_path: str) -> None:
    if not os.path.exists(file_path):
        return
    try:
        with open(file_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
        log(f"Loaded local environment from {file_path}")
    except Exception as e:
        log(f"Warning: could not load local env file {file_path}: {type(e).__name__}: {e}")

def is_artifact_doi(doi: str) -> bool:
    """Check if DOI is from an artifact repository (not a paper publisher)."""
    if not doi:
        return False
    return doi.lower().startswith(ALLOWED_ARTIFACT_DOI_PREFIXES)


def normalize_title(title: str) -> str:
    if not title:
        return ""
    normalized = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(normalized.split())


def extract_doi(url) -> str:
    if not url or not isinstance(url, str):
        return ""
    
    # Try direct DOI regex first
    match = DOI_REGEX.search(url)
    if match:
        return match.group(0).rstrip(".,);").lower()
    
    # Try converting Zenodo record URL to DOI format: https://zenodo.org/records/<id> -> 10.5281/zenodo.<id>
    m = re.search(r"zenodo\.org/(?:record|records)/(\d+)", url, re.I)
    if m:
        return f"10.5281/zenodo.{m.group(1)}".lower()
    
    return ""


def extract_zenodo_record_id(url) -> str:
    if not url or not isinstance(url, str):
        return ""
    m = re.search(r"zenodo\.org/(?:record|records)/(\d+)", url, re.I)
    if m:
        return m.group(1)
    m = re.search(r"zenodo\.org/badge/latestdoi/(\d+)", url, re.I)
    if m:
        return m.group(1)
    return ""


def fetch_json(url: str, timeout: int = 20) -> dict:
    return fetch_json_with_headers(url, timeout=timeout, headers=None)


def fetch_json_with_headers(url: str, timeout: int = 20, headers: dict | None = None) -> dict:
    req_headers = {"User-Agent": "researchartifacts-citations/0.1"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    started = time.time()
    log(f"[HTTP] GET {short_url(url)}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
            elapsed = time.time() - started
            log(f"[HTTP] OK  {short_url(url)} ({elapsed:.1f}s)")
            return payload
    except Exception as e:
        elapsed = time.time() - started
        log(f"[HTTP] ERR {short_url(url)} ({elapsed:.1f}s): {type(e).__name__}: {e}")
        raise


def fetch_zenodo_doi(record_id: str, cache: dict) -> str:
    """
    Get DOI for a Zenodo record.
    Always returns the Zenodo DOI (10.5281/zenodo.{record_id}) to ensure we get
    artifact citations, not paper citations from DOIs that authors may have linked.
    """
    if record_id in cache:
        return cache[record_id]
    
    # Construct Zenodo DOI directly from record ID
    # This ensures we always get artifact citations, not paper citations
    doi = f"10.5281/zenodo.{record_id}".lower()
    
    # Verify the record exists by checking the API
    url = f"https://zenodo.org/api/records/{record_id}"
    try:
        fetch_json(url, timeout=30)
        # Record exists, use the constructed Zenodo DOI
        cache[record_id] = doi
        return doi
    except Exception:
        # Record doesn't exist or API error
        cache[record_id] = ""
        return ""


def normalize_doi(value: str) -> str:
    if not value:
        return ""
    if value.lower().startswith("https://doi.org/"):
        value = value[len("https://doi.org/"):]
    if value.lower().startswith("http://doi.org/"):
        value = value[len("http://doi.org/"):]
    match = DOI_REGEX.search(value)
    if match:
        return match.group(0).rstrip(".,);").lower()
    return ""


def fetch_openalex_citations(doi: str, cache: dict, citing_doi_limit: int) -> dict:
    if doi in cache:
        return cache[doi]
    url = "https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="")
    last_err = ""
    for attempt in range(4):
        log(f"[OpenAlex] DOI {doi} (attempt {attempt + 1}/4)")
        try:
            payload = fetch_json(url, timeout=25)
            cited = payload.get("cited_by_count")
            cited_val = cited if isinstance(cited, int) else None
            citing_dois = []
            truncated = False

            # Construct citing works URL from OpenAlex ID if we need citing DOIs
            if citing_doi_limit > 0 and cited_val and cited_val > 0:
                openalex_id = payload.get("id", "")
                if openalex_id:
                    # Extract work ID from full URL (e.g., https://openalex.org/W12345 -> W12345)
                    work_id = openalex_id.split("/")[-1] if "/" in openalex_id else openalex_id
                    citing_works_url = f"https://api.openalex.org/works?filter=cites:{work_id}"
                    citing_dois, truncated = fetch_openalex_citing_dois(
                        citing_works_url, citing_doi_limit
                    )

            cache[doi] = {
                "count": cited_val,
                "citing_dois": citing_dois,
                "truncated": truncated,
                "error": "",
            }
            log(f"[OpenAlex] DOI {doi} -> cited_by_count={cited_val}")
            return cache[doi]
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            log(f"[OpenAlex] retrying DOI {doi} after error: {last_err}")
            time.sleep(0.6 * (attempt + 1))
    cache[doi] = {"count": None, "citing_dois": [], "truncated": False, "error": last_err}
    log(f"[OpenAlex] DOI {doi} failed after 4 attempts")
    return cache[doi]


def fetch_openalex_citing_dois(base_url: str, limit: int) -> tuple[list[str], bool]:
    """
    Fetch citing DOIs from OpenAlex using the filter API.
    base_url should be like: https://api.openalex.org/works?filter=cites:W12345
    """
    citing_dois = set()
    truncated = False
    cursor = "*"
    while True:
        url = f"{base_url}&per_page=200&cursor={urllib.parse.quote(cursor, safe='')}"
        payload = fetch_json(url, timeout=25)
        for work in payload.get("results", []) or []:
            doi_val = work.get("doi") or (work.get("ids", {}) or {}).get("doi") or ""
            norm = normalize_doi(doi_val)
            if norm:
                citing_dois.add(norm)
                if len(citing_dois) >= limit:
                    truncated = True
                    break
        if truncated:
            break
        cursor = (payload.get("meta", {}) or {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(0.2)
    return sorted(citing_dois), truncated


def fetch_semantic_scholar_citations(doi: str, cache: dict, citing_doi_limit: int) -> dict:
    if doi in cache:
        return cache[doi]

    headers = {}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    paper_id = "DOI:" + doi
    base_url = "https://api.semanticscholar.org/graph/v1/paper/" + urllib.parse.quote(paper_id, safe="")
    last_err = ""
    request_timeout = int(os.environ.get("SEMANTIC_SCHOLAR_TIMEOUT", "8"))
    max_attempts = int(os.environ.get("SEMANTIC_SCHOLAR_MAX_ATTEMPTS", "2"))
    for attempt in range(max_attempts):
        log(f"[SemanticScholar] DOI {doi} (attempt {attempt + 1}/{max_attempts})")
        try:
            payload = fetch_json_with_headers(
                base_url + "?fields=citationCount", timeout=request_timeout, headers=headers
            )
            cited = payload.get("citationCount")
            cited_val = cited if isinstance(cited, int) else None
            citing_dois = []
            truncated = False
            if citing_doi_limit > 0:
                citing_dois, truncated = fetch_semantic_scholar_citing_dois(
                    base_url, headers, citing_doi_limit
                )
            cache[doi] = {
                "count": cited_val,
                "citing_dois": citing_dois,
                "truncated": truncated,
                "error": "",
            }
            log(f"[SemanticScholar] DOI {doi} -> citationCount={cited_val}")
            return cache[doi]
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt + 1 < max_attempts:
                log(f"[SemanticScholar] retrying DOI {doi} after error: {last_err}")
            time.sleep(0.6 * (attempt + 1))
    cache[doi] = {"count": None, "citing_dois": [], "truncated": False, "error": last_err}
    log(f"[SemanticScholar] DOI {doi} failed after {max_attempts} attempts")
    return cache[doi]


def semantic_scholar_reachable() -> bool:
    check_url = "https://api.semanticscholar.org/graph/v1/paper/DOI%3A10.1038%2Fnature12373?fields=paperId"
    timeout = int(os.environ.get("SEMANTIC_SCHOLAR_PREFLIGHT_TIMEOUT", "3"))
    try:
        fetch_json_with_headers(check_url, timeout=timeout, headers=None)
        return True
    except Exception as e:
        log(f"[SemanticScholar] preflight failed: {type(e).__name__}: {e}")
        return False


def fetch_semantic_scholar_citing_dois(
    base_url: str, headers: dict, limit: int
) -> tuple[list[str], bool]:
    citing_dois = set()
    truncated = False
    offset = 0
    page_size = 100
    while True:
        url = (
            f"{base_url}/citations?fields=externalIds&limit={page_size}&offset={offset}"
        )
        payload = fetch_json_with_headers(url, timeout=25, headers=headers)
        for entry in payload.get("data", []) or []:
            ext_ids = (entry.get("citingPaper", {}) or {}).get("externalIds", {}) or {}
            doi_val = ext_ids.get("DOI", "")
            norm = normalize_doi(doi_val)
            if norm:
                citing_dois.add(norm)
                if len(citing_dois) >= limit:
                    truncated = True
                    break
        if truncated:
            break
        next_offset = payload.get("next")
        if next_offset is None:
            if len(payload.get("data", []) or []) < page_size:
                break
            offset += page_size
        else:
            offset = next_offset
        time.sleep(0.2)
    return sorted(citing_dois), truncated


def generate(data_dir: str) -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    local_env_path = os.path.join(repo_root, ".env.local")
    load_local_env_file(local_env_path)

    print("=" * 60, flush=True)
    print("Starting artifact citation generation...", flush=True)
    print("=" * 60, flush=True)
    
    artifacts_path = os.path.join(data_dir, "assets", "data", "artifacts.json")
    out_path = os.path.join(data_dir, "assets", "data", "artifact_citations.json")
    summary_path = os.path.join(data_dir, "assets", "data", "artifact_citations_summary.json")

    print(f"Loading artifacts from: {artifacts_path}", flush=True)
    
    if not os.path.exists(artifacts_path):
        print(f"Error: {artifacts_path} not found. Run generate_statistics.py first.", flush=True)
        return

    with open(artifacts_path, "r") as f:
        artifacts = json.load(f)
    
    print(f"✓ Loaded {len(artifacts)} artifacts", flush=True)

    zenodo_cache = {}
    openalex_cache = {}
    semantic_scholar_cache = {}
    openalex_citing_limit = int(os.environ.get("OPENALEX_CITING_DOI_LIMIT", "200"))
    semantic_citing_limit = int(os.environ.get("SEMANTIC_SCHOLAR_CITING_DOI_LIMIT", "200"))

    print(f"Processing {len(artifacts)} artifacts...", flush=True)
    print(f"OpenAlex citing DOI limit: {openalex_citing_limit}", flush=True)
    print(f"Semantic Scholar citing DOI limit: {semantic_citing_limit}", flush=True)
    print(flush=True)

    entries = []
    seen_doi = set()
    dois_found = 0
    dois_filtered = 0
    semantic_failures = 0
    semantic_disabled = os.environ.get("DISABLE_SEMANTIC_SCHOLAR", "").strip() == "1"

    if semantic_disabled:
        log("[SemanticScholar] disabled via DISABLE_SEMANTIC_SCHOLAR=1")
    else:
        log("[SemanticScholar] running connectivity preflight...")
        if not semantic_scholar_reachable():
            semantic_disabled = True
            log("[SemanticScholar] disabled for this run due to connectivity failure")
    
    for idx, artifact in enumerate(artifacts, 1):
        title = artifact.get("title", "")
        if not title:
            continue
        urls = artifact.get("artifact_urls", [])
        if not urls:
            # Legacy fallback
            urls = [artifact.get("artifact_url", ""), artifact.get("repository_url", "")]

        doi = ""
        source = ""
        
        # First priority: Try to get DOI from Zenodo API for Zenodo records
        # This ensures we get the artifact DOI, not a paper DOI embedded in the page
        for url in urls:
            record_id = extract_zenodo_record_id(url)
            if record_id:
                doi = fetch_zenodo_doi(record_id, zenodo_cache)
                if doi:
                    source = "zenodo_api"
                    break
        
        # Fallback: Extract DOI directly from URL (for non-Zenodo artifacts)
        if not doi:
            for url in urls:
                doi = extract_doi(url)
                if doi:
                    source = "url"
                    break
        
        # Filter: Only keep artifact DOIs (Zenodo, Figshare), drop paper DOIs (ACM, IEEE, etc.)
        if doi and not is_artifact_doi(doi):
            dois_filtered += 1
            doi = ""
            source = ""
        elif doi:
            dois_found += 1

        # Progress indicator
        if idx % 50 == 0:
            print(f"Progress: {idx}/{len(artifacts)} artifacts processed, {dois_found} DOIs found, {dois_filtered} filtered", flush=True)

        cited_by = None
        openalex_err = ""
        semantic_err = ""
        openalex_count = None
        semantic_count = None
        openalex_citing_dois = []
        semantic_citing_dois = []
        openalex_truncated = False
        semantic_truncated = False
        if doi:
            openalex_entry = fetch_openalex_citations(doi, openalex_cache, openalex_citing_limit)
            if semantic_disabled:
                semantic_entry = {"count": None, "citing_dois": [], "truncated": False, "error": "disabled_after_connect_failures"}
            else:
                semantic_entry = fetch_semantic_scholar_citations(
                    doi, semantic_scholar_cache, semantic_citing_limit
                )
            openalex_count = openalex_entry.get("count")
            semantic_count = semantic_entry.get("count")
            openalex_citing_dois = openalex_entry.get("citing_dois", [])
            semantic_citing_dois = semantic_entry.get("citing_dois", [])
            openalex_truncated = bool(openalex_entry.get("truncated"))
            semantic_truncated = bool(semantic_entry.get("truncated"))
            openalex_err = openalex_entry.get("error", "")
            semantic_err = semantic_entry.get("error", "")

            if semantic_err and "timed out" in semantic_err.lower():
                semantic_failures += 1
                if semantic_failures >= 5 and not semantic_disabled:
                    semantic_disabled = True
                    log("[SemanticScholar] disabled for this run after 5 timeout failures (network/connectivity issue)")

            counts = [c for c in [openalex_count, semantic_count] if isinstance(c, int)]
            cited_by = max(counts) if counts else None
            seen_doi.add(doi)

        entries.append({
            "title": title,
            "normalized_title": normalize_title(title),
            "conference": artifact.get("conference", ""),
            "year": artifact.get("year", ""),
            "doi": doi,
            "doi_source": source,
            "cited_by_count": cited_by,
            "citations_openalex": openalex_count,
            "citations_semantic_scholar": semantic_count,
            "citing_dois_openalex": openalex_citing_dois,
            "citing_dois_semantic_scholar": semantic_citing_dois,
            "citing_dois_openalex_truncated": openalex_truncated,
            "citing_dois_semantic_scholar_truncated": semantic_truncated,
            "openalex_error": openalex_err,
            "semantic_scholar_error": semantic_err,
        })

    # Summaries
    total = len(entries)
    with_doi = sum(1 for e in entries if e.get("doi"))
    resolved = sum(1 for e in entries if isinstance(e.get("cited_by_count"), int))
    openalex_resolved = sum(1 for e in entries if isinstance(e.get("citations_openalex"), int))
    semantic_resolved = sum(1 for e in entries if isinstance(e.get("citations_semantic_scholar"), int))
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
        "openalex_resolved": openalex_resolved,
        "semantic_scholar_resolved": semantic_resolved,
        "aggregate_resolved": resolved,
        "artifacts_with_citations": cited,
        "by_year": {str(k): v for k, v in sorted(by_year.items())},
    }

    with open(out_path, "w") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(flush=True)
    print("✓ Processing complete!", flush=True)
    print(f"  Total artifacts: {len(artifacts)}", flush=True)
    print(f"  Artifact DOIs found: {dois_found}", flush=True)
    print(f"  Paper DOIs filtered: {dois_filtered}", flush=True)
    print(f"  Artifacts with citations: {cited}", flush=True)
    print(flush=True)
    print(f"Wrote {out_path} ({len(entries)} entries)", flush=True)
    print(f"Wrote {summary_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate artifact citation stats via OpenAlex and Semantic Scholar")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to researchartifacts.github.io")
    parser.add_argument("--enable-citations", action="store_true", default=False,
                        help="Actually run citation collection. Without this flag, the script exits immediately.")
    args = parser.parse_args()

    if not args.enable_citations:
        print("=" * 78, flush=True)
        print("WARNING: Citation collection is DISABLED by default.", flush=True)
        print("", flush=True)
        print("OpenAlex citation counts for artifact DOIs are UNRELIABLE.", flush=True)
        print("Verification (March 2026) found that ALL 43 reported citing DOIs", flush=True)
        print("were false positives (paper DOI cited instead of artifact DOI),", flush=True)
        print("self-citations, or unresolvable. Zero genuine third-party artifact", flush=True)
        print("citations exist in the current dataset.", flush=True)
        print("", flush=True)
        print("If you still want to run citation collection (e.g., for research", flush=True)
        print("or to check whether the situation has improved), pass:", flush=True)
        print("  --enable-citations", flush=True)
        print("", flush=True)
        print("After collection, run verify_artifact_citations.py to validate", flush=True)
        print("whether any reported citations are genuine.", flush=True)
        print("=" * 78, flush=True)
        return

    generate(args.data_dir)


if __name__ == "__main__":
    main()
