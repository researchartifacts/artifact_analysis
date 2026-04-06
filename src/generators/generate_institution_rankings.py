#!/usr/bin/env python3
"""
Generate institution rankings by aggregating combined ranking data by affiliation.
Creates JSON files for overall, systems, and security institution rankings.
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def load_combined_ranking(path):
    """Load combined ranking JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_affiliation(affiliation):
    """Normalize affiliation to a canonical base institution name."""
    if not affiliation:
        return ""
    aff = affiliation.strip()

    # Technical University of Munich (TUM) aliases
    if re.search(r"\b(TU\s*Munich|TUM)\b|Technical\s+University\s+(of\s+)?Munich", aff, re.IGNORECASE):
        return "Technical University of Munich"

    # KU Leuven / DistriNet aliases
    if re.search(
        r"distrinet|imec\s*-?\s*distrinet|\bku\s*leuven\b|katholieke\s+universiteit\s+leuven", aff, re.IGNORECASE
    ):
        return "KU Leuven"

    # Special case: CISPA - normalize all variants to a canonical form
    if "CISPA" in aff:
        return "CISPA Helmholtz Center for Information Security"

    # Split by comma or period to get base institution (before location)
    parts = re.split(r"[,.]", aff)
    if not parts:
        return ""
    base = parts[0].strip()

    # Remove trailing abbreviations in parentheses (e.g., "(SJTU)", "(HKUST)")
    base = re.sub(r"\s*\([^)]*\)\s*$", "", base).strip()

    # Keep UC campuses distinct when present
    if base.lower() == "university of california" and len(parts) > 1:
        campus = parts[1].strip()
        if campus and campus.lower() not in ["usa", "ca", "california"]:
            return base + ", " + campus

    # Apply additional normalization to the base name
    # Remove leading "The"
    if base.lower().startswith("the "):
        base = base[4:].strip()

    # Remove trailing location suffixes like "Shanghai, China" → "Shanghai"
    # This handles "Shanghai Jiao Tong University Shanghai" case
    base_words = base.split()
    if len(base_words) > 1:
        # Check if last word looks like a location (city name repeated or geographic area)
        last_word = base_words[-1]
        # Remove if it's a short word that looks like a location abbreviation or repeated location
        if (
            len(last_word) <= 3 or last_word in ["Shanghai", "China", "USA", "UK", "Germany", "France", "Japan"]
        ) and last_word in base[: -len(last_word)]:  # If this word appears earlier in the string
            base = " ".join(base_words[:-1]).strip()

    # Normalize common typos and fixes
    # Fix "University of Pennsylvani" → "University of Pennsylvania"
    if "pennsylvani" in base.lower() and "pennsylvania" not in base.lower():
        base = re.sub(r"pennsylvani", "Pennsylvania", base, flags=re.IGNORECASE)

    # Fix "hanghai" → "Shanghai" (missing S)
    if "hanghai" in base.lower():
        base = re.sub(r"[Ss]?hanghai", "Shanghai", base, flags=re.IGNORECASE)

    # Fix "Jiaotong" → "Jiao Tong" (missing space)
    if "jiaotong" in base.lower() and "jiao tong" not in base.lower():
        base = re.sub(r"jiaotong", "Jiao Tong", base, flags=re.IGNORECASE)

    # Remove common corporate suffixes
    if base.lower().endswith(" ltd"):
        base = base[:-4].strip()
    elif (
        base.lower().endswith(" co.")
        or base.lower().endswith(" co")
        or base.lower().endswith(" inc.")
        or base.lower().endswith(" inc")
    ):
        base = base.rsplit(None, 1)[0].strip() if " " in base else base

    # Fix case inconsistencies in known institutions
    if "sun yat" in base.lower() and "university" in base.lower():
        base = "Sun Yat-sen University"

    if "oregon state" in base.lower():
        base = "Oregon State University"

    if "universit" in base.lower() and "catholique" in base.lower() and "louvain" in base.lower():
        base = "Universit Catholique de Louvain"

    return base


