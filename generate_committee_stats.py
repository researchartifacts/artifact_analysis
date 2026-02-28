#!/usr/bin/env python3
"""
Generate committee statistics for the researchartifacts website.

Scrapes AE committee member data from sysartifacts and secartifacts,
classifies members by country, continent, and institution, and outputs
structured YAML/JSON for Jekyll rendering + chart generation.
"""

import argparse
import json
import os
import re
import yaml
from collections import defaultdict
from datetime import datetime

from pytrie import Trie
from thefuzz import fuzz

from sys_sec_committee_scrape import get_committees
from sys_sec_scrape import download_file
from alternative_committee_scrape import (
    get_alternative_committees,
    get_all_usenix_committees,
    scrape_ches_committee,
    scrape_pets_committee,
    USENIX_CONF_SLUGS,
    USENIX_KNOWN_YEARS,
    CHES_KNOWN_YEARS,
    PETS_KNOWN_YEARS,
)

# ── Country → Continent mapping ──────────────────────────────────────────────

COUNTRY_TO_CONTINENT = {
    # Africa
    'Algeria': 'Africa', 'Angola': 'Africa', 'Benin': 'Africa',
    'Botswana': 'Africa', 'Burkina Faso': 'Africa', 'Cameroon': 'Africa',
    'Egypt': 'Africa', 'Ethiopia': 'Africa', 'Ghana': 'Africa',
    'Kenya': 'Africa', 'Morocco': 'Africa', 'Nigeria': 'Africa',
    'Rwanda': 'Africa', 'Senegal': 'Africa', 'South Africa': 'Africa',
    'Tanzania': 'Africa', 'Tunisia': 'Africa', 'Uganda': 'Africa',
    'Zimbabwe': 'Africa',
    # Asia
    'Bangladesh': 'Asia', 'China': 'Asia', 'Hong Kong': 'Asia',
    'India': 'Asia', 'Indonesia': 'Asia', 'Iran': 'Asia',
    'Iraq': 'Asia', 'Israel': 'Asia', 'Japan': 'Asia',
    'Jordan': 'Asia', 'Kazakhstan': 'Asia', 'Kuwait': 'Asia',
    'Lebanon': 'Asia', 'Macau': 'Asia', 'Malaysia': 'Asia',
    'Myanmar': 'Asia', 'Nepal': 'Asia', 'Oman': 'Asia',
    'Pakistan': 'Asia', 'Philippines': 'Asia', 'Qatar': 'Asia',
    'Saudi Arabia': 'Asia', 'Singapore': 'Asia', 'South Korea': 'Asia',
    'Sri Lanka': 'Asia', 'Syria': 'Asia', 'Taiwan': 'Asia',
    'Thailand': 'Asia', 'Turkey': 'Asia',
    'United Arab Emirates': 'Asia', 'Vietnam': 'Asia',
    'Taiwan, Province of China': 'Asia',
    # Europe
    'Albania': 'Europe', 'Austria': 'Europe', 'Belgium': 'Europe',
    'Bosnia and Herzegovina': 'Europe', 'Bulgaria': 'Europe',
    'Croatia': 'Europe', 'Cyprus': 'Europe', 'Czech Republic': 'Europe',
    'Czechia': 'Europe', 'Denmark': 'Europe', 'Estonia': 'Europe',
    'Finland': 'Europe', 'France': 'Europe', 'Germany': 'Europe',
    'Greece': 'Europe', 'Hungary': 'Europe', 'Iceland': 'Europe',
    'Ireland': 'Europe', 'Italy': 'Europe', 'Latvia': 'Europe',
    'Lithuania': 'Europe', 'Luxembourg': 'Europe', 'Malta': 'Europe',
    'Montenegro': 'Europe', 'Netherlands': 'Europe', 'North Macedonia': 'Europe',
    'Norway': 'Europe', 'Poland': 'Europe', 'Portugal': 'Europe',
    'Romania': 'Europe', 'Russia': 'Europe', 'Serbia': 'Europe',
    'Slovakia': 'Europe', 'Slovenia': 'Europe', 'Spain': 'Europe',
    'Sweden': 'Europe', 'Switzerland': 'Europe',
    'United Kingdom': 'Europe',
    # North America
    'Canada': 'North America', 'Costa Rica': 'North America',
    'Cuba': 'North America', 'Dominican Republic': 'North America',
    'Guatemala': 'North America', 'Haiti': 'North America',
    'Honduras': 'North America', 'Jamaica': 'North America',
    'Mexico': 'North America', 'Nicaragua': 'North America',
    'Panama': 'North America', 'Trinidad and Tobago': 'North America',
    'United States': 'North America',
    # South America
    'Argentina': 'South America', 'Bolivia': 'South America',
    'Brazil': 'South America', 'Chile': 'South America',
    'Colombia': 'South America', 'Ecuador': 'South America',
    'Paraguay': 'South America', 'Peru': 'South America',
    'Uruguay': 'South America', 'Venezuela': 'South America',
    # Oceania
    'Australia': 'Oceania', 'Fiji': 'Oceania',
    'New Zealand': 'Oceania', 'Papua New Guinea': 'Oceania',
}


def _extract_conf_year(conf_year_str):
    """Extract conference name and year from string like 'osdi2024'."""
    m = re.match(r'^([a-zA-Z]+)(\d{4})$', conf_year_str)
    if m:
        return m.group(1).upper(), int(m.group(2))
    return conf_year_str.upper(), None


