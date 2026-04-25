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

from parse_results_md import get_ae_results
from test_artifact_repositories import _normalise_url

logger = logging.getLogger(__name__)

# ── Shared URL classification helpers ───────────────────────────────────────
# Import from the shared module when running as a package, otherwise fall back
# to a local copy (standalone execution for the paper).
try:
    from src.utils.artifact_urls import extract_source, get_artifact_url, resolve_doi_prefix  # noqa: F401
except ImportError:
    from utils.artifact_urls import extract_source, get_artifact_url, resolve_doi_prefix  # noqa: F401


def extract_year_from_confname(conf_year_str):
    """
    Extract year from conference name like 'osdi2024' -> 2024.
    Returns None if no year found.
    """
    match = re.search(r"(\d{4})$", conf_year_str)
    if match:
        return int(match.group(1))
    return None


def count_sources_by_year(all_results: dict[str, list[dict]]) -> dict[int, int]:
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
            url = get_artifact_url(artifact, normalise_fn=_normalise_url)
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
