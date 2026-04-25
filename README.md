# ReproDB Pipeline

[![Tests](https://github.com/reprodb/reprodb-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/reprodb/reprodb-pipeline/actions/workflows/tests.yml)
[![Docs](https://github.com/reprodb/reprodb-pipeline/actions/workflows/deploy-docs.yml/badge.svg)](https://reprodb.github.io/reprodb-pipeline/)
[![Schemas](https://github.com/reprodb/reprodb-pipeline/actions/workflows/export-schemas.yml/badge.svg)](https://reprodb.github.io/data-schemas/)

Scrapes artifact evaluation data from [sysartifacts](https://sysartifacts.github.io), [secartifacts](https://secartifacts.github.io), and [USENIX](https://www.usenix.org) conference pages, then generates statistics, visualizations, and author rankings for [reprodb.github.io](https://reprodb.github.io).

**[Documentation](https://reprodb.github.io/reprodb-pipeline/)** · **[Data Schemas](https://reprodb.github.io/data-schemas/)**

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
./run_pipeline.sh --output_dir ../reprodb.github.io  # default
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
| `src/generators/generate_author_index.py` | Author name → ID lookup index |
| `src/generators/generate_paper_index.py` | Paper title → artifact ID lookup index |
| `src/generators/generate_paper_citations.py` | Paper-level citation statistics |
| `src/generators/generate_search_data.py` | Merged data for website full-text search |
| `src/generators/generate_ranking_history.py` | Historical ranking snapshots |
| `src/generators/generate_artifact_availability.py` | Artifact URL availability checks |
| `src/generators/analyze_retention.py` | Artifact retention analysis over time |
| `src/generators/collect_repo_detail.py` | Detailed per-repo metadata collection |
| `src/generators/export_artifact_citations.py` | Exports artifact citation data |
| `src/generators/verify_artifact_citations.py` | Verifies artifact citation accuracy |

### Scrapers (data collection)

| Script | Purpose |
|--------|---------|
| `src/scrapers/acm_scrape.py` | Scrapes ACM Digital Library |
| `src/scrapers/usenix_scrape.py` | Scrapes USENIX conference pages for badges |
| `src/scrapers/acsac_scrape.py` | Scrapes ACSAC artifact evaluation pages |
| `src/scrapers/generate_results.py` | Generates results.md for sysartifacts and secartifacts sites |
| `src/scrapers/repo_utils.py` | GitHub API fetching with caching |
| `src/scrapers/parse_results_md.py` | Parses artifact YAML front-matter from repos |
| `src/scrapers/parse_committee_md.py` | Committee member scraping from repos |
| `src/scrapers/scrape_committee_web.py` | Committee scraping from conference websites |

### Enrichers (data enhancement)

| Script | Purpose |
|--------|---------|
| `src/enrichers/enrich_affiliations_ae_members.py` | AE committee member affiliation enrichment |
| `src/enrichers/enrich_affiliations_csrankings.py` | CSRankings-based enrichment |
| `src/enrichers/enrich_affiliations_openalex.py` | OpenAlex-based enrichment |

### Utilities

| Script | Purpose |
|--------|---------|
| `src/utils/dblp_extract.py` | Pre-extracts DBLP XML into JSON lookup files (papers, affiliations) |
| `src/utils/collect_artifact_stats.py` | Artifact stats collector |
| `src/utils/committee_statistics.py` | Committee analysis utilities |
| `src/utils/test_artifact_repositories.py` | Repository accessibility testing |
| `src/utils/conference.py` | Conference name normalization, area mapping, constants |
| `src/utils/cache.py` | Atomic read/write cache helpers |
| `src/utils/logging_config.py` | Centralized logging setup |
| `src/utils/http.py` | HTTP request helpers with retry/caching |
| `src/utils/io.py` | File I/O utilities |
| `src/utils/author_index.py` | Author index lookup utilities |

### Models (Pydantic data models)

| Module | Purpose |
|--------|---------|
| `src/models/artifacts.py` | Core artifact record schema |
| `src/models/artifacts_by_conference.py` | Per-conference badge breakdown schema |
| `src/models/artifacts_by_year.py` | Year-over-year artifact counts schema |
| `src/models/author_stats.py` | Per-author statistics schema |
| `src/models/author_index.py` | Author name → ID index schema |
| `src/models/combined_rankings.py` | Combined rankings schema |
| `src/models/institution_rankings.py` | Institution-level rankings schema |
| `src/models/paper_index.py` | Paper title → artifact ID index schema |
| `src/models/repo_stats.py` | Repository metrics schema |
| `src/models/search_data.py` | Full-text search data schema |
| `src/models/summary.py` | Site summary statistics schema |
| `src/models/export_schemas.py` | JSON Schema export from Pydantic models |

## Output

Statistics and data go to `_data/` and `assets/` in the output directory:

- `_data/summary.yml` — overall totals and per-area counts
- `_data/artifacts_by_conference.yml` — per-conference artifact counts and badges
- `_data/artifacts_by_year.yml` — yearly trends
- `_data/authors.yml`, `author_summary.yml` — top authors with rates
- `_data/systems_authors.yml`, `security_authors.yml` — per-area author rankings
- `_data/repo_stats.yml` — GitHub repository metadata
- `_data/participation_stats.yml` — AE participation rates and badge % of all papers
- `_data/committee_stats.yml` — AE committee statistics
- `_data/combined_summary.yml` — combined summary across all areas
- `_data/coverage.yml` — data coverage metrics
- `_data/navigation.yml` — site navigation structure
- `assets/data/artifacts.json`, `authors.json`, `summary.json` — JSON exports
- `assets/data/participation_stats.json` — participation stats (JSON)
- `assets/data/combined_rankings.json` — combined author rankings (JSON)
- `assets/data/institution_rankings.json` — institution rankings (JSON)
- `assets/data/search_data.json` — full-text search index (JSON)
- `assets/data/author_profiles.json` — detailed author profiles (JSON)
- `assets/data/committee_stats.json` — committee statistics (JSON)
- `assets/charts/*.svg` — generated visualizations

## Repository Layout

```
reprodb-pipeline/
├── src/
│   ├── scrapers/          — Data collection (GitHub, ACM, USENIX, etc.)
│   ├── enrichers/         — Data enhancement (affiliations, repositories)
│   ├── generators/        — Output generation (statistics, visualizations)
│   ├── models/            — Pydantic data models and JSON Schema export
│   └── utils/             — Utilities and helpers
├── scripts/               — Shell scripts (downloader)
├── data/
│   ├── dblp/              — DBLP XML database (downloaded, ~3GB)
│   ├── affiliation_rules.yaml  — Affiliation normalization rules
│   ├── local_committees.yaml   — Cached committee data for offline use
│   ├── name_aliases.yaml       — Author name alias mappings
│   └── university_country_overrides.yaml — Country override mappings
├── docs/                  — MkDocs documentation source
├── logs/                  — Pipeline logs and argument history
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

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.