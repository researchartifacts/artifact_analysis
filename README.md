# Research Artifacts Analysis

Scrapes artifact evaluation data from [sysartifacts](https://sysartifacts.github.io), [secartifacts](https://secartifacts.github.io), and [USENIX](https://www.usenix.org) conference pages, then generates statistics, visualizations, and author rankings for [researchartifacts.github.io](https://researchartifacts.github.io).

## Quick Start

```bash
pip install -r requirements.txt
./run_pipeline.sh
```

The pipeline runs six steps:
1. Checks DBLP freshness and downloads if needed
2. Scrapes artifact data from sysartifacts, secartifacts, and USENIX conference pages
3. Generates repository statistics (stars, forks, languages)
4. Creates per-category and total SVG visualizations
5. Matches authors via DBLP and computes author metrics (skipped if `dblp.xml.gz` is absent)
6. Splits author data into per-area (systems/security) files

### Options

```bash
./run_pipeline.sh --output_dir ../researchartifacts.github.io  # default
./run_pipeline.sh --conf_regex 'osdi202[3-4]'                  # filter conferences
./run_pipeline.sh --http_proxy http://proxy:8080                # use proxy
```

## Scripts

### Pipeline scripts

| Script | Purpose |
|--------|---------|
| `run_pipeline.sh` | Orchestrates the full pipeline (6 steps) |
| `download_dblp.sh` | Downloads/refreshes DBLP XML (auto-checks Last-Modified) |
| `generate_statistics.py` | Scrapes sysartifacts + secartifacts + USENIX, writes YAML/JSON |
| `generate_repo_stats.py` | Collects GitHub repo metadata (stars, forks, languages) |
| `generate_visualizations.py` | Creates SVG charts (per-category, total, badges, trends) |
| `generate_author_stats.py` | Ranks authors by artifact count via DBLP matching, computes rates |
| `generate_area_authors.py` | Splits author data into systems and security area files |

### Standalone tools

| Script | Purpose |
|--------|---------|
| `usenix_scrape.py` | Scrapes USENIX conference pages for artifact badges (FAST, OSDI, ATC, etc.) |
| `generate_sysartifacts_results.py` | Generates sysartifacts-compatible `results.md` for any USENIX conference |

### Supporting modules

| Module | Purpose |
|--------|---------|
| `sys_sec_scrape.py` | GitHub API fetching with caching |
| `sys_sec_scrape_no_api.py` | GitHub fetching without API (raw HTML) |
| `sys_sec_artifacts_results_scrape.py` | YAML front-matter parsing for artifact results |
| `parse_dlbp.py` | DBLP XML parsing |

### Legacy scripts (from upstream)

| Script | Purpose |
|--------|---------|
| `collect_artifact_stats.py` | Original artifact stats collector |
| `committee_statistics.py` | Committee membership analysis |
| `eurosys_plot.py` | EuroSys-specific plotting |
| `sys_sec_committee_scrape.py` | Committee scraping |
| `test_artifact_repositories.py` | Tests artifact repository accessibility |

## Output

Statistics and data go to `_data/` and `assets/` in the output directory:

- `_data/summary.yml` — overall totals and per-area counts
- `_data/artifacts_by_conference.yml` — per-conference artifact counts and badges
- `_data/artifacts_by_year.yml` — yearly trends
- `_data/authors.yml`, `author_summary.yml` — top authors with rates
- `_data/systems_authors.yml`, `security_authors.yml` — per-area author rankings
- `_data/repo_stats.yml` — GitHub repository metadata
- `_data/navigation.yml` — site navigation structure
- `assets/data/artifacts.json`, `authors.json`, `summary.json` — JSON exports
- `assets/charts/*.svg` — generated visualizations

## Caching

- **GitHub responses** are cached in `.cache/` with a 1-hour TTL
- **DBLP XML** freshness is checked via HTTP `Last-Modified` header at each run

## Conferences Tracked

Conferences from sysartifacts/secartifacts are auto-discovered from their repositories.
USENIX conferences are configured in `generate_statistics.py` via the `USENIX_CONFERENCES` list.

**Systems (sysartifacts):** EuroSys, SOSP, SC (+ OSDI, ATC when present)
**Systems (USENIX direct):** FAST
**Security (secartifacts):** ACSAC, CHES, NDSS, PETS, USENIX Security
**Workshops:** WOOT, SysTEX

## Automation

A GitHub Actions workflow (`.github/workflows/update-stats.yml`) runs monthly. Requires a `WEBSITE_UPDATE_TOKEN` secret with `repo` scope. Can also be triggered manually from the Actions tab.

## License

MIT
