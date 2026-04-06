#!/usr/bin/env python3
"""
Generate artifact storage source statistics over time.

Tracks how GitHub, Zenodo, and other platforms have changed over the years
for artifact evaluation repositories.

Usage:
  python generate_artifact_sources_timeline.py --output_dir ../acm-rep-2026-paper/reproducibility
"""

import argparse
import csv
import logging
import os
import re
from collections import defaultdict

from sys_sec_artifacts_results_scrape import get_ae_results
from test_artifact_repositories import _normalise_url

logger = logging.getLogger(__name__)


def _resolve_doi_prefix(url):
    """Resolve DOI prefix to actual repository. Returns repository name or None."""
    doi_match = re.search(r"(?:doi\.org/)?(?:https?://doi\.org/)?(10\.\d+(?:[/\.][\w.\-]+)*)", url)
    if not doi_match:
        return None

    doi_prefix = doi_match.group(1).split("/")[0].split(".")[0:2]
    doi_prefix_str = ".".join(doi_prefix)

    # Map DOI prefixes to repositories
    doi_to_repo = {
        "10.5281": "Zenodo",  # Zenodo
        "10.6084": "Figshare",  # Figshare
        "10.17605": "OSF",  # Open Science Framework
        "10.4121": "Dataverse",  # Royal Data Repository
        "10.60517": "Zenodo",  # Zenodo (alternative prefix)
        "10.7278": "Figshare",  # Figshare (alternative)
        "10.25835": "NIST",  # NIST Data
    }

    return doi_to_repo.get(doi_prefix_str)


def extract_source(url):
    """Determine the source of an artifact from its URL."""
    if not url:
        return None

    url_lower = url.lower()

    if "github.com" in url_lower or "github.io" in url_lower:
        return "GitHub"
    if "zenodo" in url_lower or "zenodo.org" in url_lower:
        return "Zenodo"
    if "figshare" in url_lower:
        return "Figshare"
    if "osf.io" in url_lower:
        return "OSF"
    if "gitlab" in url_lower:
        return "GitLab"
    if "bitbucket" in url_lower:
        return "Bitbucket"
    if "archive.org" in url_lower or "arxiv" in url_lower:
        return "Archive"
    if "dataverse" in url_lower:
        return "Dataverse"
    if "doi.org" in url_lower:
        # Try to resolve DOI to actual repository
        resolved = _resolve_doi_prefix(url_lower)
        return resolved if resolved else "DOI"
    return "Other"


def get_artifact_url(artifact):
    """Extract the first valid URL from an artifact."""
    # New format: artifact_urls is the canonical list
    urls = artifact.get("artifact_urls", [])
    if isinstance(urls, list):
        for u in urls:
            norm = _normalise_url(u)
            if norm:
                return norm
    # Legacy fallback
    for key in ["repository_url", "artifact_url", "github_url", "second_repository_url", "bitbucket_url"]:
        val = artifact.get(key, "")
        if isinstance(val, list):
            val = val[0] if val else ""
        val = _normalise_url(val)
        if val:
            return val

    return None


def extract_year_from_confname(conf_year_str):
    """
    Extract year from conference name like 'osdi2024' -> 2024.
    Returns None if no year found.
    """
    match = re.search(r"(\d{4})$", conf_year_str)
    if match:
        return int(match.group(1))
    return None


def count_sources_by_year(all_results):
    """
    Count artifacts by source for each year.

    Returns dict: year -> {source: count}
    """
    stats = defaultdict(lambda: defaultdict(int))

    for conf_year, artifacts in all_results.items():
        year = extract_year_from_confname(conf_year)
        if not year:
            continue

        for artifact in artifacts:
            url = get_artifact_url(artifact)
            source = extract_source(url)
            if source:
                stats[year][source] += 1

    return dict(stats)


def generate_csv(output_dir):
    """Generate CSV file with artifact sources by year."""

    # Get all artifacts (from both systems and security)
    logger.info("Fetching artifact evaluation results...")
    sys_results = get_ae_results(r".*20[12][0-9]", "sys")
    sec_results = get_ae_results(r".*20[12][0-9]", "sec")
    all_results = {**sys_results, **sec_results}

    # Count sources by year
    stats_by_year = count_sources_by_year(all_results)

    # Sort years
    years = sorted(stats_by_year.keys())

    # Get all unique sources
    all_sources = set()
    for year_stats in stats_by_year.values():
        all_sources.update(year_stats.keys())

    # Sort sources with GitHub and Zenodo first, then alphabetically
    sources = sorted(
        all_sources, key=lambda x: (0 if x == "GitHub" else (1 if x == "Zenodo" else (2 if x == "Other" else 3)), x)
    )

    # Write CSV
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "fig_sources_over_time.csv")

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Year"] + sources)
        writer.writeheader()

        for year in years:
            row = {"Year": year}
            for source in sources:
                row[source] = stats_by_year[year].get(source, 0)
            writer.writerow(row)

    logger.info(f"✓ Generated {csv_path}")

    # Print summary
    logger.info("\nArtifact sources over time:")
    logger.info(f"{'Year':<6} {' '.join(f'{s:>10}' for s in sources)}")
    for year in years:
        counts = [str(stats_by_year[year].get(s, 0)) for s in sources]
        logger.info(f"{year:<6} {' '.join(f'{c:>10}' for c in counts)}")

    return csv_path


if __name__ == "__main__":
    from src.utils.logging_config import setup_logging

    setup_logging()

    parser = argparse.ArgumentParser(description="Generate artifact sources over time statistics")
    parser.add_argument(
        "--output_dir",
        default="../acm-rep-2026-paper/reproducibility/output/figures",
        help="Output directory for CSV file",
    )
    args = parser.parse_args()

    generate_csv(args.output_dir)
