#!/usr/bin/env python3
"""
Analyze AEC member retention in three dimensions:
  (a) Within-conference retention (same conference, different years)
  (b) Cross-conference retention (different conference, same area)
  (c) Cross-area retention (systems ↔ security)

Compares results with EuroSys claim of "very little retention"
(D'Elia et al., ACM REP '25).
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

from src.scrapers.sys_sec_committee_scrape import get_committees
from src.scrapers.alternative_committee_scrape import (
    get_alternative_committees,
    USENIX_CONF_SLUGS,
    USENIX_KNOWN_YEARS,
    CHES_KNOWN_YEARS,
    PETS_KNOWN_YEARS,
)
from src.utils.conference import (
    conf_area as _conf_area,
    parse_conf_year as _extract_conf_year,
    clean_name as _display_name,
    normalize_name as _normalize_name,
)

MIN_COMMITTEE_SIZE = 5
PLACEHOLDER_NAMES = {'you?', 'you', 'tba', 'tbd', 'n/a', '', 'title: organizers'}


def _clean_committee(members):
    cleaned = []
    for m in members:
        name = m.get('name', '').strip()
        link_match = re.match(r'\[([^\]]+)\]\([^)]*\)', name)
        if link_match:
            name = link_match.group(1)
        name = re.sub(r'<br\s*/?>$', '', name).strip()
        if name.lower() in PLACEHOLDER_NAMES or len(name) <= 1:
            continue
        if 'contact' in name.lower() or 'reach' in name.lower() or 'mailto:' in name.lower():
            continue
        name = _display_name(name)
        cleaned.append({'name': name, 'affiliation': m.get('affiliation', '')})
    return cleaned


def _is_valid_committee(members):
    if not members:
        return False
    return len(members) >= MIN_COMMITTEE_SIZE


def scrape_all_committees(conf_regex):
    """Scrape committee data from all sources, returning {conf_year: [members]}."""
    print("Scraping systems committees from sysartifacts...")
    sys_results = get_committees(conf_regex, 'sys')
    print(f"  Found {len(sys_results)} systems conference-years")

    print("Scraping security committees from secartifacts...")
    sec_results = get_committees(conf_regex, 'sec')
    print(f"  Found {len(sec_results)} security conference-years")

    all_results = {}
    all_results.update(sys_results)
    all_results.update(sec_results)

    # Clean
    for cy in list(all_results.keys()):
        all_results[cy] = _clean_committee(all_results[cy])

    # Supplement with alternative sources (skip PETs — site unreliable)
    conferences_needed = {}
    for conf, slug in USENIX_CONF_SLUGS.items():
        for year in USENIX_KNOWN_YEARS.get(conf, []):
            cy = f"{conf}{year}"
            if re.search(conf_regex, cy):
                if cy not in all_results or not _is_valid_committee(all_results.get(cy)):
                    area = 'systems' if conf in SYSTEMS_CONFS else 'security'
                    conferences_needed[cy] = area

    for year in CHES_KNOWN_YEARS:
        cy = f"ches{year}"
        if re.search(conf_regex, cy):
            if cy not in all_results or not _is_valid_committee(all_results.get(cy)):
                conferences_needed[cy] = 'security'

    # Skip PETS — petsymposium.org is unreliable/timing out
    # The secartifacts YAML has PETs chairs but not full committees

    if conferences_needed:
        print(f"  Fetching alternative sources for {len(conferences_needed)} conference-years...")
        alt_results = get_alternative_committees(conferences_needed)
        for cy, members in alt_results.items():
            cleaned = _clean_committee(members)
            if cleaned:
                all_results[cy] = cleaned
                print(f"    ✓ {cy}: {len(cleaned)} members")

    return all_results


def build_member_map(all_results):
    """Build normalized_name → set of (conf, year) tuples."""
    member_map = defaultdict(set)  # norm_name → {(CONF, year)}

    for conf_year, members in all_results.items():
        conf_name, year = _extract_conf_year(conf_year)
        if year is None:
            continue
        area = _conf_area(conf_year)
        for m in members:
            name = m.get('name', '').strip()
            if not name:
                continue
            norm = _normalize_name(name)
            member_map[norm].add((conf_name, year))

    return member_map


def analyze_retention(all_results):
    """Compute retention in three dimensions."""
    member_map = build_member_map(all_results)
    conf_to_area_map = {cy: _conf_area(cy) for cy in all_results}

    # Build per-conference-year member sets for year-over-year analysis
    # {(CONF, year) → set of normalized names}
    cy_members = defaultdict(set)
    for norm, conf_years in member_map.items():
        for (conf, year) in conf_years:
            cy_members[(conf, year)].add(norm)

    # Get all conferences and years
    all_confs = sorted(set(c for c, y in cy_members.keys()))
    all_years = sorted(set(y for c, y in cy_members.keys()))

    # ── (a) Within-conference retention ──────────────────────────────────
    # For each conference, what % of year Y members were also in year Y-1
    # for THE SAME conference?
    print("\n" + "=" * 70)
    print("(a) WITHIN-CONFERENCE RETENTION (same conference, year Y-1 → Y)")
    print("=" * 70)

    within_conf_data = {}
    for conf in all_confs:
        conf_years = sorted(y for c, y in cy_members.keys() if c == conf)
        if len(conf_years) < 2:
            continue
        within_conf_data[conf] = {}
        for i in range(1, len(conf_years)):
            prev_year = conf_years[i - 1]
            curr_year = conf_years[i]
            prev_members = cy_members[(conf, prev_year)]
            curr_members = cy_members[(conf, curr_year)]
            retained = prev_members & curr_members
            if curr_members:
                pct = len(retained) / len(curr_members) * 100
            else:
                pct = 0
            within_conf_data[conf][(prev_year, curr_year)] = {
                'prev_size': len(prev_members),
                'curr_size': len(curr_members),
                'retained': len(retained),
                'retained_pct': pct,
            }
            print(f"  {conf} {prev_year}→{curr_year}: "
                  f"{len(retained)}/{len(curr_members)} retained = {pct:.1f}%  "
                  f"(prev={len(prev_members)}, curr={len(curr_members)})")

    # Aggregate within-conference retention by year
    print("\n  --- Aggregated within-conference retention by year ---")
    for year in all_years:
        total_retained = 0
        total_curr = 0
        for conf in all_confs:
            for (py, cy), data in within_conf_data.get(conf, {}).items():
                if cy == year:
                    total_retained += data['retained']
                    total_curr += data['curr_size']
        if total_curr > 0:
            pct = total_retained / total_curr * 100
            print(f"  Year {year}: {total_retained}/{total_curr} = {pct:.1f}%")

    # Aggregate by area
    for area_label, area_confs in [("SYSTEMS", SYSTEMS_CONFS), ("SECURITY", SECURITY_CONFS)]:
        print(f"\n  --- {area_label} within-conference retention by year ---")
        for year in all_years:
            total_retained = 0
            total_curr = 0
            for conf in all_confs:
                if conf.lower() not in area_confs:
                    continue
                for (py, cy), data in within_conf_data.get(conf, {}).items():
                    if cy == year:
                        total_retained += data['retained']
                        total_curr += data['curr_size']
            if total_curr > 0:
                pct = total_retained / total_curr * 100
                print(f"  Year {year}: {total_retained}/{total_curr} = {pct:.1f}%")

    # ── (b) Cross-conference retention (same area) ───────────────────────
    # For each year, what % of members served on a DIFFERENT conference
    # in the same area the previous year?
    print("\n" + "=" * 70)
    print("(b) CROSS-CONFERENCE RETENTION (different conf, same area, Y-1 → Y)")
    print("=" * 70)

    for area_label, area_confs in [("SYSTEMS", SYSTEMS_CONFS), ("SECURITY", SECURITY_CONFS)]:
        print(f"\n  --- {area_label} ---")
        area_conf_names = [c for c in all_confs if c.lower() in area_confs]

        for year in all_years:
            prev_year = year - 1
            # Members in this area, this year
            curr_area_members = set()
            for conf in area_conf_names:
                curr_area_members |= cy_members.get((conf, year), set())
            if not curr_area_members:
                continue

            # Members in same area, previous year, any conference
            prev_area_members = set()
            for conf in area_conf_names:
                prev_area_members |= cy_members.get((conf, prev_year), set())

            # Of current year's members, how many were in same area last year
            # but on a DIFFERENT conference?
            retained_same_conf = set()
            retained_diff_conf = set()
            for member in curr_area_members:
                if member in prev_area_members:
                    # Check if same conference or different
                    curr_confs = {c for c in area_conf_names if member in cy_members.get((c, year), set())}
                    prev_confs = {c for c in area_conf_names if member in cy_members.get((c, prev_year), set())}
                    if curr_confs & prev_confs:
                        retained_same_conf.add(member)
                    else:
                        retained_diff_conf.add(member)

            total_retained = len(retained_same_conf) + len(retained_diff_conf)
            if curr_area_members:
                pct_same = len(retained_same_conf) / len(curr_area_members) * 100
                pct_diff = len(retained_diff_conf) / len(curr_area_members) * 100
                pct_total = total_retained / len(curr_area_members) * 100
                newcomers = len(curr_area_members) - total_retained
                pct_new = newcomers / len(curr_area_members) * 100
                print(f"  {year}: total={len(curr_area_members)}  "
                      f"same-conf={len(retained_same_conf)} ({pct_same:.1f}%)  "
                      f"diff-conf={len(retained_diff_conf)} ({pct_diff:.1f}%)  "
                      f"total-retained={total_retained} ({pct_total:.1f}%)  "
                      f"newcomers={newcomers} ({pct_new:.1f}%)")

    # ── (c) Cross-area retention ─────────────────────────────────────────
    # Members who served in BOTH systems and security conferences
    print("\n" + "=" * 70)
    print("(c) CROSS-AREA RETENTION (systems ↔ security)")
    print("=" * 70)

    # Per member: which areas did they serve in?
    cross_area_members = set()
    for norm, conf_years in member_map.items():
        areas = set()
        for (conf, year) in conf_years:
            cy_str = f"{conf.lower()}{year}"
            area = _conf_area(cy_str)
            if area in ('systems', 'security'):
                areas.add(area)
        if len(areas) == 2:
            cross_area_members.add(norm)

    total_unique = len(member_map)
    print(f"\n  Total unique members: {total_unique}")
    print(f"  Cross-area members (served in both systems + security): {len(cross_area_members)}")
    print(f"  Cross-area percentage: {len(cross_area_members)/total_unique*100:.1f}%")

    # Year-by-year cross-area analysis
    print("\n  --- Cross-area by year ---")
    for year in all_years:
        sys_members_year = set()
        sec_members_year = set()
        for conf in all_confs:
            area = _conf_area(f"{conf.lower()}2020")  # area doesn't depend on year
            members = cy_members.get((conf, year), set())
            if area == 'systems':
                sys_members_year |= members
            elif area == 'security':
                sec_members_year |= members

        if sys_members_year and sec_members_year:
            overlap = sys_members_year & sec_members_year
            # Members who were in security previously, now in systems (or vice versa)
            print(f"  {year}: systems={len(sys_members_year)}, security={len(sec_members_year)}, "
                  f"overlap={len(overlap)} ({len(overlap)/len(sys_members_year|sec_members_year)*100:.1f}%)")
        elif sys_members_year or sec_members_year:
            total = len(sys_members_year) + len(sec_members_year)
            print(f"  {year}: systems={len(sys_members_year)}, security={len(sec_members_year)}, overlap=0")

    # Cross-area year-over-year: members in area X in year Y who were in area Z in year Y-1
    print("\n  --- Cross-area mobility (area X this year, area Y last year) ---")
    for year in all_years:
        prev_year = year - 1
        sys_curr = set()
        sec_curr = set()
        sys_prev = set()
        sec_prev = set()
        for conf in all_confs:
            area = _conf_area(f"{conf.lower()}2020")
            if area == 'systems':
                sys_curr |= cy_members.get((conf, year), set())
                sys_prev |= cy_members.get((conf, prev_year), set())
            elif area == 'security':
                sec_curr |= cy_members.get((conf, year), set())
                sec_prev |= cy_members.get((conf, prev_year), set())

        # Security→Systems mobility
        sec_to_sys = sys_curr & sec_prev - sys_prev
        # Systems→Security mobility
        sys_to_sec = sec_curr & sys_prev - sec_prev
        if sys_curr or sec_curr:
            print(f"  {year}: sec→sys={len(sec_to_sys)}, sys→sec={len(sys_to_sec)}")

    # ── Summary comparison with EuroSys ──────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY: Comparison with EuroSys findings (D'Elia et al., ACM REP '25)")
    print("=" * 70)
    print("""
