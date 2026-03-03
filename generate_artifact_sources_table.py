#!/usr/bin/env python3
"""
Generate artifact storage source statistics.

Counts artifacts by storage source (GitHub, Zenodo, Figshare, OSF, etc.)
and creates both summary data and detailed CSV for visualization.

Usage:
  python generate_artifact_sources_table.py --conf_regex '.*20[12][0-9]' --output_dir ../acm-rep-2026-paper/reproducibility
"""

import argparse
import json
import os
import re
import yaml
import csv
from collections import defaultdict

from sys_sec_artifacts_results_scrape import get_ae_results
from test_artifact_repositories import _normalise_url


def _resolve_doi_prefix(url):
    """Resolve DOI prefix to actual repository. Returns repository name or None."""
    doi_match = re.search(r"(?:doi\.org/)?(?:https?://doi\.org/)?(10\.\d+(?:[/\.][\w.\-]+)*)", url)
    if not doi_match:
        return None
    
    doi_prefix = doi_match.group(1).split("/")[0].split(".")[0:2]
    doi_prefix_str = ".".join(doi_prefix)
    
    # Map DOI prefixes to repositories
    doi_to_repo = {
        "10.5281": "Zenodo",      # Zenodo
        "10.6084": "Figshare",    # Figshare
        "10.17605": "OSF",        # Open Science Framework
        "10.4121": "Dataverse",   # Royal Data Repository
        "10.60517": "Zenodo",     # Zenodo (alternative prefix)
        "10.7278": "Figshare",    # Figshare (alternative)
        "10.25835": "NIST",       # NIST Data
    }
    
    return doi_to_repo.get(doi_prefix_str)


def extract_source(url):
    """Determine the source of an artifact from its URL."""
    if not url:
        return 'unknown'
    
    url_lower = url.lower()
    
    if 'github.com' in url_lower or 'github.io' in url_lower:
        return 'GitHub'
    elif 'zenodo' in url_lower or 'zenodo.org' in url_lower:
        return 'Zenodo'
    elif 'figshare' in url_lower:
        return 'Figshare'
    elif 'osf.io' in url_lower:
        return 'OSF'
    elif 'gitlab' in url_lower:
        return 'GitLab'
    elif 'bitbucket' in url_lower:
        return 'Bitbucket'
    elif 'archive.org' in url_lower or 'arxiv' in url_lower:
        return 'Archive.org'
    elif 'dataverse' in url_lower:
        return 'Dataverse'
    elif 'archive' in url_lower:
        return 'Archive site'
    elif 'doi.org' in url_lower:
        # Try to resolve DOI to actual repository
        resolved = _resolve_doi_prefix(url_lower)
        return resolved if resolved else 'DOI'
    else:
        return 'Other'


def get_artifact_url(artifact):
    """Extract the first valid URL from an artifact."""
    url_keys = ['repository_url', 'artifact_url', 'github_url', 
                'second_repository_url', 'bitbucket_url', 'artifact_urls']
    
    for key in url_keys:
        val = artifact.get(key, '')
        if isinstance(val, list):
            val = val[0] if val else ''
        val = _normalise_url(val)
        if val:
            return val
    
    return None


def get_artifact_urls(artifact):
    """Extract all normalized URLs from an artifact across known URL keys."""
    url_keys = ['repository_url', 'artifact_url', 'github_url',
                'second_repository_url', 'bitbucket_url', 'artifact_urls']

    urls = []
    for key in url_keys:
        val = artifact.get(key, '')
        if isinstance(val, list):
            candidates = val
        else:
            candidates = [val]

        for candidate in candidates:
            norm = _normalise_url(candidate)
            if norm:
                urls.append(norm)

    deduped = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def count_sources_by_conference(all_results):
    """Count artifacts by source for each conference."""
    stats = defaultdict(lambda: defaultdict(int))
    stats['overall'] = defaultdict(int)
    
    area_map = {}  # Maps conference to area (systems/security)
    
    for conf_year, artifacts in all_results.items():
        conf_name = re.match(r'^([a-zA-Z]+)', conf_year)
        if not conf_name:
            continue
        conf_name = conf_name.group(1).upper()
        
        # Determine area from prefix (this is a heuristic)
        area = 'unknown'
        
        for artifact in artifacts:
            urls = get_artifact_urls(artifact)
            sources = {extract_source(url) for url in urls} if urls else {'unknown'}
            for source in sources:
                stats[conf_name][source] += 1
                stats['overall'][source] += 1
            if urls:
                stats[conf_name]['total'] += 1
                stats['overall']['total'] += 1
    
    return dict(stats)


