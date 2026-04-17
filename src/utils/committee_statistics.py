from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import yaml
from pytrie import Trie
from parse_committee_md import get_committees
from repo_utils import download_file
from thefuzz import fuzz

logger = logging.getLogger(__name__)

_OVERRIDES_PATH = Path(__file__).resolve().parents[2] / "data" / "university_country_overrides.yaml"


def calculate_affiliation_stats(results: dict[str, list[dict]]) -> dict[str, list[dict]]:
    affiliation_stats: dict[str, list[dict]] = {}
    for name in results:
        for member in results[name]:
            affiliation = member["affiliation"]
            if affiliation not in affiliation_stats:
                affiliation_stats[affiliation] = []
                affiliation_stats[affiliation].append(member)
            else:
                affiliation_stats[affiliation].append(member)

    return affiliation_stats


def calculate_affiliation_stats_per_year(results: dict[str, list[dict]]) -> dict[str, dict[str, list[dict]]]:
    affiliation_stats: dict[str, dict[str, list[dict]]] = {}
    for name in results:
        for member in results[name]:
            affiliation = member["affiliation"]
            if affiliation not in affiliation_stats:
                affiliation_stats[affiliation] = {}
            if name not in affiliation_stats[affiliation]:
                affiliation_stats[affiliation][name] = []
            affiliation_stats[affiliation][name].append(member)

    return affiliation_stats


def aec_retention(results: dict[str, list[dict]]) -> None:
    conf_mem_set: dict[str, dict[str, bool]] = {}
    for conf in results:
        conf_mem_set[conf] = {}
        for member in results[conf]:
            conf_mem_set[conf][member["name"]] = True

    retention_counts: dict[str, dict[str, int]] = {}
    for name in results:
        for comp_name in results:
            if name not in retention_counts:
                retention_counts[name] = {}
            retention_counts[name][comp_name] = 0

            for mem_name in conf_mem_set[name]:
                retention_counts[name][comp_name] += 1 if mem_name in conf_mem_set[comp_name] else 0

    # print table header
    logger.info(f"conferences;{';'.join(results.keys())}")
    for name in results:
        logger.info(f"{name};{';'.join(str(n) for n in retention_counts[name].values())}")


def classify_aec_by_country(results):
    university_info = json.loads(
        download_file(
            "https://github.com/Hipo/university-domains-list/raw/refs/heads/master/world_universities_and_domains.json"
        )
    )
    with open(_OVERRIDES_PATH) as fh:
        university_info.extend(yaml.safe_load(fh))

    name_index = {}
    for uni in university_info:
        name_index[uni["name"].lower()] = uni
        splitted = uni["name"].split(" ")
        if len(splitted) > 1:
            for splitted_name in splitted:
                name_index[splitted_name.lower()] = uni
            if len(splitted) > 2:
                for s_cnt in range(1, len(splitted) - 1):
                    name_index[" ".join(splitted[s_cnt:]).lower()] = uni

    prefix_tree = Trie(**name_index)
    per_year_country_stats: dict[str, dict[str, int]] = {}
    failed = []
    for conf, members in results.items():
        per_year_country_stats[conf] = {}
        for member in members:
            affiliation = member["affiliation"].lower()
            university = prefix_tree.values(prefix=affiliation)

            if university:
                uni = university[0]
                per_year_country_stats[conf][uni["country"]] = per_year_country_stats[conf].get(uni["country"], 0) + 1
            else:
                best_match: dict | None = None
                best_match_ratio = 0
                for name in name_index:
                    ratio = fuzz.ratio(name, affiliation)
                    if ratio > best_match_ratio:
                        best_match_ratio = ratio
                        best_match = name_index[name]

                if best_match_ratio > 80 and best_match is not None:
                    per_year_country_stats[conf][best_match["country"]] = (
                        per_year_country_stats[conf].get(best_match["country"], 0) + 1
                    )
                else:
                    country_info = best_match["country"] if best_match else "unknown"
                    failed.append(affiliation)
                    logger.warning(f"Failed {affiliation} in {country_info} with ratio {best_match_ratio}")

    return per_year_country_stats, failed


def aec_by_country(results):
    per_year_country_stats, failed = classify_aec_by_country(results)

    # get all affiliations
    countries = set()
    for country_year in per_year_country_stats.values():
        for country in country_year:
            countries.add(country)

    # print table header
    logger.info("countries;%s;sum", ";".join(results.keys()))
    for country in sorted(countries):
        parts = [country]
        total = 0
        for conf in per_year_country_stats:
            count = per_year_country_stats[conf].get(country, 0)
            parts.append(str(count))
            total += count
        parts.append(str(total))
        logger.info(";".join(parts))

    logger.warning(f"Number failed to identify {len(failed)}")
    logger.warning(f"List of failed affiliations:{', '.join(failed)}")


def main():
    parser = argparse.ArgumentParser(description="Scraping results of sys/secartifacts.github.io from conferences.")
    parser.add_argument(
        "--conf_regex", type=str, default=".20[1|2][0-9]", help="Regular expression for conference name and or years"
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="sys",
        help="Prefix of artifacts website like sys for sysartifacts or sec for secartifacts",
    )
    parser.add_argument("--analyze_affiliation", action="store_true", help="Analyze affiliation of committee members")
    parser.add_argument(
        "--analyze_affiliation_per_conference", action="store_true", help="Analyze affiliation of committee members"
    )
    parser.add_argument(
        "--analyze_aec_retention",
        action="store_true",
        help="Analyze if AEC members stay over multiple years or between conferences",
    )
    parser.add_argument(
        "--analyze_by_country", action="store_true", help="Analyze from which countries AEC members are"
    )

    args = parser.parse_args()

    results = get_committees(args.conf_regex, args.prefix)

    if args.analyze_affiliation:
        affiliation_stats = calculate_affiliation_stats(results)
        # print table header
        logger.info("Affiliation; Count")
        for affiliation in sorted(affiliation_stats, key=lambda x: len(affiliation_stats[x]), reverse=True):
            logger.info(f"{affiliation}; {len(affiliation_stats[affiliation])}")

    if args.analyze_affiliation_per_conference:
        affiliation_stats_by_year = calculate_affiliation_stats_per_year(results)
        # print table header
        logger.info(f"Affiliation;{';'.join(results.keys())};sum")

        for aff_name, aff_data in sorted(affiliation_stats_by_year.items()):
            counts = []
            for conference in results:
                if conference in aff_data:
                    counts.append(len(aff_data[conference]))
                else:
                    counts.append(0)
            logger.info(f"{aff_name};{';'.join(str(i) for i in counts)};{sum(counts)}")

    if args.analyze_aec_retention:
        aec_retention(results)

    if args.analyze_by_country:
        aec_by_country(results)


if __name__ == "__main__":
    from src.utils.logging_config import setup_logging

    setup_logging()

    main()
