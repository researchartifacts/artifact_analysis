"""
Generate repository statistics (stars, forks, etc.) for the website.

Collects stats from GitHub/Zenodo/Figshare for all scraped artifacts and writes:
  - _data/repo_stats.yml              — per-conference/year aggregates (for website)
  - assets/data/repo_stats_detail.json — per-repo detail (for analysis/figures)

Usage:
  python generate_repo_stats.py --conf_regex '.*20[12][0-9]' --output_dir ../researchartifacts.github.io
"""

import argparse
import json
import os
import re
import yaml
from collections import defaultdict
from datetime import datetime

from ..scrapers.sys_sec_artifacts_results_scrape import get_ae_results
from ..scrapers.sys_sec_scrape import get_conferences_from_prefix
from ..utils.collect_artifact_stats import github_stats, zenodo_stats, figshare_stats
from ..utils.test_artifact_repositories import check_artifact_exists
from ..utils.conference import conf_area as _conf_area, parse_conf_year as extract_conference_name


def collect_stats_for_results(results, url_keys=None):
    """Collect repository stats for all artifacts."""
    if url_keys is None:
        url_keys = ['repository_url', 'artifact_url', 'github_url',
                     'second_repository_url', 'bitbucket_url']

    # First pass: extract ALL URLs from list-valued fields and create expanded artifact entries
    # This ensures we collect stats for every artifact location, not just the first
    expanded_artifacts = {}
    for conf_year, artifacts in results.items():
        expanded_artifacts[conf_year] = []
        for artifact in artifacts:
            # Collect all URLs from this artifact (including multi-valued fields)
            all_urls_by_key = {}
            
            # Add single-valued URL fields
            for url_key in url_keys:
                if url_key in artifact and artifact[url_key]:
                    all_urls_by_key[url_key] = [artifact[url_key]]
            
            # Add URLs from list-valued fields (artifact_urls, additional_urls, etc.)
            for list_key in ['artifact_urls', 'additional_urls']:
                if list_key in artifact and isinstance(artifact[list_key], list):
                    for url in artifact[list_key]:
                        if isinstance(url, str) and url:
                            # Map back to single key: artifact_urls -> artifact_url
                            flat_key = list_key.rstrip('s')
                            if flat_key not in all_urls_by_key:
                                all_urls_by_key[flat_key] = []
                            if url not in all_urls_by_key[flat_key]:
                                all_urls_by_key[flat_key].append(url)
            
            # Create separate artifact entry for each URL to process
            if all_urls_by_key:
                for url_key, urls in all_urls_by_key.items():
                    for url in urls:
                        artifact_copy = {k: v for k, v in artifact.items() 
                                        if k not in ['artifact_urls', 'additional_urls']}
                        artifact_copy[url_key] = url
                        expanded_artifacts[conf_year].append(artifact_copy)
            else:
                # No URLs found, keep original artifact
                expanded_artifacts[conf_year].append(artifact)
    
    results = expanded_artifacts

    # Filter url_keys to only those that actually appear in the data
    present_keys = set()
    for artifacts in results.values():
        for artifact in artifacts:
            for key in url_keys:
                if key in artifact and artifact[key]:
                    present_keys.add(key)
    url_keys = [k for k in url_keys if k in present_keys]
    if not url_keys:
        print("  Warning: No URL keys found in artifact data. No repository stats to collect.")
        return []
    print(f"  Scanning URL fields: {', '.join(url_keys)}")

    # Check which URLs exist
    results, _, _ = check_artifact_exists(results, url_keys)

    all_stats = []
    seen_urls = set()

    total_artifacts = sum(len(arts) for arts in results.values())
    processed = 0
    collected = 0

    for conf_year, artifacts in results.items():
        conf_name, year = extract_conference_name(conf_year)
        if year is None:
            continue

        for artifact in artifacts:
            processed += 1
            for url_key in url_keys:
                url = artifact.get(url_key, '')
                exists_key = f'{url_key}_exists'
                if not artifact.get(exists_key, False) or not url:
                    continue

                # Deduplicate: skip if we've already collected stats for this URL
                url_normalized = url.rstrip('/')
                if url_normalized in seen_urls:
                    continue
                seen_urls.add(url_normalized)

                stats = None
                source = 'unknown'
                try:
                    if 'github' in url:
                        stats = github_stats(url)
                        source = 'github'
                    elif 'zenodo' in url:
                        stats = zenodo_stats(url)
                        source = 'zenodo'
                    elif 'figshare' in url:
                        stats = figshare_stats(url)
                        source = 'figshare'
                except Exception as e:
                    print(f"  Error collecting stats for {url}: {e}")
                    continue

                if stats:
                    collected += 1
                    entry = {
                        'conference': conf_name,
                        'year': year,
                        'title': artifact.get('title', 'Unknown'),
                        'url': url,
                        'source': source,
                    }
                    entry.update(stats)
                    all_stats.append(entry)

            if processed % 50 == 0 or processed == total_artifacts:
                print(f"  Progress: {processed}/{total_artifacts} artifacts checked, "
                      f"{collected} stats collected, {len(seen_urls)} unique URLs")

    return all_stats