EuroSys claim: "the number of returning members remains relatively small,
suggesting that most AEC members are new." (Based on EuroSys-only data, Table 4b)

Our findings:
""")

    # Compute EuroSys-specific retention if available
    eurosys_years = sorted(y for c, y in cy_members.keys() if c == 'EUROSYS')
    if len(eurosys_years) >= 2:
        print("  EuroSys within-conference retention (for direct comparison):")
        for i in range(1, len(eurosys_years)):
            py, cy = eurosys_years[i - 1], eurosys_years[i]
            prev = cy_members.get(('EUROSYS', py), set())
            curr = cy_members.get(('EUROSYS', cy), set())
            retained = prev & curr
            if curr:
                pct = len(retained) / len(curr) * 100
                print(f"    {py}→{cy}: {len(retained)}/{len(curr)} = {pct:.1f}%")

    # Overall within-conf average
    all_within = []
    for conf, pairs in within_conf_data.items():
        for _, data in pairs.items():
            if data['curr_size'] > 10:  # skip tiny committees
                all_within.append(data['retained_pct'])
    if all_within:
        avg_within = sum(all_within) / len(all_within)
        print(f"\n  Average within-conference retention: {avg_within:.1f}%")

    # Average cross-conference (different conf, same area)
    print("\n  Key insight: Are people switching conferences rather than leaving entirely?")


def main():
    parser = argparse.ArgumentParser(description='Analyze AEC member retention')
    parser.add_argument('--conf_regex', default='.*20[12][0-9]',
                        help='Regex to filter conference-years')
    parser.add_argument('--output', default=None,
                        help='Output JSON file for retention data')
    args = parser.parse_args()

    all_results = scrape_all_committees(args.conf_regex)

    # Filter out tiny committees (likely just chairs)
    valid_results = {
        cy: members for cy, members in all_results.items()
        if len(members) >= MIN_COMMITTEE_SIZE
    }

    print(f"\nUsing {len(valid_results)} conference-years with ≥{MIN_COMMITTEE_SIZE} members")
    for cy in sorted(valid_results.keys()):
        conf, year = _extract_conf_year(cy)
        area = _conf_area(cy)
        print(f"  {cy}: {len(valid_results[cy])} members ({area})")

    analyze_retention(valid_results)

    if args.output:
        # Save the per-member conference_years mapping for further analysis
        member_map = build_member_map(valid_results)
        output_data = {}
        for norm, conf_years in sorted(member_map.items()):
            output_data[norm] = sorted([[c, y] for c, y in conf_years])
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nSaved member→conference_years mapping to {args.output}")


if __name__ == '__main__':
    main()
