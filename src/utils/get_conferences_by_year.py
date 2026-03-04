#!/usr/bin/env python3
"""
Count the number of conferences scraped per year.
"""

import re
from sys_sec_artifacts_results_scrape import get_ae_results

def extract_year_from_confname(conf_year_str):
    """Extract year from conference name like 'osdi2024' -> 2024."""
    match = re.search(r'(\d{4})$', conf_year_str)
    if match:
        return int(match.group(1))
    return None

# Get all artifacts (from both systems and security)
sys_results = get_ae_results(r'.*20[12][0-9]', 'sys')
sec_results = get_ae_results(r'.*20[12][0-9]', 'sec')
all_results = {**sys_results, **sec_results}

# Count unique conferences per year
confs_by_year = {}
for conf_year in all_results.keys():
    year = extract_year_from_confname(conf_year)
    if year:
        if year not in confs_by_year:
            confs_by_year[year] = set()
        confs_by_year[year].add(conf_year)

# Print summary
for year in sorted(confs_by_year.keys()):
    count = len(confs_by_year[year])
    print(f"{year}: {count} conferences")
    print(f"  {', '.join(sorted(confs_by_year[year]))}")
