#!/usr/bin/env python3
"""
Pre-extract structured data from the local DBLP XML dump.

Parses ``dblp.xml.gz`` in a single pass and writes JSON lookup files that
every downstream pipeline step can load instead of hitting the DBLP API.

Outputs (under *output_dir*):
  .cache/dblp_extracted/papers_by_venue.json
      {conf: {year_str: [{title, authors, doi, dblp_key}]}}

  .cache/dblp_extracted/affiliations.json
      {author_name: affiliation}

The extraction is cached: if the DBLP file has not changed (same mtime)
the previous JSON files are reused.

Usage:
  python -m src.utils.dblp_extract --dblp_file data/dblp/dblp.xml.gz

NOTE — DBLP API policy
~~~~~~~~~~~~~~~~~~~~~~
We deliberately avoid the DBLP web API (https://dblp.org/search/…).  The
local XML dump contains the same data and avoids rate-limiting issues that
grow worse as the number of tracked conferences increases.  All new code
should use the extracted JSON files produced by this module.  Do NOT add
new DBLP API calls.
"""

import argparse
import json
import logging
import os
from collections import defaultdict
from gzip import GzipFile

import lxml.etree as ET

from ..generators.generate_author_stats import venue_to_conference

logger = logging.getLogger(__name__)
# Where we write the extracted JSON files
_EXTRACT_DIR_NAME = "dblp_extracted"


def _extract_dir(repo_root=None):
    """Return the directory where extracted JSON files are stored."""
    if repo_root is None:
        # __file__ = src/utils/dblp_extract.py → dirname x3 = repo root
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(repo_root, ".cache", _EXTRACT_DIR_NAME)


def _mtime_file(extract_dir):
    return os.path.join(extract_dir, "_dblp_mtime")


def _is_fresh(dblp_file, extract_dir):
    """Check whether the cached extraction is still valid."""
    mtime_path = _mtime_file(extract_dir)
    if not os.path.exists(mtime_path):
        return False
    try:
        with open(mtime_path) as f:
            cached_mtime = float(f.read().strip())
        return os.path.getmtime(dblp_file) == cached_mtime
    except (ValueError, OSError):
        return False