def _build_university_index():
    """Download and build the university name → info index (with manual overrides)."""
    university_info = json.loads(download_file(
        "https://github.com/Hipo/university-domains-list/raw/refs/heads/master/"
        "world_universities_and_domains.json"
    ))
    # Manual overrides for institutions not in the database
    university_info.extend([
        {'name': 'télécom sudparis', 'country': 'France'},
        {'name': 'ku leuven', 'country': 'Belgium'},
        {'name': 'imec-distrinet, ku leuven', 'country': 'Belgium'},
        {'name': 'university of crete', 'country': 'Greece'},
        {'name': 'ucla', 'country': 'United States'},
        {'name': 'tu munich', 'country': 'Germany'},
        {'name': 'inesc-id & ist u. lisboa in Portugal', 'country': 'Portugal'},
        {'name': 'ist lisbon & inesc-id', 'country': 'Portugal'},
        {'name': 'mpi-sws', 'country': 'Germany'},
        {'name': 'hkust', 'country': 'Hong Kong'},
        {'name': 'uc irvine', 'country': 'United States'},
        {'name': 'uiuc', 'country': 'United States'},
        {'name': 'school of computer science, university college dublin', 'country': 'Ireland'},
        {'name': 'imdea software institute', 'country': 'Spain'},
        {'name': 'university of chinese academy of sciences', 'country': 'China'},
        {'name': 'zhengqing', 'country': 'China'},
        {'name': 'the university of utah', 'country': 'United States'},
        {'name': 'institute of parallel and distributed systems, shanghai jiao tong university', 'country': 'China'},
        {'name': 'computing and imaging institute - the university of utah', 'country': 'United States'},
        {'name': 'university of crete & ics-forth', 'country': 'Greece'},
        {'name': 'ics-forth', 'country': 'Greece'},
        {'name': 'kaust', 'country': 'Saudi Arabia'},
        {'name': 'lrz', 'country': 'Germany'},
        {'name': 'ensta bretagne', 'country': 'France'},
        {'name': 'institute of computing technology chinese academy of sciences', 'country': 'China'},
        {'name': 'imdea networks institute & uc3m', 'country': 'Spain'},
        {'name': 'hasso plattner institute', 'country': 'Germany'},
        {'name': 'unist', 'country': 'South Korea'},
        {'name': 'niccolò cusano university', 'country': 'Italy'},
        {'name': 'uc irvine & mpi-sp', 'country': 'United States'},
        {'name': 'univ. toulouse iii, irit', 'country': 'France'},
        {'name': 'university of telepegaso,rome,italy', 'country': 'Italy'},
        {'name': 'leibniz supercomputing center', 'country': 'Germany'},
        {'name': 'inesc tec & u. minho', 'country': 'Portugal'},
        {'name': 'barkhausen institut', 'country': 'Germany'},
        {'name': 'the ohio state university', 'country': 'United States'},
        # Additional overrides for common unmatched institutions
        {'name': 'cispa helmholtz center for information security', 'country': 'Germany'},
        {'name': 'cispa', 'country': 'Germany'},
        {'name': 'cuhk', 'country': 'Hong Kong'},
        {'name': 'cuhk-shenzhen', 'country': 'China'},
        {'name': 'kaist', 'country': 'South Korea'},
        {'name': 'epfl', 'country': 'Switzerland'},
        {'name': 'eth zurich', 'country': 'Switzerland'},
        {'name': 'ethz', 'country': 'Switzerland'},
        {'name': 'google', 'country': 'United States'},
        {'name': 'microsoft research', 'country': 'United States'},
        {'name': 'microsoft', 'country': 'United States'},
        {'name': 'meta', 'country': 'United States'},
        {'name': 'amazon', 'country': 'United States'},
        {'name': 'ibm research', 'country': 'United States'},
        {'name': 'intel labs', 'country': 'United States'},
        {'name': 'vmware research', 'country': 'United States'},
        {'name': 'bytedance', 'country': 'China'},
        {'name': 'tencent', 'country': 'China'},
        {'name': 'alibaba', 'country': 'China'},
        {'name': 'huawei', 'country': 'China'},
        {'name': 'inesc-id and instituto superior técnico', 'country': 'Portugal'},
        {'name': 'inesc-id', 'country': 'Portugal'},
        {'name': 'max planck institute for informatics', 'country': 'Germany'},
        {'name': 'max planck institute for software systems', 'country': 'Germany'},
        {'name': 'mpi-sp', 'country': 'Germany'},
        {'name': 'mpi-inf', 'country': 'Germany'},
        {'name': 'institute of software', 'country': 'China'},
        {'name': 'institute of software, chinese academy of sciences', 'country': 'China'},
        {'name': 'snu', 'country': 'South Korea'},
        {'name': 'postech', 'country': 'South Korea'},
        {'name': 'ntu', 'country': 'Singapore'},
        {'name': 'nus', 'country': 'Singapore'},
        {'name': 'sutd', 'country': 'Singapore'},
        {'name': 'tu delft', 'country': 'Netherlands'},
        {'name': 'tu darmstadt', 'country': 'Germany'},
        {'name': 'tu berlin', 'country': 'Germany'},
        {'name': 'tu wien', 'country': 'Austria'},
        {'name': 'rwth aachen', 'country': 'Germany'},
        {'name': 'rwth aachen university', 'country': 'Germany'},
        {'name': 'inria', 'country': 'France'},
        {'name': 'cea', 'country': 'France'},
        {'name': 'cnrs', 'country': 'France'},
        {'name': 'vrije universiteit amsterdam', 'country': 'Netherlands'},
        {'name': 'vu amsterdam', 'country': 'Netherlands'},
        {'name': 'sapienza university of rome', 'country': 'Italy'},
        {'name': 'politecnico di milano', 'country': 'Italy'},
        {'name': 'iisc', 'country': 'India'},
        {'name': 'iit bombay', 'country': 'India'},
        {'name': 'iit delhi', 'country': 'India'},
        {'name': 'iit kanpur', 'country': 'India'},
        {'name': 'iit madras', 'country': 'India'},
        {'name': 'ucl', 'country': 'United Kingdom'},
        {'name': 'imperial college london', 'country': 'United Kingdom'},
        # Industry & government labs
        {'name': 'akamai technologies', 'country': 'United States'},
        {'name': 'sandia national laboratories', 'country': 'United States'},
        {'name': 'lawrence berkeley national laboratory', 'country': 'United States'},
        {'name': 'pnnl', 'country': 'United States'},
        {'name': 'pacific northwest national laboratory', 'country': 'United States'},
        {'name': 'hewlett packard enterprise', 'country': 'United States'},
        {'name': 'hewlett packard enterprise labs', 'country': 'United States'},
        {'name': 'netflix', 'country': 'United States'},
        {'name': 'linkedin', 'country': 'United States'},
        {'name': 'blackberry', 'country': 'Canada'},
        {'name': 'accenture labs', 'country': 'United States'},
        {'name': 'mit csail', 'country': 'United States'},
        {'name': 'baidu security', 'country': 'China'},
        {'name': 'huawei technologies co.', 'country': 'China'},
        {'name': 'orange labs', 'country': 'France'},
        {'name': 'telefonica research', 'country': 'Spain'},
        {'name': "csiro's data61", 'country': 'Australia'},
        {'name': 'csiro data61', 'country': 'Australia'},
    ])

    name_index = {}
    for uni in university_info:
        name_index[uni['name'].lower()] = uni
        splitted = uni['name'].split(" ")
        if len(splitted) > 1:
            for part in splitted:
                name_index[part.lower()] = uni
            if len(splitted) > 2:
                for s_cnt in range(1, len(splitted) - 1):
                    name_index[" ".join(splitted[s_cnt:]).lower()] = uni

    return name_index