def count_sources_by_area(all_results):
    """Count artifacts by source for systems vs security."""
    sys_sources = defaultdict(int)
    sec_sources = defaultdict(int)
    sys_no_source = 0
    sec_no_source = 0
    
    for conf_year, artifacts in all_results.items():
        # Determine if this is a systems or security conference
        # Load conference metadata to determine area
        conf_name = re.match(r'^([a-zA-Z]+)', conf_year)
        if not conf_name:
            continue
        conf_name = conf_name.group(1).upper()
        
        # These are from the sysartifacts and secartifacts websites
        systems_confs = {'ATC', 'EUROSYS', 'FAST', 'OSDI', 'SC', 'SOSP'}
        security_confs = {'ACSAC', 'CHES', 'NDSS', 'PETS', 'SYSTEX', 'USENIX', 'WOOT'}
        
        target_dict = None
        is_systems = False
        if conf_name in systems_confs:
            target_dict = sys_sources
            is_systems = True
        elif conf_name in security_confs:
            target_dict = sec_sources
            is_systems = False
        
        if target_dict is None:
            # Try to infer: check for "Security" in second part of conf_year
            if 'security' in conf_year.lower():
                target_dict = sec_sources
                is_systems = False
            else:
                target_dict = sys_sources
                is_systems = True
        
        for artifact in artifacts:
            urls = get_artifact_urls(artifact)
            if urls:
                sources = {extract_source(url) for url in urls}
                for source in sources:
                    target_dict[source] += 1
                target_dict['total'] += 1
            else:
                # Count artifacts without URLs separately
                if is_systems:
                    sys_no_source += 1
                else:
                    sec_no_source += 1
    
    return {
        'systems': dict(sys_sources),
        'security': dict(sec_sources),
        'systems_no_source': sys_no_source,
        'security_no_source': sec_no_source,
    }


def count_sources_overall(all_results):
    """Count artifacts by source overall."""
    sources = defaultdict(int)
    
    for conf_year, artifacts in all_results.items():
        for artifact in artifacts:
            urls = get_artifact_urls(artifact)
            source_set = {extract_source(url) for url in urls} if urls else {'unknown'}
            for source in source_set:
                sources[source] += 1
            if urls:
                sources['total'] += 1
    
    return dict(sources)


