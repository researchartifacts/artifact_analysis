#!/usr/bin/env python3
"""
Generate mapping of cited artifacts to their authors and institutions.

This script cross-references artifact_citations.json (artifacts with citations)
with author statistics to identify which authors and institutions created
artifacts that have been cited by other papers.

Outputs:
  assets/data/cited_artifacts_by_author.json - Map of authors to their cited artifacts
  assets/data/cited_artifacts_by_institution.json - Map of institutions to cited artifacts
  assets/data/cited_artifacts_list.json - List of all cited artifacts with creator info

Usage:
  python generate_cited_artifacts_list.py --data_dir ../reprodb.github.io
"""

import argparse
import json
import logging
import os
from collections import defaultdict

from src.utils.conference import normalize_title

logger = logging.getLogger(__name__)


def generate(data_dir: str) -> None:
    """Generate cited artifacts mappings"""

    # Paths to required files
    citations_path = os.path.join(data_dir, "assets", "data", "artifact_citations.json")
    paper_authors_map_path = os.path.join(data_dir, "assets", "data", "paper_authors_map.json")
    combined_rankings_path = os.path.join(data_dir, "assets", "data", "combined_rankings.json")
    institution_rankings_path = os.path.join(data_dir, "assets", "data", "institution_rankings.json")

    out_author_cited = os.path.join(data_dir, "assets", "data", "cited_artifacts_by_author.json")
    out_institution_cited = os.path.join(data_dir, "assets", "data", "cited_artifacts_by_institution.json")
    out_cited_list = os.path.join(data_dir, "assets", "data", "cited_artifacts_list.json")

    # Load data
    if not os.path.exists(citations_path):
        logger.error(f"Error: {citations_path} not found. Run generate_artifact_citations.py first")
        return

    with open(citations_path, "r") as f:
        citations = json.load(f)

    # Build lookup: normalized title -> citation data
    cited_artifacts = {}
    for citation_entry in citations:
        if citation_entry.get("cited_by_count") and citation_entry["cited_by_count"] > 0:
            norm_title = normalize_title(citation_entry.get("title", ""))
            if norm_title:
                cited_artifacts[norm_title] = citation_entry

    logger.info(f"Found {len(cited_artifacts)} artifacts with citations")

    if not cited_artifacts:
        logger.warning("No cited artifacts found. Skipping mapping generation.")
        return

    # Load paper-to-authors mapping
    paper_author_map = {}
    if os.path.exists(paper_authors_map_path):
        with open(paper_authors_map_path, "r") as f:
            papers = json.load(f)
            for paper in papers:
                norm_title = normalize_title(paper.get("title", ""))
                if norm_title:
                    paper_author_map[norm_title] = paper
    else:
        logger.warning(
            f"Warning: {paper_authors_map_path} not found. Run generate_author_stats.py first for full mapping."
        )

    # Load institution and author ranking data
    author_info = {}
    institution_info = {}

    if os.path.exists(combined_rankings_path):
        with open(combined_rankings_path, "r") as f:
            rankings = json.load(f)
            for author in rankings:
                author_name = author.get("name", "")
                author_info[author_name] = {
                    "display_name": author.get("display_name", ""),
                    "affiliation": author.get("affiliation", ""),
                    "display_affiliation": author.get("display_affiliation", ""),
                }

    if os.path.exists(institution_rankings_path):
        with open(institution_rankings_path, "r") as f:
            institutions = json.load(f)
            for inst in institutions:
                inst_name = inst.get("institution", "")
                institution_info[inst_name] = {
                    "display_name": inst.get("display_name", ""),
                }

    # Build mapping: author -> cited artifacts
    cited_by_author = defaultdict(
        lambda: {
            "display_name": "",
            "affiliation": "",
            "display_affiliation": "",
            "cited_artifacts": [],
            "total_citations": 0,
        }
    )

    # Build mapping: institution -> cited artifacts
    cited_by_institution = defaultdict(
        lambda: {
            "display_name": "",
            "cited_artifacts": [],
            "total_citations": 0,
            "member_count": 0,
        }
    )

    # Build list of all cited artifacts with creator info
    cited_artifacts_list = []

    # Cross-reference: for each cited artifact, find its authors
    for norm_title, citation_data in cited_artifacts.items():
        paper = paper_author_map.get(norm_title)

        artifact_entry = {
            "title": citation_data.get("title", ""),
            "conference": citation_data.get("conference", ""),
            "year": citation_data.get("year", ""),
            "doi": citation_data.get("doi", ""),
            "cited_by_count": citation_data.get("cited_by_count", 0),
            "authors": [],
            "institutions": set(),
        }

        if paper:
            authors = paper.get("authors", [])
            artifact_entry["authors"] = authors

            # Add to author mappings
            for author_name in authors:
                author_data = author_info.get(author_name, {})

                if author_name not in cited_by_author:
                    cited_by_author[author_name]["display_name"] = author_data.get("display_name", author_name)
                    cited_by_author[author_name]["affiliation"] = author_data.get("affiliation", "")
                    cited_by_author[author_name]["display_affiliation"] = author_data.get("display_affiliation", "")

                cited_by_author[author_name]["cited_artifacts"].append(
                    {
                        "title": artifact_entry["title"],
                        "conference": artifact_entry["conference"],
                        "year": artifact_entry["year"],
                        "citations": artifact_entry["cited_by_count"],
                    }
                )
                cited_by_author[author_name]["total_citations"] += artifact_entry["cited_by_count"]

                # Track institutions
                affiliation = author_data.get("affiliation", "")
                if affiliation:
                    artifact_entry["institutions"].add(affiliation)

                    if affiliation not in cited_by_institution:
                        inst_data = institution_info.get(affiliation, {})
                        cited_by_institution[affiliation]["display_name"] = inst_data.get("display_name", affiliation)

                    if not any(
                        a["title"] == artifact_entry["title"]
                        for a in cited_by_institution[affiliation]["cited_artifacts"]
                    ):
                        cited_by_institution[affiliation]["cited_artifacts"].append(
                            {
                                "title": artifact_entry["title"],
                                "conference": artifact_entry["conference"],
                                "year": artifact_entry["year"],
                                "citations": artifact_entry["cited_by_count"],
                                "authors": [author_name],
                            }
                        )
                        cited_by_institution[affiliation]["total_citations"] += artifact_entry["cited_by_count"]

        artifact_entry["institutions"] = list(artifact_entry["institutions"])
        cited_artifacts_list.append(artifact_entry)

    # Write output files
    os.makedirs(os.path.dirname(out_author_cited), exist_ok=True)

    with open(out_author_cited, "w") as f:
        # Convert defaultdict to regular dict for JSON serialization
        out_dict = {k: v for k, v in cited_by_author.items()}
        # Sort by total citations
        sort_dict = {
            k: out_dict[k] for k in sorted(out_dict.keys(), key=lambda x: out_dict[x]["total_citations"], reverse=True)
        }
        json.dump(sort_dict, f, indent=2, ensure_ascii=False)

    with open(out_institution_cited, "w") as f:
        out_dict = {k: v for k, v in cited_by_institution.items()}
        sort_dict = {
            k: out_dict[k] for k in sorted(out_dict.keys(), key=lambda x: out_dict[x]["total_citations"], reverse=True)
        }
        json.dump(sort_dict, f, indent=2, ensure_ascii=False)

    with open(out_cited_list, "w") as f:
        # Sort by citation count
        sorted_list = sorted(cited_artifacts_list, key=lambda x: x["cited_by_count"], reverse=True)
        json.dump(sorted_list, f, indent=2, ensure_ascii=False)

    logger.info(f"Wrote {out_author_cited} ({len(cited_by_author)} authors with cited artifacts)")
    logger.info(f"Wrote {out_institution_cited} ({len(cited_by_institution)} institutions with cited artifacts)")
    logger.info(f"Wrote {out_cited_list} ({len(cited_artifacts_list)} cited artifacts)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mapping of cited artifacts to authors/institutions")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to reprodb.github.io")
    args = parser.parse_args()
    generate(args.data_dir)


if __name__ == "__main__":
    from src.utils.logging_config import setup_logging

    setup_logging()

    main()