def _clean_affiliation(aff):
    """Strip HTML tags, markdown formatting, and whitespace from affiliation."""
    import re as _re
    aff = _re.sub(r'<[^>]+>', '', aff)        # remove HTML tags like <br>
    aff = aff.strip('_* \t\n\r')              # remove markdown bold/italic markers
    aff = _re.sub(r'\s+', ' ', aff).strip()   # collapse whitespace
    return aff


def classify_member(affiliation, prefix_tree, name_index):
    """Classify a single member's affiliation to a country.

    Returns (country, institution_name) or (None, None) on failure.
    """
    aff_lower = affiliation.lower().strip()
    if not aff_lower:
        return None, None

    # Try prefix-tree match first
    matches = prefix_tree.values(prefix=aff_lower)
    if matches:
        uni = matches[0]
        return uni['country'], uni.get('name', affiliation)

    # Fall back to fuzzy matching
    best_match = None
    best_ratio = 0
    for name, uni in name_index.items():
        ratio = fuzz.ratio(name, aff_lower)
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = uni

    if best_ratio > 80 and best_match:
        return best_match['country'], best_match.get('name', affiliation)

    return None, None


def classify_committees(all_results):
    """Classify all committee members by country, continent, and institution.

    Parameters
    ----------
    all_results : dict
        {conf_year: [{name, affiliation}, ...]}

    Returns
    -------
    dict with keys: by_country, by_continent, by_institution, by_conference,
                    failed_affiliations
    """
    name_index = _build_university_index()
    prefix_tree = Trie(**name_index)

    # Per-conference-year breakdown
    by_conf_country = {}   # conf_year → {country: count}
    by_conf_continent = {} # conf_year → {continent: count}
    by_conf_institution = {}  # conf_year → {institution: count}
    failed = []

    for conf_year, members in all_results.items():
        by_conf_country[conf_year] = defaultdict(int)
        by_conf_continent[conf_year] = defaultdict(int)
        by_conf_institution[conf_year] = defaultdict(int)

        for member in members:
            affiliation = _clean_affiliation(member['affiliation'])
            country, inst_name = classify_member(
                affiliation, prefix_tree, name_index
            )
            if country:
                by_conf_country[conf_year][country] += 1
                continent = COUNTRY_TO_CONTINENT.get(country, 'Unknown')
                by_conf_continent[conf_year][continent] += 1
                by_conf_institution[conf_year][inst_name or member['affiliation']] += 1
            else:
                failed.append({
                    'conference': conf_year,
                    'name': member['name'],
                    'affiliation': affiliation,
                })

    return {
        'by_country': by_conf_country,
        'by_continent': by_conf_continent,
        'by_institution': by_conf_institution,
        'failed': failed,
    }


def _aggregate_across_conferences(per_conf, conf_to_area):
    """Aggregate per-conference-year dicts into overall + per-area totals.

    Parameters
    ----------
    per_conf : dict
        {conf_year: {key: count}}
    conf_to_area : dict
        {conf_year: 'systems' | 'security'}

    Returns
    -------
    (overall, systems, security) — each is {key: total_count}
    """
    overall = defaultdict(int)
    systems = defaultdict(int)
    security = defaultdict(int)
    for conf_year, counts in per_conf.items():
        area = conf_to_area.get(conf_year, 'unknown')
        for key, count in counts.items():
            overall[key] += count
            if area == 'systems':
                systems[key] += count
            elif area == 'security':
                security[key] += count
    return dict(overall), dict(systems), dict(security)


def _build_yearly_series(per_conf, conf_to_area):
    """Build year-level time-series for charting.

    Returns dict: {year: {key: count}} aggregated across all conferences.
    Also returns per-area: (all_years, systems_years, security_years)
    """
    all_years = defaultdict(lambda: defaultdict(int))
    sys_years = defaultdict(lambda: defaultdict(int))
    sec_years = defaultdict(lambda: defaultdict(int))

    for conf_year, counts in per_conf.items():
        _, year = _extract_conf_year(conf_year)
        if year is None:
            continue
        area = conf_to_area.get(conf_year, 'unknown')
        for key, count in counts.items():
            all_years[year][key] += count
            if area == 'systems':
                sys_years[year][key] += count
            elif area == 'security':
                sec_years[year][key] += count

    return dict(all_years), dict(sys_years), dict(sec_years)


def _top_n(d, n=20):
    """Return top-N items from a dict sorted by value descending."""
    return sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]


# ── Conference → area mapping ────────────────────────────────────────────────

SYSTEMS_CONFS = {'atc', 'eurosys', 'fast', 'osdi', 'sc', 'sosp'}
SECURITY_CONFS = {'acsac', 'ches', 'ndss', 'pets', 'systex', 'usenixsec', 'woot'}


def _conf_area(conf_year):
    """Determine area (systems/security) from a conf_year string."""
    conf_name, _ = _extract_conf_year(conf_year)
    name_lower = conf_name.lower()
    if name_lower in SYSTEMS_CONFS:
        return 'systems'
    if name_lower in SECURITY_CONFS:
        return 'security'
    return 'unknown'


# Minimum committee size to consider data valid from sysartifacts/secartifacts.
# Committees with fewer members are likely placeholder or chair-only entries.
# PETS secartifacts has only 3 (chairs); real committees have 13-172 members.
MIN_COMMITTEE_SIZE = 5

# Known placeholder names to filter out
PLACEHOLDER_NAMES = {'you?', 'you', 'tba', 'tbd', 'n/a', '', 'title: organizers'}