def aggregate_stats(all_stats):
    """Aggregate per-conference and per-year statistics."""
    # Per-conference aggregates
    by_conf = defaultdict(lambda: {
        'github_repos': 0, 'total_stars': 0, 'total_forks': 0,
        'max_stars': 0, 'max_forks': 0,
        'zenodo_repos': 0, 'total_views': 0, 'total_downloads': 0,
        'years': defaultdict(lambda: {'github_repos': 0, 'stars': 0, 'forks': 0}),
        'all_github_entries': [],
    })

    by_year = defaultdict(lambda: {
        'github_repos': 0, 'total_stars': 0, 'total_forks': 0,
        'max_stars': 0, 'max_forks': 0,
        'zenodo_repos': 0, 'total_views': 0, 'total_downloads': 0,
    })

    overall = {
        'github_repos': 0, 'total_stars': 0, 'total_forks': 0,
        'max_stars': 0, 'max_forks': 0,
        'zenodo_repos': 0, 'total_views': 0, 'total_downloads': 0,
        'avg_stars': 0, 'avg_forks': 0,
    }

    for s in all_stats:
        conf = s['conference']
        year = s['year']

        if s['source'] == 'github':
            stars = s.get('github_stars', 0) or 0
            forks = s.get('github_forks', 0) or 0

            by_conf[conf]['github_repos'] += 1
            by_conf[conf]['total_stars'] += stars
            by_conf[conf]['total_forks'] += forks
            by_conf[conf]['max_stars'] = max(by_conf[conf]['max_stars'], stars)
            by_conf[conf]['max_forks'] = max(by_conf[conf]['max_forks'], forks)
            by_conf[conf]['years'][year]['github_repos'] += 1
            by_conf[conf]['years'][year]['stars'] += stars
            by_conf[conf]['years'][year]['forks'] += forks
            by_conf[conf]['all_github_entries'].append({
                'title': s.get('title', 'Unknown'),
                'url': s.get('url', ''),
                'conference': conf,
                'year': year,
                'area': _conf_area(conf),
                'stars': stars,
                'forks': forks,
                'description': (s.get('description', '') or '')[:120],
                'language': s.get('language', '') or '',
                'name': s.get('name', ''),
                'pushed_at': s.get('pushed_at', ''),
            })

            by_year[year]['github_repos'] += 1
            by_year[year]['total_stars'] += stars
            by_year[year]['total_forks'] += forks
            by_year[year]['max_stars'] = max(by_year[year]['max_stars'], stars)
            by_year[year]['max_forks'] = max(by_year[year]['max_forks'], forks)

            overall['github_repos'] += 1
            overall['total_stars'] += stars
            overall['total_forks'] += forks
            overall['max_stars'] = max(overall['max_stars'], stars)
            overall['max_forks'] = max(overall['max_forks'], forks)

        elif s['source'] == 'zenodo':
            views = s.get('zenodo_views', 0) or 0
            downloads = s.get('zenodo_downloads', 0) or 0

            by_conf[conf]['zenodo_repos'] += 1
            by_conf[conf]['total_views'] += views
            by_conf[conf]['total_downloads'] += downloads

            by_year[year]['zenodo_repos'] += 1
            by_year[year]['total_views'] += views
            by_year[year]['total_downloads'] += downloads

            overall['zenodo_repos'] += 1
            overall['total_views'] += views
            overall['total_downloads'] += downloads

    if overall['github_repos'] > 0:
        overall['avg_stars'] = round(overall['total_stars'] / overall['github_repos'], 1)
        overall['avg_forks'] = round(overall['total_forks'] / overall['github_repos'], 1)

    # Convert to serializable format
    conf_stats = []
    for conf_name in sorted(by_conf.keys()):
        d = by_conf[conf_name]
        avg_stars = round(d['total_stars'] / d['github_repos'], 1) if d['github_repos'] > 0 else 0
        avg_forks = round(d['total_forks'] / d['github_repos'], 1) if d['github_repos'] > 0 else 0
        year_list = []
        for yr in sorted(d['years'].keys()):
            yd = d['years'][yr]
            year_list.append({
                'year': yr,
                'github_repos': yd['github_repos'],
                'stars': yd['stars'],
                'forks': yd['forks'],
                'avg_stars': round(yd['stars'] / yd['github_repos'], 1) if yd['github_repos'] > 0 else 0,
                'avg_forks': round(yd['forks'] / yd['github_repos'], 1) if yd['github_repos'] > 0 else 0,
            })
        # Top 5 repos by stars
        top_repos = sorted(d['all_github_entries'], key=lambda x: x['stars'], reverse=True)[:5]
        conf_stats.append({
            'name': conf_name,
            'github_repos': d['github_repos'],
            'total_stars': d['total_stars'],
            'total_forks': d['total_forks'],
            'avg_stars': avg_stars,
            'avg_forks': avg_forks,
            'max_stars': d['max_stars'],
            'max_forks': d['max_forks'],
            'years': year_list,
            'top_repos': top_repos,
        })

    year_stats = []
    for yr in sorted(by_year.keys()):
        d = by_year[yr]
        avg_stars = round(d['total_stars'] / d['github_repos'], 1) if d['github_repos'] > 0 else 0
        avg_forks = round(d['total_forks'] / d['github_repos'], 1) if d['github_repos'] > 0 else 0
        year_stats.append({
            'year': yr,
            'github_repos': d['github_repos'],
            'total_stars': d['total_stars'],
            'total_forks': d['total_forks'],
            'avg_stars': avg_stars,
            'avg_forks': avg_forks,
            'max_stars': d['max_stars'],
            'max_forks': d['max_forks'],
        })

    overall['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')

    # Per-repo detail: all GitHub entries with individual star/fork counts
    all_github_detail = []
    for conf_name in sorted(by_conf.keys()):
        all_github_detail.extend(by_conf[conf_name]['all_github_entries'])

    return {
        'overall': overall,
        'by_conference': conf_stats,
        'by_year': year_stats,
        'all_github_repos': all_github_detail,
    }


