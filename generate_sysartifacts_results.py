#!/usr/bin/env python3
"""
Generate sysartifacts-compatible results.md files for USENIX conferences.

This script scrapes USENIX technical-sessions pages to collect paper
titles, artifact evaluation badges, and paper PDF URLs, then produces
results.md files in the format expected by sysartifacts.github.io.

Supported conferences include any that follow the standard USENIX
technical-sessions layout (e.g. FAST, OSDI, ATC/NSDI).

Usage:
  # Generate results for FAST 2024 and 2025
  python generate_sysartifacts_results.py --conference fast --years 2024,2025 --output_dir ./out

  # Generate results for OSDI 2024
  python generate_sysartifacts_results.py --conference osdi --years 2024 --output_dir ./out

  # Preview without writing (print to stdout)
  python generate_sysartifacts_results.py --conference fast --years 2025 --dry-run

  # Custom directory prefix (e.g. "usenixatc" instead of "atc")
  python generate_sysartifacts_results.py --conference atc --years 2024 --dir-prefix usenixatc

Requirements:
  pip install requests beautifulsoup4 pyyaml lxml

The generated results.md files can be dropped into the sysartifacts repo:
  _conferences/<conf><YY>/results.md
"""

import argparse
import os
import sys

# Add parent directory to path so we can import usenix_scrape
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usenix_scrape import scrape_conference_year


def generate_results_md(conference, year, papers_with_badges):
    """
    Generate a sysartifacts-compatible results.md for a USENIX conference year.

    Args:
        conference: Conference short name (e.g. 'fast', 'osdi', 'atc')
        year: Conference year (int)
        papers_with_badges: List of dicts with keys 'title', 'badges', 'paper_url'
                            (as returned by usenix_scrape.scrape_conference_year)

    Returns:
        String content of the results.md file.
    """
    # Count badges
    n_available = sum(1 for p in papers_with_badges if 'available' in p['badges'])
    n_functional = sum(1 for p in papers_with_badges if 'functional' in p['badges'])
    n_reproduced = sum(1 for p in papers_with_badges if 'reproduced' in p['badges'])

    # Build YAML front-matter artifacts list
    artifact_lines = []
    for p in papers_with_badges:
        # Escape YAML special characters in title
        title = p['title'].replace('"', '\\"')
        badges = ','.join(p['badges'])
        paper_url = p.get('paper_url', '')

        artifact_lines.append(f'  - title: "{title}"')
        if paper_url:
            artifact_lines.append(f'    paper_url: "{paper_url}"')
        artifact_lines.append(f'    badges: "{badges}"')
        artifact_lines.append('')

    artifacts_yaml = '\n'.join(artifact_lines).rstrip()

    md = f"""---
title: Results
order: 50
available_img: "usenix_available.svg"
available_name: "Artifacts Available"
functional_img: "usenix_functional.svg"
functional_name: "Artifacts Evaluated - Functional"
reproduced_img: "usenix_reproduced.svg"
reproduced_name: "Results Reproduced"

artifacts:
{artifacts_yaml}
---

**Evaluation Results**:

* {n_available} Artifacts Available
* {n_functional} Artifacts Functional
* {n_reproduced} Results Reproduced

<table>
  <thead>
    <tr>
      <th>Paper title</th>
      <th>Avail.</th>
      <th>Funct.</th>
      <th>Repro.</th>
    </tr>
  </thead>
  <tbody>
  {{% for artifact in page.artifacts %}}
    <tr>
      <td>
        {{% if artifact.paper_url %}}
          <a href="{{{{artifact.paper_url}}}}" target="_blank">{{{{artifact.title}}}}</a>
        {{% else %}}
          {{{{ artifact.title }}}}
        {{% endif %}}
      </td>
      <td>
        {{% if artifact.badges contains "available" %}}
          <img src="{{{{ site.baseurl }}}}/images/{{{{ page.available_img }}}}" alt="{{{{ page.available_name }}}}" width="50px">
        {{% endif %}}
      </td>
      <td>
        {{% if artifact.badges contains "functional" %}}
          <img src="{{{{ site.baseurl }}}}/images/{{{{ page.functional_img }}}}" alt="{{{{ page.functional_name }}}}" width="50px">
        {{% endif %}}
      </td>
      <td>
        {{% if artifact.badges contains "reproduced" %}}
          <img src="{{{{ site.baseurl }}}}/images/{{{{ page.reproduced_img }}}}" alt="{{{{ page.reproduced_name }}}}" width="50px">
        {{% endif %}}
      </td>
    </tr>
  {{% endfor %}}
  </tbody>
</table>
"""
    return md


def main():
    parser = argparse.ArgumentParser(
        description='Generate sysartifacts results.md for USENIX conferences'
    )
    parser.add_argument(
        '--conference', '-c', type=str, required=True,
        help='USENIX conference short name (e.g. fast, osdi, atc, nsdi)'
    )
    parser.add_argument(
        '--years', '-y', type=str, default='2024,2025',
        help='Comma-separated conference years (default: 2024,2025)'
    )
    parser.add_argument(
        '--output_dir', '-o', type=str, default=None,
        help='Output directory (results written to <output_dir>/<conf><YY>/results.md). '
             'If not specified and --dry-run is not set, writes to current directory.'
    )
    parser.add_argument(
        '--dir-prefix', type=str, default=None,
        help='Override directory prefix (default: conference name). '
             'E.g. --dir-prefix usenixatc to get usenixatc24/ instead of atc24/'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print generated results to stdout instead of writing files'
    )
    parser.add_argument(
        '--max-workers', type=int, default=4,
        help='Max parallel HTTP requests (default: 4)'
    )
    parser.add_argument(
        '--delay', type=float, default=0.5,
        help='Delay between requests in seconds (default: 0.5)'
    )
    args = parser.parse_args()

    conference = args.conference.lower()
    dir_prefix = (args.dir_prefix or conference).lower()
    years = [int(y.strip()) for y in args.years.split(',')]

    for year in years:
        yy = str(year)[2:]
        conf_label = f"{conference.upper()} {year}"
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"Scraping {conf_label} from USENIX...", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        all_papers = scrape_conference_year(
            conference, year,
            max_workers=args.max_workers,
            delay=args.delay
        )

        # Filter to papers with badges only
        papers_with_badges = [p for p in all_papers if p.get('badges')]

        if not papers_with_badges:
            print(f"WARNING: No papers with badges found for {conf_label}", file=sys.stderr)
            continue

        print(f"\n{conf_label}: {len(papers_with_badges)} papers with badges "
              f"(of {len(all_papers)} total)", file=sys.stderr)

        # Generate the results.md content
        content = generate_results_md(conference, year, papers_with_badges)

        if args.dry_run:
            print(f"\n--- {dir_prefix}{yy}/results.md ---")
            print(content)
        else:
            out_dir = args.output_dir or '.'
            conf_dir = os.path.join(out_dir, f'{dir_prefix}{yy}')
            os.makedirs(conf_dir, exist_ok=True)
            out_path = os.path.join(conf_dir, 'results.md')
            with open(out_path, 'w') as f:
                f.write(content)
            print(f"Written: {out_path}", file=sys.stderr)

    print("\nDone!", file=sys.stderr)


if __name__ == '__main__':
    main()