def _normalize_name(name):
    """Normalize a person's name for matching across conferences.

    Strips whitespace, lowercases, removes accents via simple mapping,
    and collapses middle initials.
    """
    import unicodedata
    name = name.strip().lower()
    # Normalize unicode accented characters (e.g. é → e)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    # Remove period after initials
    name = re.sub(r'\.', '', name)
    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _compute_recurring_members(all_results, conf_to_area, classified):
    """Compute statistics for recurring AE committee members.

    For each unique person (matched by normalized name), track:
    - Total memberships across all conference-years
    - Number of times served as chair
    - Conferences and years served
    - Most recent affiliation
    - Area (systems/security/both)
    - Country (from classification)

    Parameters
    ----------
    all_results : dict
        {conf_year: [{name, affiliation, role?}, ...]}
    conf_to_area : dict
        {conf_year: 'systems'|'security'|'unknown'}
    classified : dict
        Classification data with by_country, by_institution per conf_year

    Returns
    -------
    (members_list, summary_dict)
        members_list: list of dicts sorted by total_memberships desc
        summary_dict: aggregated summary stats
    """
    # Map: normalized_name -> member record
    member_map = {}

    for conf_year, members in all_results.items():
        conf_name, year = _extract_conf_year(conf_year)
        area = conf_to_area.get(conf_year, 'unknown')

        for m in members:
            name_raw = m.get('name', '').strip()
            if not name_raw:
                continue
            norm = _normalize_name(name_raw)
            role = m.get('role', 'member')
            affiliation = m.get('affiliation', '').strip('*_ \t')

            if norm not in member_map:
                member_map[norm] = {
                    'name': name_raw,
                    'affiliation': affiliation,
                    'total_memberships': 0,
                    'chair_count': 0,
                    'conferences': set(),
                    'conference_years': [],
                    'years': set(),
                    'years_count': {},  # year -> count
                    'areas': set(),
                    'roles_by_conf': {},  # conf_year -> role
                    # Per-area tracking
                    'sys_memberships': 0,
                    'sys_chair_count': 0,
                    'sys_conferences': set(),
                    'sys_years': set(),
                    'sys_years_count': {},
                    'sec_memberships': 0,
                    'sec_chair_count': 0,
                    'sec_conferences': set(),
                    'sec_years': set(),
                    'sec_years_count': {},
                }

            rec = member_map[norm]
            rec['total_memberships'] += 1
            if role == 'chair':
                rec['chair_count'] += 1
            rec['conferences'].add(conf_name)
            rec['conference_years'].append(conf_year)
            if year:
                rec['years'].add(year)
                rec['years_count'][year] = rec['years_count'].get(year, 0) + 1
            if area in ('systems', 'security'):
                rec['areas'].add(area)
            rec['roles_by_conf'][conf_year] = role
            # Keep most recent affiliation (higher year = more recent)
            if affiliation and (not rec['affiliation'] or (year and max(rec['years']) == year)):
                rec['affiliation'] = affiliation
                rec['name'] = name_raw  # prefer most recent spelling

            # Per-area accumulation
            if area == 'systems':
                rec['sys_memberships'] += 1
                if role == 'chair':
                    rec['sys_chair_count'] += 1
                rec['sys_conferences'].add(conf_name)
                if year:
                    rec['sys_years'].add(year)
                    rec['sys_years_count'][year] = rec['sys_years_count'].get(year, 0) + 1
            elif area == 'security':
                rec['sec_memberships'] += 1
                if role == 'chair':
                    rec['sec_chair_count'] += 1
                rec['sec_conferences'].add(conf_name)
                if year:
                    rec['sec_years'].add(year)
                    rec['sec_years_count'][year] = rec['sec_years_count'].get(year, 0) + 1

    # Filter: at least 2 memberships, but always keep chairs
    recurring = [rec for rec in member_map.values() if rec['total_memberships'] >= 2 or rec['chair_count'] > 0]

    # Classify area
    for rec in recurring:
        if 'systems' in rec['areas'] and 'security' in rec['areas']:
            rec['area'] = 'both'
        elif 'systems' in rec['areas']:
            rec['area'] = 'systems'
        elif 'security' in rec['areas']:
            rec['area'] = 'security'
        else:
            rec['area'] = 'unknown'

    # Build output list (JSON-serializable) — combined (all areas)
    members_list = []
    for rec in recurring:
        entry = {
            'name': rec['name'],
            'affiliation': rec['affiliation'],
            'total_memberships': rec['total_memberships'],
            'chair_count': rec['chair_count'],
            'conferences': sorted(list(rec['conferences'])),
            'area': rec['area'],
            'years': {y: rec['years_count'][y] for y in sorted(rec['years'])},
            'first_year': min(rec['years']) if rec['years'] else None,
            'last_year': max(rec['years']) if rec['years'] else None,
        }
        members_list.append(entry)

    # Sort by total_memberships desc, then chair_count desc, then name
    members_list.sort(key=lambda x: (-x['total_memberships'], -x['chair_count'], x['name']))

    # Build area-specific lists with area-only counts
    systems_members = []
    for rec in recurring:
        if rec['sys_memberships'] < 2 and rec['sys_chair_count'] == 0:
            continue  # not enough systems participation
        entry = {
            'name': rec['name'],
            'affiliation': rec['affiliation'],
            'total_memberships': rec['sys_memberships'],
            'chair_count': rec['sys_chair_count'],
            'conferences': sorted(list(rec['sys_conferences'])),
            'area': rec['area'],
            'years': {y: rec['sys_years_count'][y] for y in sorted(rec['sys_years'])},
            'first_year': min(rec['sys_years']) if rec['sys_years'] else None,
            'last_year': max(rec['sys_years']) if rec['sys_years'] else None,
        }
        systems_members.append(entry)
    systems_members.sort(key=lambda x: (-x['total_memberships'], -x['chair_count'], x['name']))

    security_members = []
    for rec in recurring:
        if rec['sec_memberships'] < 2 and rec['sec_chair_count'] == 0:
            continue  # not enough security participation
        entry = {
            'name': rec['name'],
            'affiliation': rec['affiliation'],
            'total_memberships': rec['sec_memberships'],
            'chair_count': rec['sec_chair_count'],
            'conferences': sorted(list(rec['sec_conferences'])),
            'area': rec['area'],
            'years': {y: rec['sec_years_count'][y] for y in sorted(rec['sec_years'])},
            'first_year': min(rec['sec_years']) if rec['sec_years'] else None,
            'last_year': max(rec['sec_years']) if rec['sec_years'] else None,
        }
        security_members.append(entry)
    security_members.sort(key=lambda x: (-x['total_memberships'], -x['chair_count'], x['name']))

    summary = {
        'total_recurring': len(members_list),
        'total_recurring_systems': len(systems_members),
        'total_recurring_security': len(security_members),
        'total_chairs': sum(1 for m in members_list if m['chair_count'] > 0),
        'max_memberships': max((m['total_memberships'] for m in members_list), default=0),
    }

    return members_list, systems_members, security_members, summary


