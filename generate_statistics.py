#!/usr/bin/env python3
"""
Generate comprehensive statistics and data files for the researchartifacts website.
This script collects data from both sysartifacts and secartifacts, processes it,
and generates YAML/JSON files for Jekyll to render.
"""

import json
import os
import yaml
import argparse
from datetime import datetime
from collections import defaultdict
import re
from sys_sec_artifacts_results_scrape import get_ae_results
from sys_sec_scrape import get_conferences_from_prefix
from usenix_scrape import scrape_conference_year, to_pipeline_format
from acm_scrape import (
    scrape_conference_year as acm_scrape_conference_year,
    to_pipeline_format as acm_to_pipeline_format,
    get_acm_conferences,
)

# Workshops (as opposed to conferences) — used for visual distinction
WORKSHOPS = {'woot', 'systex'}

# Mapping from sysartifacts/secartifacts conference prefix to the USENIX URL
# conference short-name and category.  When a conference directory exists on
# sysartifacts or secartifacts but has NO results.md, the pipeline will
# automatically try to scrape it from usenix.org using this mapping.
USENIX_CONF_MAP = {
    'fast':      ('fast',             'systems'),
    'osdi':      ('osdi',             'systems'),
    'atc':       ('atc',              'systems'),
    'usenixsec': ('usenixsecurity',  'security'),
}

def extract_conference_name(conf_year_str):
    """Extract conference name from string like 'osdi2024' -> 'osdi'"""
    match = re.match(r'^([a-zA-Z]+)(\d{4})$', conf_year_str)
    if match:
        return match.group(1), match.group(2)
    return conf_year_str, None

def count_badges(artifacts):
    """Count different badge types in artifacts list"""
    badges = {
        'available': 0,
        'functional': 0,
        'reproducible': 0,
        'reusable': 0,
        'replicated': 0
    }
    
    for artifact in artifacts:
        if 'badges' in artifact and artifact['badges']:
            badge_list = artifact['badges']
            if isinstance(badge_list, str):
                badge_list = [b.strip() for b in badge_list.split(',')]
            for badge in badge_list:
                badge_lower = badge.lower()
                if 'available' in badge_lower:
                    badges['available'] += 1
                if 'functional' in badge_lower:
                    badges['functional'] += 1
                if 'reproduc' in badge_lower or 'replicated' in badge_lower:
                    badges['reproducible'] += 1
                if 'reusable' in badge_lower:
                    badges['reusable'] += 1
    
    return badges