def main():
    parser = argparse.ArgumentParser(
        description='Generate artifact sources table and statistics.'
    )
    parser.add_argument(
        '--conf_regex', 
        type=str, 
        default='.*20[12][0-9]',
        help='Regex for conference names/years'
    )
    parser.add_argument(
        '--output_dir', 
        type=str, 
        default=None,
        help='Output directory for CSV files'
    )
    args = parser.parse_args()

    # Try to load cached results
    cache_path = None
    if args.output_dir:
        cache_path = os.path.join(args.output_dir, '_data', 'all_results_cache.yml')
    if not cache_path or not os.path.exists(cache_path):
        cache_path = os.path.join(os.path.dirname(__file__) or '.', '.cache', 'all_results_cache.yml')

    if os.path.exists(cache_path):
        print(f"Loading cached results from {cache_path}...")
        with open(cache_path, 'r') as f:
            all_results = yaml.safe_load(f) or {}
        all_results = {k: v for k, v in all_results.items() if re.search(args.conf_regex, k)}
        print(f"Loaded {sum(len(v) for v in all_results.values())} artifacts")
    else:
        print("Collecting artifact results (scraping)...")
        sys_results = get_ae_results(args.conf_regex, 'sys')
        sec_results = get_ae_results(args.conf_regex, 'sec')
        all_results = {**sys_results, **sec_results}
        print(f"Found {sum(len(v) for v in all_results.values())} artifacts")

    print("\nAnalyzing artifact sources...")
    
    # Get statistics
    by_conf = count_sources_by_conference(all_results)
    by_area = count_sources_by_area(all_results)
    overall = count_sources_overall(all_results)
    
    # Print overall summary
    print("\nOverall artifact sources:")
    for source in sorted(overall.keys(), key=lambda x: overall[x], reverse=True):
        count = overall[source]
        pct = (count / overall.get('total', 1) * 100) if source != 'total' else 0
        if source == 'total':
            print(f"  Total artifacts: {count}")
        else:
            print(f"  {source}: {count} ({pct:.1f}%)")
    
    print("\nArtifacts by area:")
    print(f"  Systems: {by_area['systems'].get('total', 0)} total")
    for source in sorted(by_area['systems'].keys(), key=lambda x: by_area['systems'][x], reverse=True):
        if source != 'total':
            count = by_area['systems'][source]
            pct = count / by_area['systems'].get('total', 1) * 100
            print(f"    {source}: {count} ({pct:.1f}%)")
    
    print(f"\n  Security: {by_area['security'].get('total', 0)} total")
    for source in sorted(by_area['security'].keys(), key=lambda x: by_area['security'][x], reverse=True):
        if source != 'total':
            count = by_area['security'][source]
            pct = count / by_area['security'].get('total', 1) * 100
            print(f"    {source}: {count} ({pct:.1f}%)")

    # Generate CSV files
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Overall sources CSV
        sources_csv = os.path.join(args.output_dir, 'artifact_sources_overall.csv')
        with open(sources_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Source', 'Count', 'Percentage'])
            writer.writeheader()
            total = overall.get('total', sum(v for k, v in overall.items() if k != 'total'))
            for source in sorted(overall.keys(), key=lambda x: overall[x], reverse=True):
                if source != 'total':
                    count = overall[source]
                    pct = count / total * 100 if total > 0 else 0
                    writer.writerow({'Source': source, 'Count': count, 'Percentage': f'{pct:.1f}'})
        print(f"\nWritten: {sources_csv}")
        
        # By-area CSV
        area_csv = os.path.join(args.output_dir, 'artifact_sources_by_area.csv')
        with open(area_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Source', 'Systems', 'Security', 'Total'])
            writer.writeheader()
            all_sources = set(by_area['systems'].keys()) | set(by_area['security'].keys())
            for source in sorted(all_sources):
                if source != 'total' and source != 'unknown':
                    sys_count = by_area['systems'].get(source, 0)
                    sec_count = by_area['security'].get(source, 0)
                    total_count = sys_count + sec_count
                    writer.writerow({
                        'Source': source,
                        'Systems': sys_count,
                        'Security': sec_count,
                        'Total': total_count
                    })
            # Add "Without Source" row
            sys_no_source = by_area.get('systems_no_source', 0)
            sec_no_source = by_area.get('security_no_source', 0)
            writer.writerow({
                'Source': 'Without Source',
                'Systems': sys_no_source,
                'Security': sec_no_source,
                'Total': sys_no_source + sec_no_source
            })
            # Add total row
            sys_total = by_area['systems'].get('total', 0)
            sec_total = by_area['security'].get('total', 0)
            writer.writerow({
                'Source': 'TOTAL',
                'Systems': sys_total,
                'Security': sec_total,
                'Total': sys_total + sec_total
            })
        print(f"Written: {area_csv}")
        
        # By-conference CSV (top conferences)
        conf_csv = os.path.join(args.output_dir, 'artifact_sources_by_conference.csv')
        with open(conf_csv, 'w', newline='') as f:
            # Get all sources
            all_sources = set()
            for conf_stats in by_conf.values():
                all_sources.update(k for k in conf_stats.keys() if k != 'total')
            
            fieldnames = ['Conference'] + sorted(all_sources)
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval=0)
            writer.writeheader()
            
            # Sort by total and write
            sorted_confs = sorted([k for k in by_conf.keys() if k != 'overall'], 
                                key=lambda x: by_conf[x].get('total', 0), reverse=True)
            for conf in sorted_confs:
                row = {'Conference': conf}
                row.update({s: by_conf[conf].get(s, 0) for s in all_sources})
                writer.writerow(row)
        print(f"Written: {conf_csv}")
    
    return 0


if __name__ == '__main__':
    exit(main())