def _compute_institution_timeline(classified, conf_to_area):
    """Compute institution participation over years.

    Returns
    ----------
    institution_by_year : dict
        {year: {institution: count}} for all areas
    institution_by_year_systems : dict
    institution_by_year_security : dict
    top_institutions_by_year : list
        [{year, institutions: [{name, count}]}] for chart data
    """
    inst_years_all = defaultdict(lambda: defaultdict(int))
    inst_years_sys = defaultdict(lambda: defaultdict(int))
    inst_years_sec = defaultdict(lambda: defaultdict(int))

    for conf_year, inst_counts in classified['by_institution'].items():
        _, year = _extract_conf_year(conf_year)
        if year is None:
            continue
        area = conf_to_area.get(conf_year, 'unknown')
        for inst, count in inst_counts.items():
            inst_years_all[year][inst] += count
            if area == 'systems':
                inst_years_sys[year][inst] += count
            elif area == 'security':
                inst_years_sec[year][inst] += count

    # Build top-N per year for charting
    top_by_year = []
    for year in sorted(inst_years_all.keys()):
        top = sorted(inst_years_all[year].items(), key=lambda x: -x[1])[:15]
        top_by_year.append({
            'year': year,
            'institutions': [{'name': k, 'count': v} for k, v in top]
        })

    # Unique institutions per year
    unique_by_year = []
    for year in sorted(inst_years_all.keys()):
        unique_by_year.append({
            'year': year,
            'total': len(inst_years_all[year]),
            'systems': len(inst_years_sys.get(year, {})),
            'security': len(inst_years_sec.get(year, {})),
        })

    return {
        'all': {str(y): dict(c) for y, c in sorted(inst_years_all.items())},
        'systems': {str(y): dict(c) for y, c in sorted(inst_years_sys.items())},
        'security': {str(y): dict(c) for y, c in sorted(inst_years_sec.items())},
        'top_by_year': top_by_year,
        'unique_by_year': unique_by_year,
    }



def _is_valid_committee(members):
    """Check if committee data looks valid (not placeholder, has enough members)."""
    if not members:
        return False
    # Filter out known placeholder entries
    real_members = [
        m for m in members
        if m.get('name', '').strip().lower() not in PLACEHOLDER_NAMES
        and len(m.get('name', '').strip()) > 1
    ]
    return len(real_members) >= MIN_COMMITTEE_SIZE


def _clean_committee(members):
    """Remove placeholder members and clean up names."""
    cleaned = []
    for m in members:
        name = m.get('name', '').strip()
        # Strip markdown link syntax [name](url)
        link_match = re.match(r'\[([^\]]+)\]\([^)]*\)', name)
        if link_match:
            name = link_match.group(1)
        # Strip trailing <br> tags
        name = re.sub(r'<br\s*/?>$', '', name).strip()
        # Skip placeholders
        if name.lower() in PLACEHOLDER_NAMES or len(name) <= 1:
            continue
        # Skip lines that look like contact info rather than people
        if 'contact' in name.lower() or 'reach' in name.lower() or 'mailto:' in name.lower():
            continue
        affiliation = m.get('affiliation', '').strip()
        affiliation = re.sub(r'<br\s*/?>$', '', affiliation).strip()
        affiliation = affiliation.strip('*_').strip()  # remove markdown bold/italic markers
        entry = {'name': name, 'affiliation': affiliation}
        if 'role' in m:
            entry['role'] = m['role']
        cleaned.append(entry)
    return cleaned


