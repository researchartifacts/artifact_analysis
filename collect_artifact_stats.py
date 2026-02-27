import argparse
import os
import time
import requests
from sys_sec_artifacts_results_scrape import get_ae_results
from test_artifact_repositories import check_artifact_exists
from sys_sec_scrape import (cached_github_stats, cached_zenodo_stats,
                            cached_figshare_stats)

# Keep thin wrappers so existing callers still work
def github_stats(url):
    return cached_github_stats(url)

def zenodo_stats(url):
    return cached_zenodo_stats(url)

def figshare_stats(url):
    return cached_figshare_stats(url)


def get_all_artifact_stats(results, url_keys):
    for name, artifacts in results.items():
        for url_key in url_keys:
            print(f'Getting stats for {len(artifacts)}')
            for artifact in artifacts:
                if url_key+'_exists' in artifact and artifact[url_key+'_exists']:
                    if 'zenodo' in artifact[url_key]:
                        stats = zenodo_stats(artifact[url_key])
                    elif 'figshare' in artifact[url_key]:
                        stats = figshare_stats(artifact[url_key])
                    elif 'github' in artifact[url_key]:
                        stats = github_stats(artifact[url_key])
                    else: # needed since stats doesn't exist otherwise
                        print(f'No stats for {artifact[url_key]} at {name} titled {artifact["title"]}')
                        continue

                    if stats:
                        artifact['stats'] = {**stats, **artifact.get('stats', {})}
                else:
                    print(f'{url_key} does not exist for {artifact["title"]} at {name}')

    return results

def main():

    parser = argparse.ArgumentParser(description='Scraping results of sys/secartifacts.github.io from conferences.')
    parser.add_argument('--conf_regex', type=str, default='.20[1|2][0-9]', help='Regular expression for conference name and or names')
    parser.add_argument('--prefix', type=str, default='sys', help='Prefix of artifacts website like sys for sysartifacts or sec for secartifacts')
    parser.add_argument('--url_keys', type=str, nargs='+', default=['repository_url'], help='Keys in the artifact dictionary to check the URLs for')

    args = parser.parse_args()
    results = get_ae_results(args.conf_regex, args.prefix)
    results, _, _ = check_artifact_exists(results, args.url_keys)

    results = get_all_artifact_stats(results, args.url_keys)

    artifact_id = 0
    for name, artifacts in results.items():
        for artifact in artifacts:
            if 'stats' not in artifact:
                continue

            for key, value in artifact['stats'].items():
                print(f'{name},{artifact_id},{key},{value}')

            artifact_id += 1

if __name__ == "__main__":
    main()