def main():
    parser = argparse.ArgumentParser(description='Generate repository statistics.')
    parser.add_argument('--conf_regex', type=str, default='.*20[12][0-9]',
                        help='Regex for conference names/years')
    parser.add_argument('--output_dir', type=str, default=None,
                        help='Website repo root directory')
    args = parser.parse_args()

    # Try to load the cached results written by generate_statistics.py to
    # avoid re-scraping every results.md file.
    cache_path = None
    if args.output_dir:
        cache_path = os.path.join(args.output_dir, '_data', 'all_results_cache.yml')
    if not cache_path or not os.path.exists(cache_path):
        # Fallback: repo root .cache directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(script_dir)
        cache_path = os.path.join(repo_root, '.cache', 'all_results_cache.yml')

    if os.path.exists(cache_path):
        print(f"Loading cached results from {cache_path}...")
        with open(cache_path, 'r') as f:
            all_results = yaml.safe_load(f) or {}
        # Filter by conf_regex (cache may contain more conferences)
        all_results = {k: v for k, v in all_results.items() if re.search(args.conf_regex, k)}
        print(f"Loaded {sum(len(v) for v in all_results.values())} artifacts across {len(all_results)} conference-years (from cache)")
    else:
        print("Collecting artifact results (no cache found, scraping)...")
        sys_results = get_ae_results(args.conf_regex, 'sys')
        sec_results = get_ae_results(args.conf_regex, 'sec')
        all_results = {**sys_results, **sec_results}
        print(f"Found {sum(len(v) for v in all_results.values())} artifacts across {len(all_results)} conference-years")

    print("Collecting repository statistics (this may take a while)...")
    all_stats = collect_stats_for_results(all_results)
    print(f"Collected stats for {len(all_stats)} repositories")

    print("Aggregating statistics...")
    aggregated = aggregate_stats(all_stats)

    print(f"Overall: {aggregated['overall']['github_repos']} GitHub repos, "
          f"{aggregated['overall']['total_stars']} total stars, "
          f"{aggregated['overall']['total_forks']} total forks")

    if args.output_dir:
        data_dir = os.path.join(args.output_dir, '_data')
        assets_dir = os.path.join(args.output_dir, 'assets', 'data')
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(assets_dir, exist_ok=True)
        out_path = os.path.join(data_dir, 'repo_stats.yml')
        with open(out_path, 'w') as f:
            yaml.dump({k: v for k, v in aggregated.items() if k != 'all_github_repos'},
                      f, default_flow_style=False, sort_keys=False)
        print(f"Written to {out_path}")

        # Write per-repo detail JSON for CDF generation
        detail_path = os.path.join(assets_dir, 'repo_stats_detail.json')
        with open(detail_path, 'w') as f:
            json.dump(aggregated.get('all_github_repos', []), f, indent=2)
        print(f"Written per-repo detail ({len(aggregated.get('all_github_repos', []))} repos) to {detail_path}")

    return aggregated


if __name__ == '__main__':
    main()