def generate_committee_data(conf_regex, output_dir):
    """Main entry point: scrape committees, classify, and write output files."""

    # ── 1. Scrape committees from both prefixes ──────────────────────────────
    print("  Scraping systems committee data from sysartifacts...")
    sys_results = get_committees(conf_regex, 'sys')
    print(f"    Found {len(sys_results)} systems conference-years")

    print("  Scraping security committee data from secartifacts...")
    sec_results = get_committees(conf_regex, 'sec')
    print(f"    Found {len(sec_results)} security conference-years")

    all_results = {}
    all_results.update(sys_results)
    all_results.update(sec_results)

    # Clean all results (remove placeholders, fix markdown links)
    for cy in list(all_results.keys()):
        all_results[cy] = _clean_committee(all_results[cy])

    # ── 1b. Supplement with alternative sources ──────────────────────────────
    #  Identify conferences that are missing or have low-quality data
    print("  Checking for conferences needing alternative sources...")
    conferences_needed = {}

    # Determine which conference-years we expect based on USENIX/CHES/PETS
    for conf, slug in USENIX_CONF_SLUGS.items():
        for year in USENIX_KNOWN_YEARS.get(conf, []):
            cy = f"{conf}{year}"
            if re.search(conf_regex, cy):
                area = 'systems' if conf in SYSTEMS_CONFS else 'security'
                if cy not in all_results or not _is_valid_committee(all_results.get(cy)):
                    conferences_needed[cy] = area

    for year in CHES_KNOWN_YEARS:
        cy = f"ches{year}"
        if re.search(conf_regex, cy):
            if cy not in all_results or not _is_valid_committee(all_results.get(cy)):
                conferences_needed[cy] = 'security'

    for year in PETS_KNOWN_YEARS:
        cy = f"pets{year}"
        if re.search(conf_regex, cy):
            if cy not in all_results or not _is_valid_committee(all_results.get(cy)):
                conferences_needed[cy] = 'security'

    if conferences_needed:
        print(f"    Need alternative sources for {len(conferences_needed)} conference-years:")
        for cy in sorted(conferences_needed.keys()):
            existing = len(all_results.get(cy, []))
            print(f"      {cy} (currently {existing} members)")

        alt_results = get_alternative_committees(conferences_needed)
        for cy, members in alt_results.items():
            cleaned = _clean_committee(members)
            if cleaned:
                existing_count = len(all_results.get(cy, []))
                all_results[cy] = cleaned
                print(f"    ✓ {cy}: replaced {existing_count} → {len(cleaned)} members (alternative source)")
    else:
        print("    All conference-years have valid committee data.")

    if not all_results:
        print("  No committee data found — skipping committee stats.")
        return None

    # ── 2. Classify by country / continent / institution ─────────────────────
    print("  Classifying committee members...")
    classified = classify_committees(all_results)

    if classified['failed']:
        print(f"  ⚠️  Could not classify {len(classified['failed'])} members")

    # Build area map
    conf_to_area = {cy: _conf_area(cy) for cy in all_results}

    # ── 3. Aggregate statistics ──────────────────────────────────────────────
    country_all, country_sys, country_sec = _aggregate_across_conferences(
        classified['by_country'], conf_to_area
    )
    continent_all, continent_sys, continent_sec = _aggregate_across_conferences(
        classified['by_continent'], conf_to_area
    )
    inst_all, inst_sys, inst_sec = _aggregate_across_conferences(
        classified['by_institution'], conf_to_area
    )

    # Yearly time-series
    country_years_all, country_years_sys, country_years_sec = _build_yearly_series(
        classified['by_country'], conf_to_area
    )
    continent_years_all, continent_years_sys, continent_years_sec = _build_yearly_series(
        classified['by_continent'], conf_to_area
    )

    # Committee sizes per conference-year
    committee_sizes = []
    for conf_year in sorted(all_results.keys()):
        conf_name, year = _extract_conf_year(conf_year)
        area = conf_to_area.get(conf_year, 'unknown')
        committee_sizes.append({
            'conference': conf_name,
            'year': year,
            'conf_year': conf_year,
            'area': area,
            'size': len(all_results[conf_year]),
        })

    # Total members
    total_members = sum(len(m) for m in all_results.values())
    total_systems = sum(len(m) for cy, m in all_results.items()
                        if conf_to_area.get(cy) == 'systems')
    total_security = sum(len(m) for cy, m in all_results.items()
                         if conf_to_area.get(cy) == 'security')

    # ── 3b. Compute recurring AE member statistics ───────────────────────────
    print("  Computing recurring AE member rankings...")
    all_members, sys_members, sec_members, recurring_summary = \
        _compute_recurring_members(all_results, conf_to_area, classified)
    print(f"    Found {recurring_summary['total_recurring']} recurring members "
          f"({recurring_summary['total_chairs']} include chair roles)")

    # ── 3c. Compute institution timeline ─────────────────────────────────────
    print("  Computing institution timeline...")
    inst_timeline = _compute_institution_timeline(classified, conf_to_area)
    print(f"    Tracked {len(inst_timeline['unique_by_year'])} years of institution data")

    # ── 4. Build output structures ───────────────────────────────────────────

    # Summary for _data/committee_stats.yml
    committee_summary = {
        'last_updated': datetime.now().strftime('%Y-%m-%d'),
        'total_members': total_members,
        'total_systems': total_systems,
        'total_security': total_security,
        'total_conferences': len(all_results),
        'total_countries': len(country_all),
        'total_continents': len(continent_all),
        'total_institutions': len(inst_all),
        'recurring_members': recurring_summary['total_recurring'],
        'recurring_members_systems': recurring_summary['total_recurring_systems'],
        'recurring_members_security': recurring_summary['total_recurring_security'],
        'recurring_chairs': recurring_summary['total_chairs'],
        'top_countries': [{'name': k, 'count': v} for k, v in _top_n(country_all, 15)],
        'top_countries_systems': [{'name': k, 'count': v} for k, v in _top_n(country_sys, 15)],
        'top_countries_security': [{'name': k, 'count': v} for k, v in _top_n(country_sec, 15)],
        'top_continents': [{'name': k, 'count': v} for k, v in _top_n(continent_all, 10)],
        'top_continents_systems': [{'name': k, 'count': v} for k, v in _top_n(continent_sys, 10)],
        'top_continents_security': [{'name': k, 'count': v} for k, v in _top_n(continent_sec, 10)],
        'top_institutions': [{'name': k, 'count': v} for k, v in _top_n(inst_all, 20)],
        'top_institutions_systems': [{'name': k, 'count': v} for k, v in _top_n(inst_sys, 20)],
        'top_institutions_security': [{'name': k, 'count': v} for k, v in _top_n(inst_sec, 20)],
        'institution_timeline': inst_timeline['unique_by_year'],
        'committee_sizes': committee_sizes,
    }

    # Detailed JSON for charting / download
    detail_json = {
        'summary': {
            'total_members': total_members,
            'total_systems': total_systems,
            'total_security': total_security,
            'total_countries': len(country_all),
            'total_continents': len(continent_all),
            'total_institutions': len(inst_all),
        },
        'by_country': {
            'overall': [{'name': k, 'count': v}
                        for k, v in sorted(country_all.items(), key=lambda x: -x[1])],
            'systems': [{'name': k, 'count': v}
                        for k, v in sorted(country_sys.items(), key=lambda x: -x[1])],
            'security': [{'name': k, 'count': v}
                         for k, v in sorted(country_sec.items(), key=lambda x: -x[1])],
        },
        'by_continent': {
            'overall': [{'name': k, 'count': v}
                        for k, v in sorted(continent_all.items(), key=lambda x: -x[1])],
            'systems': [{'name': k, 'count': v}
                        for k, v in sorted(continent_sys.items(), key=lambda x: -x[1])],
            'security': [{'name': k, 'count': v}
                         for k, v in sorted(continent_sec.items(), key=lambda x: -x[1])],
        },
        'by_institution': {
            'overall': [{'name': k, 'count': v}
                        for k, v in sorted(inst_all.items(), key=lambda x: -x[1])],
            'systems': [{'name': k, 'count': v}
                        for k, v in sorted(inst_sys.items(), key=lambda x: -x[1])],
            'security': [{'name': k, 'count': v}
                         for k, v in sorted(inst_sec.items(), key=lambda x: -x[1])],
        },
        'by_year': {
            'country': {str(y): dict(c) for y, c in sorted(country_years_all.items())},
            'country_systems': {str(y): dict(c) for y, c in sorted(country_years_sys.items())},
            'country_security': {str(y): dict(c) for y, c in sorted(country_years_sec.items())},
            'continent': {str(y): dict(c) for y, c in sorted(continent_years_all.items())},
            'continent_systems': {str(y): dict(c) for y, c in sorted(continent_years_sys.items())},
            'continent_security': {str(y): dict(c) for y, c in sorted(continent_years_sec.items())},
        },
        'committee_sizes': committee_sizes,
        'failed_classifications': classified['failed'],
    }

    # ── 5. Write output files ────────────────────────────────────────────────
    if output_dir:
        os.makedirs(os.path.join(output_dir, '_data'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'assets/data'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'assets/charts'), exist_ok=True)

        yml_path = os.path.join(output_dir, '_data/committee_stats.yml')
        with open(yml_path, 'w') as f:
            yaml.dump(committee_summary, f, default_flow_style=False,
                      allow_unicode=True, sort_keys=False)
        print(f"  Wrote {yml_path}")

        json_path = os.path.join(output_dir, 'assets/data/committee_stats.json')
        with open(json_path, 'w') as f:
            json.dump(detail_json, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {json_path}")

        # Write recurring AE member JSON files
        ae_all_path = os.path.join(output_dir, 'assets/data/ae_members.json')
        with open(ae_all_path, 'w') as f:
            json.dump(all_members, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {ae_all_path} ({len(all_members)} members)")

        ae_sys_path = os.path.join(output_dir, 'assets/data/systems_ae_members.json')
        with open(ae_sys_path, 'w') as f:
            json.dump(sys_members, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {ae_sys_path} ({len(sys_members)} members)")

        ae_sec_path = os.path.join(output_dir, 'assets/data/security_ae_members.json')
        with open(ae_sec_path, 'w') as f:
            json.dump(sec_members, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {ae_sec_path} ({len(sec_members)} members)")

        # Write institution timeline JSON
        inst_timeline_path = os.path.join(output_dir, 'assets/data/institution_timeline.json')
        with open(inst_timeline_path, 'w') as f:
            json.dump(inst_timeline, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {inst_timeline_path}")

    # ── 6. Generate charts ───────────────────────────────────────────────────
    if output_dir:
        _generate_committee_charts(committee_summary, detail_json, output_dir,
                                   inst_timeline=inst_timeline)

    print(f"  Committee stats: {total_members} members from "
          f"{len(country_all)} countries, {len(continent_all)} continents, "
          f"{len(inst_all)} institutions")
    print(f"  Recurring members: {recurring_summary['total_recurring']} "
          f"(sys: {recurring_summary['total_recurring_systems']}, "
          f"sec: {recurring_summary['total_recurring_security']}, "
          f"chairs: {recurring_summary['total_chairs']})")

    return detail_json


# ── Chart generation ─────────────────────────────────────────────────────────

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def _generate_committee_charts(summary, detail, output_dir, inst_timeline=None):
    """Generate SVG charts for committee statistics."""
    charts_dir = os.path.join(output_dir, 'assets/charts')
    os.makedirs(charts_dir, exist_ok=True)

    _chart_top_countries(detail, os.path.join(charts_dir, 'committee_countries.svg'))
    _chart_top_countries(detail, os.path.join(charts_dir, 'committee_countries_systems.svg'),
                         area='systems')
    _chart_top_countries(detail, os.path.join(charts_dir, 'committee_countries_security.svg'),
                         area='security')
    _chart_continents(detail, os.path.join(charts_dir, 'committee_continents.svg'))
    _chart_continents(detail, os.path.join(charts_dir, 'committee_continents_systems.svg'),
                      area='systems')
    _chart_continents(detail, os.path.join(charts_dir, 'committee_continents_security.svg'),
                      area='security')
    _chart_top_institutions(detail, os.path.join(charts_dir, 'committee_institutions.svg'))
    _chart_top_institutions(detail, os.path.join(charts_dir, 'committee_institutions_systems.svg'),
                            area='systems')
    _chart_top_institutions(detail, os.path.join(charts_dir, 'committee_institutions_security.svg'),
                            area='security')
    _chart_committee_sizes(summary, os.path.join(charts_dir, 'committee_sizes.svg'))
    _chart_continent_timeline(detail, os.path.join(charts_dir, 'committee_continent_timeline.svg'))

    # New: institution timeline chart
    if inst_timeline:
        _chart_institution_timeline(inst_timeline, os.path.join(charts_dir, 'institution_timeline.svg'))
        _chart_top_institutions_over_time(inst_timeline, os.path.join(charts_dir, 'institution_top_timeline.svg'))

    print(f"  Committee charts generated in {charts_dir}")


def _chart_top_countries(detail, path, area=None, top_n=15):
    """Horizontal bar chart of top countries."""
    if area:
        data = detail['by_country'].get(area, [])
        title = f'Top Countries — {"Systems" if area == "systems" else "Security"}'
    else:
        data = detail['by_country']['overall']
        title = 'Top Countries — All AE Committees'

    data = data[:top_n]
    if not data:
        return

    names = [d['name'] for d in reversed(data)]
    counts = [d['count'] for d in reversed(data)]

    fig, ax = plt.subplots(figsize=(8, max(4, len(names) * 0.4)))
    colors = plt.cm.viridis(np.linspace(0.3, 0.9, len(names)))
    ax.barh(names, counts, color=colors)
    ax.set_xlabel('Committee Members')
    ax.set_title(title, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    for i, v in enumerate(counts):
        ax.text(v + max(counts) * 0.01, i, str(v), va='center', fontsize=8)
    fig.tight_layout()
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)


def _chart_continents(detail, path, area=None):
    """Pie chart of continent distribution."""
    if area:
        data = detail['by_continent'].get(area, [])
        title = f'AE Members by Continent — {"Systems" if area == "systems" else "Security"}'
    else:
        data = detail['by_continent']['overall']
        title = 'AE Members by Continent'

    if not data:
        return

    names = [d['name'] for d in data]
    counts = [d['count'] for d in data]

    continent_colors = {
        'Europe': '#4363D8',
        'North America': '#E6194B',
        'Asia': '#3CB44B',
        'South America': '#F58231',
        'Oceania': '#42D4F4',
        'Africa': '#F032E6',
        'Unknown': '#AAAAAA',
    }
    colors = [continent_colors.get(n, '#999999') for n in names]

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        counts, labels=names, colors=colors, autopct='%1.1f%%',
        startangle=140, pctdistance=0.85
    )
    for t in autotexts:
        t.set_fontsize(8)
    ax.set_title(title, fontweight='bold')
    fig.tight_layout()
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)


def _chart_top_institutions(detail, path, area=None, top_n=20):
    """Horizontal bar chart of top institutions."""
    if area:
        data = detail['by_institution'].get(area, [])
        title = f'Top Institutions — {"Systems" if area == "systems" else "Security"}'
    else:
        data = detail['by_institution']['overall']
        title = 'Top Institutions — All AE Committees'

    data = data[:top_n]
    if not data:
        return

    names = [d['name'][:40] for d in reversed(data)]  # truncate long names
    counts = [d['count'] for d in reversed(data)]

    fig, ax = plt.subplots(figsize=(10, max(5, len(names) * 0.35)))
    colors = plt.cm.plasma(np.linspace(0.2, 0.8, len(names)))
    ax.barh(names, counts, color=colors)
    ax.set_xlabel('Committee Members')
    ax.set_title(title, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    for i, v in enumerate(counts):
        ax.text(v + max(counts) * 0.01, i, str(v), va='center', fontsize=8)
    fig.tight_layout()
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)


def _chart_committee_sizes(summary, path):
    """Line chart of committee sizes over time, split by area."""
    sizes = summary.get('committee_sizes', [])
    if not sizes:
        return

    # Group by area and year
    sys_by_year = defaultdict(int)
    sec_by_year = defaultdict(int)
    for s in sizes:
        if s['year'] is None:
            continue
        if s['area'] == 'systems':
            sys_by_year[s['year']] += s['size']
        elif s['area'] == 'security':
            sec_by_year[s['year']] += s['size']

    all_y = sorted(set(sys_by_year.keys()) | set(sec_by_year.keys()))
    sys_vals = [sys_by_year.get(y, 0) for y in all_y]
    sec_vals = [sec_by_year.get(y, 0) for y in all_y]
    tot_vals = [s + c for s, c in zip(sys_vals, sec_vals)]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(all_y, tot_vals, marker='o', label='Total', color='#333', linewidth=2.5)
    ax.plot(all_y, sys_vals, marker='s', label='Systems', color='#2E86AB', linewidth=2)
    ax.plot(all_y, sec_vals, marker='^', label='Security', color='#A23B72', linewidth=2)
    ax.set_xlabel('Year')
    ax.set_ylabel('Committee Members')
    ax.set_title('AE Committee Sizes Over Time', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xticks(all_y)
    fig.tight_layout()
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)


def _chart_continent_timeline(detail, path):
    """Stacked area chart of continent distribution over time."""
    year_data = detail.get('by_year', {}).get('continent', {})
    if not year_data:
        return

    years = sorted(year_data.keys())
    all_continents = set()
    for yd in year_data.values():
        all_continents.update(yd.keys())

    continent_order = ['North America', 'Europe', 'Asia', 'South America',
                       'Oceania', 'Africa', 'Unknown']
    continents = [c for c in continent_order if c in all_continents]
    continents += sorted(all_continents - set(continent_order))

    continent_colors = {
        'Europe': '#4363D8', 'North America': '#E6194B', 'Asia': '#3CB44B',
        'South America': '#F58231', 'Oceania': '#42D4F4', 'Africa': '#F032E6',
        'Unknown': '#AAAAAA',
    }

    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = np.zeros(len(years))
    for continent in continents:
        vals = np.array([year_data.get(y, {}).get(continent, 0) for y in years],
                        dtype=float)
        color = continent_colors.get(continent, '#999999')
        ax.bar(years, vals, bottom=bottom, label=continent, color=color, width=0.7)
        bottom += vals

    ax.set_xlabel('Year')
    ax.set_ylabel('Committee Members')
    ax.set_title('AE Committee Members by Continent Over Time', fontweight='bold')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)


def _chart_institution_timeline(inst_timeline, path):
    """Line chart showing unique institutions participating over years."""
    data = inst_timeline.get('unique_by_year', [])
    if not data:
        return

    years = [d['year'] for d in data]
    totals = [d['total'] for d in data]
    sys_vals = [d['systems'] for d in data]
    sec_vals = [d['security'] for d in data]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(years, totals, marker='o', label='Total', color='#333', linewidth=2.5)
    ax.plot(years, sys_vals, marker='s', label='Systems', color='#2E86AB', linewidth=2)
    ax.plot(years, sec_vals, marker='^', label='Security', color='#A23B72', linewidth=2)
    ax.set_xlabel('Year')
    ax.set_ylabel('Unique Institutions')
    ax.set_title('Unique Institutions on AE Committees Over Time', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xticks(years)
    fig.tight_layout()
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)


def _chart_top_institutions_over_time(inst_timeline, path, top_n=10):
    """Stacked bar chart showing top institutions' participation over years."""
    all_data = inst_timeline.get('all', {})
    if not all_data:
        return

    years = sorted(all_data.keys())

    # Find overall top-N institutions
    total_by_inst = defaultdict(int)
    for yr_data in all_data.values():
        for inst, count in yr_data.items():
            total_by_inst[inst] += count
    top_insts = [inst for inst, _ in sorted(total_by_inst.items(), key=lambda x: -x[1])[:top_n]]

    fig, ax = plt.subplots(figsize=(12, 6))
    bottom = np.zeros(len(years))
    colors = plt.cm.tab10(np.linspace(0, 1, len(top_insts)))

    for i, inst in enumerate(top_insts):
        vals = np.array([all_data.get(y, {}).get(inst, 0) for y in years], dtype=float)
        label = inst[:35] if len(inst) > 35 else inst
        ax.bar(years, vals, bottom=bottom, label=label, color=colors[i], width=0.7)
        bottom += vals

    ax.set_xlabel('Year')
    ax.set_ylabel('Committee Members')
    ax.set_title('Top Institutions on AE Committees Over Time', fontweight='bold')
    ax.legend(loc='upper left', fontsize=7, bbox_to_anchor=(1.02, 1))
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, format='svg', bbox_inches='tight')
    plt.close(fig)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Generate committee statistics for the research artifacts website'
    )
    parser.add_argument(
        '--conf_regex', type=str, default='.*20[12][0-9]',
        help='Regular expression for conference names/years'
    )
    parser.add_argument(
        '--output_dir', type=str, default=None,
        help='Output directory (website root, e.g. ../researchartifacts.github.io)'
    )
    args = parser.parse_args()

    generate_committee_data(args.conf_regex, args.output_dir)


if __name__ == '__main__':
    main()