def aggregate_by_institution(combined_data):
    """Aggregate individual rankings by institution affiliation."""
    inst_data = defaultdict(
        lambda: {
            "affiliation": "",
            "combined_score": 0,
            "artifact_score": 0,
            "artifact_citations": 0,
            "citation_score": 0,
            "ae_score": 0,
            "artifacts": 0,
            "badges_functional": 0,
            "badges_reproducible": 0,
            "ae_memberships": 0,
            "chair_count": 0,
            "total_papers": 0,
            "num_authors": 0,
            "conferences": set(),
            "years": defaultdict(int),
        }
    )

    for person in combined_data:
        affiliation = normalize_affiliation(person.get("affiliation", "").strip())

        # Skip entries with no affiliation or placeholder affiliations
        if not affiliation or affiliation == "Unknown" or affiliation.startswith("_"):
            affiliation = "Unknown"

        inst = inst_data[affiliation]
        inst["affiliation"] = affiliation
        inst["combined_score"] += person.get("combined_score", 0)
        inst["artifact_score"] += person.get("artifact_score", 0)
        inst["artifact_citations"] += person.get("artifact_citations", 0)
        inst["citation_score"] += person.get("citation_score", 0)
        inst["ae_score"] += person.get("ae_score", 0)
        inst["artifacts"] += person.get("artifacts", 0)
        inst["badges_functional"] += person.get("badges_functional", 0)
        inst["badges_reproducible"] += person.get("badges_reproducible", 0)
        inst["ae_memberships"] += person.get("ae_memberships", 0)
        inst["chair_count"] += person.get("chair_count", 0)
        inst["total_papers"] += person.get("total_papers", 0)
        inst["num_authors"] += 1

        # Aggregate conferences
        if person.get("conferences"):
            inst["conferences"].update(person["conferences"])

        # Aggregate years
        if person.get("years"):
            for year, count in person["years"].items():
                inst["years"][year] += count

    # Convert to list and calculate derived fields
    institutions = []
    for affiliation, data in inst_data.items():
        if data["artifacts"] > data["total_papers"]:
            raise ValueError(
                f"Invariant violation for institution '{affiliation}': artifacts ({data['artifacts']}) > total_papers ({data['total_papers']})"
            )
        if data["badges_reproducible"] > data["artifacts"]:
            raise ValueError(
                f"Invariant violation for institution '{affiliation}': reproduced_badges ({data['badges_reproducible']}) > artifacts ({data['artifacts']})"
            )
        if data["badges_functional"] > data["artifacts"]:
            raise ValueError(
                f"Invariant violation for institution '{affiliation}': functional_badges ({data['badges_functional']}) > artifacts ({data['artifacts']})"
            )

        # Calculate artifact rate
        artifact_rate = 0
        if data["total_papers"] > 0:
            artifact_rate = round((data["artifacts"] / data["total_papers"]) * 100, 1)

        # Calculate A:E ratio
        ae_ratio = None
        if data["ae_score"] > 0:
            ae_ratio = round(data["artifact_score"] / data["ae_score"], 2)
        elif data["artifact_score"] > 0:
            ae_ratio = None  # Artifact-only, will display as ∞
        else:
            ae_ratio = 0.0  # Neither artifacts nor AE service

        # Classify institution role based on A:E ratio
        if ae_ratio is None:
            # Artifact-only (ae_score == 0, artifact_score > 0) → creator
            role = "Producer"
        elif ae_ratio == 0.0:
            # AE-only or neither (artifact_score == 0) → evaluator
            role = "Consumer"
        elif ae_ratio > 2.0:
            role = "Producer"
        elif ae_ratio < 0.5:
            role = "Consumer"
        else:
            role = "Balanced"

        # Only include institutions with meaningful contributions, excluding incomplete affiliations
        if data["combined_score"] >= 3 and affiliation.strip() not in ("Univ", "University", "Unknown", "_"):
            institutions.append(
                {
                    "affiliation": data["affiliation"],
                    "combined_score": data["combined_score"],
                    "artifact_score": data["artifact_score"],
                    "artifact_citations": data["artifact_citations"],
                    "citation_score": data["citation_score"],
                    "ae_score": data["ae_score"],
                    "ae_ratio": ae_ratio,
                    "role": role,
                    "artifacts": data["artifacts"],
                    "badges_functional": data["badges_functional"],
                    "badges_reproducible": data["badges_reproducible"],
                    "ae_memberships": data["ae_memberships"],
                    "chair_count": data["chair_count"],
                    "total_papers": data["total_papers"],
                    "artifact_rate": artifact_rate,
                    "num_authors": data["num_authors"],
                    "conferences": sorted(list(data["conferences"])),
                    "years": dict(data["years"]),
                }
            )

    # Sort by combined_score descending
    institutions.sort(key=lambda x: x["combined_score"], reverse=True)

    return institutions


def main():
    """Generate institution ranking JSON files."""
    parser = argparse.ArgumentParser(description="Generate institution rankings")
    parser.add_argument("--data_dir", type=str, default=None, help="Path to website root (researchartifacts.github.io)")
    args = parser.parse_args()

    if args.data_dir:
        website_path = Path(args.data_dir)
    else:
        base_path = Path(__file__).parent
        website_path = base_path.parent.parent.parent / "researchartifacts.github.io"
    data_dir = website_path / "assets" / "data"

    # Process overall combined ranking
    print("Processing overall combined ranking...")
    combined_path = data_dir / "combined_rankings.json"
    if combined_path.exists():
        combined_data = load_combined_ranking(combined_path)
        institutions = aggregate_by_institution(combined_data)

        output_path = data_dir / "institution_rankings.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(institutions, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Generated {output_path} ({len(institutions)} institutions)")
    else:
        print(f"  ✗ {combined_path} not found")

    # Process systems combined ranking
    print("Processing systems combined ranking...")
    systems_path = data_dir / "systems_combined_rankings.json"
    if systems_path.exists():
        systems_data = load_combined_ranking(systems_path)
        systems_institutions = aggregate_by_institution(systems_data)

        output_path = data_dir / "systems_institution_rankings.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(systems_institutions, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Generated {output_path} ({len(systems_institutions)} institutions)")
    else:
        print(f"  ✗ {systems_path} not found")

    # Process security combined ranking
    print("Processing security combined ranking...")
    security_path = data_dir / "security_combined_rankings.json"
    if security_path.exists():
        security_data = load_combined_ranking(security_path)
        security_institutions = aggregate_by_institution(security_data)

        output_path = data_dir / "security_institution_rankings.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(security_institutions, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Generated {output_path} ({len(security_institutions)} institutions)")
    else:
        print(f"  ✗ {security_path} not found")


if __name__ == "__main__":
    main()