def generate_statistics(conf_regex='.*20[12][0-9]', output_dir=None):
    """
    Generate comprehensive statistics from sys and sec artifacts.
    
    Args:
        conf_regex: Regex to match conference names
        output_dir: Directory to write output files (default: current directory)
    
    Returns:
        Dictionary with all generated data
    """
    
    # Collecting artifact data from both sources
    sys_results = get_ae_results(conf_regex, 'sys')
    sec_results = get_ae_results(conf_regex, 'sec')

    # Track all discovered conference dirs (for coverage table)
    sys_all_dirs = {item['name'] for item in get_conferences_from_prefix('sys')
                    if re.search(conf_regex, item['name'])}
    sec_all_dirs = {item['name'] for item in get_conferences_from_prefix('sec')
                    if re.search(conf_regex, item['name'])}

    # --- Automatic USENIX fallback ---
    # For every sysartifacts / secartifacts directory that has NO results,
    # check if it maps to a USENIX conference and try scraping from usenix.org.
    usenix_results = {}
    usenix_categories = {}  # conf_year -> category
    parsed_keys = set(sys_results.keys()) | set(sec_results.keys())

    for dir_name in sorted(sys_all_dirs | sec_all_dirs):
        if dir_name in parsed_keys:
            continue  # already have results from sysartifacts/secartifacts
        conf_name, year_str = extract_conference_name(dir_name)
        if not year_str:
            continue
        year = int(year_str)
        conf_lower = conf_name.lower()
        if conf_lower not in USENIX_CONF_MAP:
            continue
        usenix_short, category = USENIX_CONF_MAP[conf_lower]
        if not re.search(conf_regex, dir_name):
            continue
        print(f"Scraping USENIX {conf_name.upper()} {year} (fallback for missing sysartifacts results)...")
        try:
            artifacts = scrape_conference_year(usenix_short, year, max_workers=4, delay=0.3)
            pipeline_arts = to_pipeline_format(artifacts)
            if pipeline_arts:
                usenix_results[dir_name] = pipeline_arts
                usenix_categories[dir_name] = category
                print(f"  Got {len(pipeline_arts)} artifacts with badges")
            else:
                print(f"  No artifacts with badges found")
        except Exception as e:
            print(f"  Error scraping {conf_name.upper()} {year}: {e}")
    
    # --- ACM conference scraping (independent of sysartifacts/secartifacts) ---
    # ACM conferences like CCS are not tracked on sysartifacts or secartifacts.
    # We scrape them directly via DBLP + ACM DL.
    acm_results = {}
    acm_categories = {}  # conf_year -> category
    acm_confs = get_acm_conferences()
    # Don't scrape conferences already handled by sysartifacts (e.g. SOSP)
    handled_confs = set()
    for d in (sys_all_dirs | sec_all_dirs | set(usenix_results.keys())):
        cn, _ = extract_conference_name(d)
        if cn:
            handled_confs.add(cn.lower())

    for acm_key, acm_meta in acm_confs.items():
        if acm_key in handled_confs:
            continue  # already handled by sysartifacts/secartifacts
        category = acm_meta['category']
        for year in sorted(acm_meta.get('proceedings_dois', {}).keys()):
            conf_year_key = f"{acm_key}{year}"
            if not re.search(conf_regex, conf_year_key):
                continue
            print(f"Scraping ACM {acm_meta['display_name']} {year} (DBLP + ACM DL)...")
            try:
                artifacts = acm_scrape_conference_year(acm_key, year, max_workers=4, delay=0.5)
                pipeline_arts = acm_to_pipeline_format(artifacts)
                if pipeline_arts:
                    acm_results[conf_year_key] = pipeline_arts
                    acm_categories[conf_year_key] = category
                    print(f"  Got {len(pipeline_arts)} artifacts with badges")
                else:
                    # Even without badges, record the conference as discovered
                    acm_results[conf_year_key] = []
                    acm_categories[conf_year_key] = category
                    print(f"  No artifacts with badges found (ACM DL may be blocked)")
            except Exception as e:
                print(f"  Error scraping {acm_meta['display_name']} {year}: {e}")

    # Tag each result by source
    sys_conf_years = set(sys_results.keys())
    usenix_conf_years = set(usenix_results.keys())
    acm_conf_years = set(acm_results.keys())
    
    # Combine results (sys + sec + usenix + acm)
    all_results = {**sys_results, **sec_results, **usenix_results, **acm_results}

    # Persist raw results so downstream steps (e.g. generate_repo_stats) can
    # skip re-scraping.  The cache file is written next to the other _data/
    # YAML files when an output_dir is given, otherwise to a local .cache dir.
    _cache_dir = os.path.join(output_dir, '_data') if output_dir else '.cache'
    os.makedirs(_cache_dir, exist_ok=True)
    _cache_path = os.path.join(_cache_dir, 'all_results_cache.yml')
    with open(_cache_path, 'w') as _f:
        yaml.dump(all_results, _f, default_flow_style=False, sort_keys=False)
    print(f"Cached raw results ({sum(len(v) for v in all_results.values())} artifacts) → {_cache_path}")

    # Organize by conference
    by_conference = defaultdict(lambda: {'years': [], 'total_artifacts': 0, 'category': 'unknown'})
    all_artifacts = []
    years_set = set()
    conferences_set = set()
    systems_artifacts_count = 0
    security_artifacts_count = 0
    
    for conf_year, artifacts in all_results.items():
        conf_name, year = extract_conference_name(conf_year)
        
        # Determine category by source
        if conf_year in sys_conf_years:
            category = 'systems'
            systems_artifacts_count += len(artifacts)
        elif conf_year in usenix_conf_years:
            category = usenix_categories.get(conf_year, 'systems')
            if category == 'systems':
                systems_artifacts_count += len(artifacts)
            else:
                security_artifacts_count += len(artifacts)
        elif conf_year in acm_conf_years:
            category = acm_categories.get(conf_year, 'security')
            if category == 'systems':
                systems_artifacts_count += len(artifacts)
            else:
                security_artifacts_count += len(artifacts)
        else:
            category = 'security'
            security_artifacts_count += len(artifacts)
        
        if year:
            years_set.add(int(year))
            conferences_set.add(conf_name.upper())
            
            badges = count_badges(artifacts)
            
            year_data = {
                'year': int(year),
                'total': len(artifacts),
                'functional': badges['functional'],
                'reproducible': badges['reproducible'],
                'available': badges['available'],
                'reusable': badges['reusable']
            }
            
            venue_type = 'workshop' if conf_name.lower() in WORKSHOPS else 'conference'
            
            by_conference[conf_name.upper()]['years'].append(year_data)
            by_conference[conf_name.upper()]['total_artifacts'] += len(artifacts)
            by_conference[conf_name.upper()]['category'] = category
            by_conference[conf_name.upper()]['venue_type'] = venue_type
            
            # Collect all artifacts with metadata
            for artifact in artifacts:
                raw_badges = artifact.get('badges', [])
                if isinstance(raw_badges, str):
                    raw_badges = [b.strip() for b in raw_badges.split(',')]
                # Resolve the best repository URL from several possible keys
                repo_url = (artifact.get('repository_url', '')
                            or artifact.get('github_url', '')
                            or artifact.get('second_repository_url', '')
                            or artifact.get('bitbucket_url', ''))
                # Resolve artifact URL, including list-valued fields
                art_url = artifact.get('artifact_url', '')
                if not art_url and isinstance(artifact.get('artifact_urls'), list):
                    art_url = artifact['artifact_urls'][0] if artifact['artifact_urls'] else ''
                artifact_entry = {
                    'conference': conf_name.upper(),
                    'category': category,
                    'year': int(year),
                    'title': artifact.get('title', 'Unknown'),
                    'badges': raw_badges,
                    'repository_url': repo_url,
                    'artifact_url': art_url,
                }
                all_artifacts.append(artifact_entry)
    
    # Sort years for each conference
    for conf in by_conference.values():
        conf['years'] = sorted(conf['years'], key=lambda x: x['year'])
    
    # Separate conferences by category
    systems_confs = sorted([c for c, d in by_conference.items() if d['category'] == 'systems'])
    security_confs = sorted([c for c, d in by_conference.items() if d['category'] == 'security'])
    
    # Generate summary statistics
    summary = {
        'total_artifacts': len(all_artifacts),
        'total_conferences': len(conferences_set),
        'systems_artifacts': systems_artifacts_count,
        'security_artifacts': security_artifacts_count,
        'conferences_list': sorted(list(conferences_set)),
        'systems_conferences': systems_confs,
        'security_conferences': security_confs,
        'year_range': f"{min(years_set)}-{max(years_set)}" if years_set else "N/A",
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    }
    
    # Format for Jekyll
    artifacts_by_conference = []
    for conf_name in sorted(by_conference.keys()):
        conf_data = by_conference[conf_name]
        artifacts_by_conference.append({
            'name': conf_name,
            'category': conf_data['category'],
            'venue_type': conf_data.get('venue_type', 'conference'),
            'total_artifacts': conf_data['total_artifacts'],
            'years': conf_data['years']
        })
    
    # Calculate yearly totals (overall and by category)
    yearly_totals = defaultdict(lambda: {'total': 0, 'systems': 0, 'security': 0})
    for artifact in all_artifacts:
        year = artifact['year']
        category = artifact['category']
        yearly_totals[year]['total'] += 1
        if category == 'systems':
            yearly_totals[year]['systems'] += 1
        elif category == 'security':
            yearly_totals[year]['security'] += 1
    
    artifacts_by_year = [
        {
            'year': year, 
            'count': data['total'],
            'systems': data['systems'],
            'security': data['security']
        }
        for year, data in sorted(yearly_totals.items())
    ]
    
    # Build coverage table: which conference/year combos were discovered vs parsed
    all_discovered = {}
    for d in sys_all_dirs | sec_all_dirs:
        cname, cyear = extract_conference_name(d)
        if cyear:
            category = 'systems' if d in sys_all_dirs else 'security'
            all_discovered[d] = {
                'conference': cname.upper(),
                'year': int(cyear),
                'category': category,
                'parsed': d in all_results and len(all_results[d]) > 0,
                'artifact_count': len(all_results.get(d, []))
            }
    # Add USENIX conferences to coverage
    for d in usenix_conf_years:
        cname, cyear = extract_conference_name(d)
        if cyear:
            category = usenix_categories.get(d, 'systems')
            all_discovered[d] = {
                'conference': cname.upper(),
                'year': int(cyear),
                'category': category,
                'parsed': d in all_results and len(all_results[d]) > 0,
                'artifact_count': len(all_results.get(d, []))
            }
    # Add ACM conferences to coverage
    for d in acm_conf_years:
        cname, cyear = extract_conference_name(d)
        if cyear:
            category = acm_categories.get(d, 'security')
            all_discovered[d] = {
                'conference': cname.upper(),
                'year': int(cyear),
                'category': category,
                'parsed': d in all_results and len(all_results[d]) > 0,
                'artifact_count': len(all_results.get(d, []))
            }

    coverage = sorted(all_discovered.values(), key=lambda x: (x['conference'], x['year']))

    # Prepare output data
    output_data = {
        'summary': summary,
        'artifacts_by_conference': artifacts_by_conference,
        'artifacts_by_year': artifacts_by_year,
        'all_artifacts': all_artifacts,
        'coverage': coverage
    }
    
    # Write output files
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'assets/data'), exist_ok=True)
        
        # Write YAML files for Jekyll _data directory
        with open(os.path.join(output_dir, '_data/summary.yml'), 'w') as f:
            yaml.dump(summary, f, default_flow_style=False)
        
        with open(os.path.join(output_dir, '_data/artifacts_by_conference.yml'), 'w') as f:
            yaml.dump(artifacts_by_conference, f, default_flow_style=False)
        
        with open(os.path.join(output_dir, '_data/artifacts_by_year.yml'), 'w') as f:
            yaml.dump(artifacts_by_year, f, default_flow_style=False)
        
        with open(os.path.join(output_dir, '_data/coverage.yml'), 'w') as f:
            yaml.dump(coverage, f, default_flow_style=False)
        
        # Write JSON files for download
        with open(os.path.join(output_dir, 'assets/data/artifacts.json'), 'w') as f:
            json.dump(all_artifacts, f, indent=2)
        
        with open(os.path.join(output_dir, 'assets/data/summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"Data files written to {output_dir}")
    
    return output_data

def main():
    parser = argparse.ArgumentParser(
        description='Generate statistics for research artifacts website'
    )
    parser.add_argument(
        '--conf_regex',
        type=str,
        default='.*20[12][0-9]',
        help='Regular expression for conference names/years'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        default=None,
        help='Output directory for generated files'
    )
    
    args = parser.parse_args()
    
    data = generate_statistics(args.conf_regex, args.output_dir)
    
    print(f"\nStatistics generated: {data['summary']['total_artifacts']} artifacts from {data['summary']['total_conferences']} conferences ({data['summary']['year_range']})")

if __name__ == '__main__':
    main()