def extract_dblp(dblp_file):
    """Parse dblp.xml.gz and write JSON lookup files.

    Returns (papers_path, affiliations_path).
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    extract_dir = _extract_dir(repo_root)
    os.makedirs(extract_dir, exist_ok=True)

    papers_path = os.path.join(extract_dir, "papers_by_venue.json")
    affiliations_path = os.path.join(extract_dir, "affiliations.json")

    # Re-use cached files if the DBLP dump hasn't changed
    if _is_fresh(dblp_file, extract_dir):
        logger.warning("DBLP extraction cache is fresh — skipping parse")
        return papers_path, affiliations_path

    logger.info(f"Parsing DBLP XML ({dblp_file}) …")

    # {conf -> {year_str -> [paper_dict]}}
    papers = defaultdict(lambda: defaultdict(list))
    # {author_name -> affiliation}
    affiliations = {}

    dblp_stream = GzipFile(filename=dblp_file)
    iteration = 0

    for _, elem in ET.iterparse(
        dblp_stream,
        events=("end",),
        tag=("inproceedings", "article", "www"),
        load_dtd=True,
        recover=True,
        huge_tree=True,
    ):
        # --- Person records: extract affiliations ---
        if elem.tag == "www":
            authors = [a.text for a in elem.findall("author") if a.text]
            affil = None
            for note in elem.findall("note"):
                if note.get("type") == "affiliation" and note.text:
                    affil = note.text.strip()
                    break  # take the first (most recent) affiliation
            if affil:
                for name in authors:
                    if name not in affiliations:
                        affiliations[name] = affil
            elem.clear()
            continue

        # --- Papers ---
        booktitle = elem.findtext("booktitle") or elem.findtext("journal") or ""
        conf = venue_to_conference(booktitle)
        if conf:
            year_str = elem.findtext("year")
            if year_str:
                title = elem.findtext("title") or ""
                # Strip trailing period (DBLP convention)
                title = title.rstrip(".")

                # Extract DOI from <ee> elements
                doi = ""
                for ee in elem.findall("ee"):
                    if ee.text and "doi.org/" in ee.text:
                        doi = ee.text.split("doi.org/")[-1]
                        break

                authors = [a.text for a in elem.findall("author") if a.text]
                dblp_key = elem.get("key", "")

                papers[conf][year_str].append(
                    {
                        "title": title,
                        "authors": authors,
                        "doi": doi,
                        "dblp_key": dblp_key,
                    }
                )

        iteration += 1
        if iteration % 2_000_000 == 0:
            logger.info(f"  … {iteration // 1_000_000}M elements")
        elem.clear()

    dblp_stream.close()

    total_papers = sum(len(plist) for conf_years in papers.values() for plist in conf_years.values())
    logger.info(
        f"  Done — {iteration} elements, {total_papers} conference papers, {len(affiliations)} author affiliations"
    )

    # Write JSON files
    with open(papers_path, "w") as f:
        json.dump(papers, f, separators=(",", ":"))
    with open(affiliations_path, "w") as f:
        json.dump(affiliations, f, separators=(",", ":"))

    # Record the DBLP file mtime for freshness checks
    with open(_mtime_file(extract_dir), "w") as f:
        f.write(str(os.path.getmtime(dblp_file)))

    sz_p = os.path.getsize(papers_path) // 1024 // 1024
    sz_a = os.path.getsize(affiliations_path) // 1024 // 1024
    logger.info(f"  → {papers_path} ({sz_p} MB)")
    logger.info(f"  → {affiliations_path} ({sz_a} MB)")

    return papers_path, affiliations_path


# ── Public lookup helpers ────────────────────────────────────────────────────


def load_papers_by_venue(repo_root=None):
    """Load the pre-extracted papers index.

    Returns dict: conf (str) → year_str (str) → list of paper dicts.
    Each paper dict has keys: title, authors, doi, dblp_key.
    """
    path = os.path.join(_extract_dir(repo_root), "papers_by_venue.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def load_affiliations(repo_root=None):
    """Load the pre-extracted author → affiliation mapping.

    Returns dict: author_name (str) → affiliation (str).
    """
    path = os.path.join(_extract_dir(repo_root), "affiliations.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def find_affiliation(name, repo_root=None):
    """Look up an author's affiliation from the pre-extracted DBLP data.

    Tries exact match, then case-insensitive.  Returns the affiliation
    string or *None*.
    """
    affiliations = load_affiliations(repo_root)
    if not affiliations:
        return None
    # Exact match
    if name in affiliations:
        return affiliations[name]
    # Case-insensitive fallback
    lower = name.lower()
    for aname, affil in affiliations.items():
        if aname.lower() == lower:
            return affil
    return None


def papers_for_venue_year(conf, year, repo_root=None):
    """Convenience: return list of paper dicts for a conference/year.

    Falls back to empty list if data is not available.
    """
    data = load_papers_by_venue(repo_root)
    return data.get(conf, {}).get(str(year), [])


def paper_count_by_venue_year(repo_root=None):
    """Return dict: (conf, year_int) → paper_count."""
    data = load_papers_by_venue(repo_root)
    counts = {}
    for conf, years in data.items():
        for year_str, paper_list in years.items():
            counts[(conf, int(year_str))] = len(paper_list)
    return counts


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Pre-extract DBLP XML data to JSON lookup files")
    parser.add_argument(
        "--dblp_file",
        type=str,
        default="data/dblp/dblp.xml.gz",
        help="Path to dblp.xml.gz",
    )
    args = parser.parse_args()

    if not os.path.exists(args.dblp_file):
        logger.error(f"Error: {args.dblp_file} not found")
        logger.info("Run scripts/download_dblp.sh first.")
        return

    extract_dblp(args.dblp_file)


if __name__ == "__main__":
    from src.utils.logging_config import setup_logging

    setup_logging()

    main()
