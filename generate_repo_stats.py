"""
Generate aggregate repository statistics (stars, forks, etc.) for the website.

Collects stats from GitHub/Zenodo/Figshare for all scraped artifacts and
writes per-conference and per-year aggregate data to YAML.

Usage:
  python generate_repo_stats.py --conf_regex '.*20[12][0-9]' --output_dir ../researchartifacts.github.io
"""

import argparse
import json
import os
import yaml
from collections import defaultdict
from datetime import datetime

from sys_sec_artifacts_results_scrape import get_ae_results
from sys_sec_scrape import get_conferences_from_prefix
from collect_artifact_stats import github_stats, zenodo_stats, figshare_stats
from test_artifact_repositories import check_artifact_exists

import re


def extract_conference_name(conf_year_str):
    match = re.match(r'^([a-zA-Z]+)(\d{4})$', conf_year_str)
    if match:
        return match.group(1).upper(), int(match.group(2))
    return conf_year_str.upper(), None


def collect_stats_for_results(results, url_keys=None):
    """Collect repository stats for all artifacts."""
    if url_keys is None:
        url_keys = ['repository_url', 'artifact_url', 'github_url',
                     'second_repository_url', 'bitbucket_url']

    # Flatten list-valued URL fields (e.g. artifact_urls) into the first
    # single-value key so existing logic can handle them.
    for artifacts in results.values():
        for artifact in artifacts:
            for list_key in ['artifact_urls', 'additional_urls']:
                if list_key in artifact and isinstance(artifact[list_key], list):
                    for i, url in enumerate(artifact[list_key]):
                        if isinstance(url, str) and url:
                            flat_key = list_key.rstrip('s')  # artifact_urls -> artifact_url
                            if flat_key not in artifact or not artifact[flat_key]:
                                artifact[flat_key] = url

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

    # First check which URLs exist
    results, _, _ = check_artifact_exists(results, url_keys)

    all_stats = []
    seen_urls = set()

    for conf_year, artifacts in results.items():
        conf_name, year = extract_conference_name(conf_year)
        if year is None:
            continue

        for artifact in artifacts:
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
                    entry = {
                        'conference': conf_name,
                        'year': year,
                        'title': artifact.get('title', 'Unknown'),
                        'url': url,
                        'source': source,
                    }
                    entry.update(stats)
                    all_stats.append(entry)

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
                'year': year,
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

    return {
        'overall': overall,
        'by_conference': conf_stats,
        'by_year': year_stats,
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
        # Fallback: local .cache directory
        cache_path = os.path.join(os.path.dirname(__file__) or '.', '.cache', 'all_results_cache.yml')

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
        os.makedirs(data_dir, exist_ok=True)
        out_path = os.path.join(data_dir, 'repo_stats.yml')
        with open(out_path, 'w') as f:
            yaml.dump(aggregated, f, default_flow_style=False, sort_keys=False)
        print(f"Written to {out_path}")

    return aggregated


if __name__ == '__main__':
    main()
