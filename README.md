# Research Artifacts Analysis

[![Tests](https://github.com/researchartifacts/artifact_analysis/actions/workflows/tests.yml/badge.svg)](https://github.com/researchartifacts/artifact_analysis/actions/workflows/tests.yml)
[![Docs](https://github.com/researchartifacts/artifact_analysis/actions/workflows/deploy-docs.yml/badge.svg)](https://researchartifacts.github.io/artifact_analysis/)
[![Schemas](https://github.com/researchartifacts/artifact_analysis/actions/workflows/export-schemas.yml/badge.svg)](https://researchartifacts.github.io/data-schemas/)

Scrapes artifact evaluation data from [sysartifacts](https://sysartifacts.github.io), [secartifacts](https://secartifacts.github.io), and [USENIX](https://www.usenix.org) conference pages, then generates statistics, visualizations, and author rankings for [researchartifacts.github.io](https://researchartifacts.github.io).

**[Documentation](https://researchartifacts.github.io/artifact_analysis/)** · **[Data Schemas](https://researchartifacts.github.io/data-schemas/)**

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
5. Matches authors via DBLP and computes author metrics (skipped if `data/dblp/dblp.xml.gz` is absent)
6. Splits author data into per-area (systems/security) files

### Options

```bash
./run_pipeline.sh --output_dir ../researchartifacts.github.io  # default
./run_pipeline.sh --conf_regex 'osdi202[3-4]'                  # filter conferences
./run_pipeline.sh --http_proxy http://proxy:8080                # use proxy
```

## Scripts

Scripts are organized into functional categories:

### Generators (statistics, visualizations, output)

| Script | Purpose |
|--------|---------|
| `src/generators/generate_statistics.py` | Scrapes sysartifacts + secartifacts + USENIX, writes YAML/JSON |
| `src/generators/generate_repo_stats.py` | Collects GitHub repo metadata (stars, forks, languages) |
| `src/generators/generate_participation_stats.py` | AE participation rates and badge % of all papers (DBLP) |
| `src/generators/generate_artifact_citations.py` | Generates artifact citation statistics (OpenAlex) |
| `src/generators/generate_visualizations.py` | Creates SVG charts (per-category, total, badges, trends) |
| `src/generators/generate_author_stats.py` | Ranks authors by artifact count via DBLP matching |
| `src/generators/generate_area_authors.py` | Splits author data into systems/security areas |
| `src/generators/generate_committee_stats.py` | Committee statistics and analysis |
| `src/generators/generate_combined_rankings.py` | Combined multi-source rankings |
| `src/generators/generate_institution_rankings.py` | Per-institution rankings |
| `src/generators/generate_author_profiles.py` | Detailed author profile data |
| `src/generators/generate_artifact_sources_table.py` | Artifact source tables |
| `src/generators/generate_artifact_sources_timeline.py` | Artifact source timelines |
| `src/generators/generate_cited_artifacts_list.py` | Lists of cited artifacts |

### Scrapers (data collection)

| Script | Purpose |
|--------|---------|
| `src/scrapers/acm_scrape.py` | Scrapes ACM Digital Library |
| `src/scrapers/usenix_scrape.py` | Scrapes USENIX conference pages for badges |
| `src/scrapers/generate_sysartifacts_results.py` | Generates sysartifacts-compatible results.md |
| `src/scrapers/sys_sec_scrape.py` | GitHub API fetching with caching |
| `src/scrapers/sys_sec_artifacts_results_scrape.py` | Parses artifact YAML front-matter |
| `src/scrapers/sys_sec_committee_scrape.py` | Committee member scraping |
| `src/scrapers/alternative_committee_scrape.py` | Alternative committee scraping |

### Enrichers (data enhancement)

| Script | Purpose |
|--------|---------|
| `src/enrichers/enrich_affiliations_dblp_incremental.py` | Incremental DBLP enrichment with caching |
| `src/enrichers/enrich_affiliations_csrankings.py` | CSRankings-based enrichment |
| `src/enrichers/enrich_affiliations_openalex.py` | OpenAlex-based enrichment |

### Utilities

| Script | Purpose |
|--------|---------|
| `src/utils/dblp_extract.py` | Pre-extracts DBLP XML into JSON lookup files (papers, affiliations) |
| `src/utils/collect_artifact_stats.py` | Artifact stats collector |
| `src/utils/committee_statistics.py` | Committee analysis utilities |
| `src/utils/test_artifact_repositories.py` | Repository accessibility testing |

## Output

Statistics and data go to `_data/` and `assets/` in the output directory:

- `_data/summary.yml` — overall totals and per-area counts
- `_data/artifacts_by_conference.yml` — per-conference artifact counts and badges
- `_data/artifacts_by_year.yml` — yearly trends
- `_data/authors.yml`, `author_summary.yml` — top authors with rates
- `_data/systems_authors.yml`, `security_authors.yml` — per-area author rankings
- `_data/repo_stats.yml` — GitHub repository metadata
- `_data/participation_stats.yml` — AE participation rates and badge % of all papers
- `_data/navigation.yml` — site navigation structure
- `assets/data/artifacts.json`, `authors.json`, `summary.json` — JSON exports
- `assets/data/participation_stats.json` — participation stats (JSON)
- `assets/charts/*.svg` — generated visualizations

## Repository Layout

```
artifact_analysis/
├── src/
│   ├── scrapers/          — Data collection (GitHub, ACM, USENIX, etc.)
│   ├── enrichers/         — Data enhancement (affiliations, repositories)
│   ├── generators/        — Output generation (statistics, visualizations)
│   └── utils/             — Utilities and helpers
├── scripts/               — Shell scripts (downloader)
├── data/
│   ├── dblp/              — DBLP XML database (downloaded, ~3GB)
│   └── inputs/            — Input CSV files (affiliations, etc.)
├── logs/                  — Pipeline logs and argument history
├── config/                — Configuration (cache version, etc.)
├── run_pipeline.sh        — Main orchestration script
├── save_results.sh        — Results snapshot and push script
└── .github/workflows/     — CI/CD automation
```

### src/ organization by functionality

- **scrapers/** — Data collection from external sources (GitHub, conferences, APIs)
- **enrichers/** — Data enhancement and augmentation (affiliations, repositories)
- **generators/** — Output generation (statistics tables, visualizations, profiles)
- **utils/** — Parsing, testing, analysis utilities

## Caching

- **GitHub responses** are cached in `.cache/` with a 1-hour TTL
- **DBLP XML** freshness is checked via HTTP `Last-Modified` header at each run
- **DBLP extracted data** is cached in `.cache/dblp_extracted/` and refreshed
  whenever the XML file changes

## DBLP Data Policy

All DBLP data is sourced from the **local XML dump** (`data/dblp/dblp.xml.gz`)
downloaded by `scripts/download_dblp.sh`.  The pipeline step `src/utils/dblp_extract.py`
parses the XML once and writes JSON lookup files that every downstream module
can load.

## Conferences Tracked

Conferences from sysartifacts/secartifacts are auto-discovered from their repositories.
USENIX conferences are configured in `generate_statistics.py` via the `USENIX_CONFERENCES` list.

**Systems (sysartifacts):** EuroSys, SOSP, SC (+ OSDI, ATC when present)
**Systems (USENIX direct):** FAST
**Security (secartifacts):** ACSAC, CHES, NDSS, PETS, USENIX Security
**Workshops:** WOOT, SysTEX

## Automation

A GitHub Actions workflow (`.github/workflows/update-stats.yml`) runs monthly. Requires a `WEBSITE_UPDATE_TOKEN` secret with `repo` scope. Can also be triggered manually from the Actions tab.