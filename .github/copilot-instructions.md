# ReproDB Pipeline — Copilot Instructions

## Data Schema Awareness

All JSON/YAML data structures produced by this pipeline are formally documented in
**[reprodb/data-schemas](https://github.com/reprodb/data-schemas)**.

When modifying any generator in `src/generators/`, check whether the change affects
the output schema (adding/removing/renaming fields, changing types, changing nesting).
If it does, **update the corresponding Pydantic model** in `src/models/`.
JSON Schema files in `data-schemas` are auto-generated from these models via
`.github/workflows/export-schemas.yml` (runs on push when `src/models/` changes).

### Schema workflow

1. Edit the generator in `src/generators/`.
2. Update the Pydantic model in `src/models/`.
3. Commit — CI auto-exports updated `.schema.json` files to `data-schemas`.

To export locally: `python -m src.models.export_schemas --output_dir ../data-schemas/schemas`

### When renaming or removing model fields

Renaming or removing a field in `src/models/` is a **breaking change** that requires
a coordinated update across multiple repos. Bump the **minor** version (pre-1.0) or
**major** version (post-1.0) in `pyproject.toml` and update all of these:

1. **Generator** (`src/generators/`) — produce the new field name.
2. **Pydantic model** (`src/models/`) — rename the field.
3. **Tests** (`tests/`) — update assertions, fixtures, and snapshot JSON.
4. **Invariants** (`src/invariants.py`) — update any field-name references.
5. **Snapshot** (`src/snapshot.py`) — update `_MONOTONIC_SUMS` and numeric field lists.
6. **JSON schemas** (`data-schemas/schemas/`) — auto-exported by CI, but verify locally.
7. **Website JS** (`reprodb.github.io/_includes/`) — update column `key:` values and
   dot-property access (e.g. `d.old_name` → `d.new_name`).
8. **Website data** (`reprodb.github.io/assets/data/` and `_data/`) — regenerate via
   pipeline or bulk-rename; these are pipeline output consumed by the site.

### Backward-compatible JSON reading (legacy field migration)

The pipeline must read its own historical output (e.g. `repo_stats_history.json`,
`ae_members.json`) which may use older field names or formats. All migration logic
lives in the **Pydantic model layer**, not in generators.

**Pattern — `model_validator(mode="before")`:**

```python
@model_validator(mode="before")
@classmethod
def _migrate_legacy_fields(cls, data):
    if not isinstance(data, dict):
        return data
    # Rename old field → new field; always pop old to satisfy extra="forbid"
    if "old_name" in data:
        if "new_name" not in data:
            data["new_name"] = data["old_name"]
        data.pop("old_name")
    return data
```

**Rules:**

1. **Add migration to the model**, not the generator. See `RepoStatsEntry._migrate_legacy_fields`
   and `AEMember._coerce_conferences` for examples.
2. **Always pop the old key** — models use `extra="forbid"`, so leftover keys cause errors.
3. **New fields take precedence** — when both old and new keys exist, keep the new value.
4. **Add tests** in `tests/models/test_migration.py` for every migration path.
5. Use `load_validated_json(path, Model)` from `src/utils/io` to load + validate in one call.
   It falls back to raw data on validation failure (graceful degradation).
6. Use `resolve_data_path(data_dir, filename)` from `src/utils/io` for the
   `_build/` → `assets/data/` path fallback instead of inline `os.path.exists` checks.

### Pydantic model mapping

| Generator | Pydantic model (`src/models/`) |
|-----------|-------------------------------|
| `generate_statistics.py` | `summary.py`, `artifacts_by_conference.py`, `artifacts_by_year.py`, `artifacts.py` |
| `generate_repo_stats.py` | `repo_stats.py` (both `RepoStatsEntry` and `RepoStatsSummary`) |
| `generate_combined_rankings.py` | `combined_rankings.py` |
| `generate_institution_rankings.py` | `institution_rankings.py` |
| `generate_author_stats.py` | `author_stats.py`, `paper_index.py` |
| `generate_search_data.py` | `search_data.py` |
| `generate_author_index.py` | `author_index.py` |

### Field naming conventions

New model fields **must** follow these suffixes so names are self-describing:

| Suffix | Meaning | Example |
|--------|---------|---------|
| `_count` | Count of discrete items | `artifact_count`, `author_count` |
| `_pct` | Percentage (0–100) | `artifact_pct`, `repro_pct` |
| `_score` | Computed ranking/weighting value | `combined_score`, `ae_score` |
| `_rate` | *(deprecated — use `_pct`)* | — |
| `total_` | Sum across a collection | `total_papers`, `total_artifacts` |
| `avg_` | Arithmetic mean | `avg_score` |
| `max_` / `min_` | Extremes | `max_stars` |
| `badges_` | Badge-type count | `badges_functional` |
| `github_` | Single-repo raw GitHub API value | `github_repos` |

### Validation

After running the pipeline locally, validate output against schemas:

```bash
cd ../data-schemas
.venv/bin/python -c "
import json, jsonschema, pathlib
schema = json.load(open('schemas/artifacts.schema.json'))
data = json.load(open('../reprodb-pipeline-results/output/artifacts.json'))
jsonschema.validate(data, schema)
print('OK')
"
```

## DBLP Data Access

**Do NOT use the DBLP HTTP API.** Always use the local DBLP XML dump (`data/dblp/dblp.xml.gz`).
The XML file is downloaded by `src/utils/download_dblp.py` and parsed by `src/utils/dblp_extract.py`.
The API has strict rate limits and is unreliable for bulk queries. All author/paper
lookups must go through the XML file.

## Module CLI Requirements

Every module in `src/generators/` and `src/scrapers/` **must** be runnable both as:

1. **CLI** via `python -m src.generators.<module_name>` with `argparse` arguments.
2. **Importable function** that can be called from other Python code.

Use an `if __name__ == "__main__":` block with `argparse` for CLI, and expose the
core logic as a function (e.g., `def main(...)` or `def run(...)`).

## Monthly Pipeline Integration

Any new or modified generator **must** be added to the monthly CI pipeline in
`.github/workflows/update-stats.yml`. When creating a new generator:

1. Add a step in `update-stats.yml` following the existing pattern (see current steps).
2. Place it in the correct order relative to dependencies (e.g., after data it reads is generated).
3. Use `--data_dir ../website` or `--output_dir ../website` consistently.
4. If the step can fail gracefully, append `|| echo "⚠️ <step> skipped"`.
5. Add the corresponding schema validation entry in the "Validate output against JSON schemas" step.

## Web Scraping & `SKIP_USENIX_SCRAPE`

The pipeline scrapes committee data from external websites (USENIX, CHES, PETS, ACSAC).
In CI, the env var `SKIP_USENIX_SCRAPE=1` is set because these sites block GitHub
Actions IPs (Cloudflare). When set, both `generate_statistics.py` and
`get_alternative_committees()` skip live scraping and fall back to cached data in
`data/local_committees.yaml`.

**When adding a new conference year:**
1. Run the scraper locally to fetch committee data (USENIX scraping works from dev machines).
2. Append the results to `data/local_committees.yaml` so CI can use them offline.
3. Update `USENIX_KNOWN_YEARS` in `src/scrapers/scrape_committee_web.py` if needed.

## CI Secrets

All cross-repo workflows use `secrets.CROSS_REPO_TOKEN` (a PAT with push access to
sibling repos under the `reprodb` org). Do **not** create separate tokens
per workflow. Workflows that use it:

- `update-stats.yml` — pushes to `reprodb.github.io` and `reprodb-pipeline-results`
- `dblp-author-analysis.yml` — pushes to `reprodb.github.io`
- `export-schemas.yml` — pushes to `data-schemas`

## Caching Conventions

- All HTTP calls must use `_session_with_retries()` from `src/scrapers/repo_utils.py`.
- Cache responses in `.cache/` with appropriate TTL: 30 days for stable data, 7 days for URL liveness (negative), 90 days for URL existence (positive).
- Use `_read_cache()` / `_write_cache()` helpers for consistency.
- DBLP extracted data lives in `.cache/dblp_extracted/` and is invalidated by mtime of the XML file.
- Never commit `.cache/` — it is gitignored.

## Shared Utilities — Do Not Duplicate

The following utilities exist in `src/utils/` and **must** be reused — never create
local copies in generators, scrapers, or enrichers:

| Utility | Module | Purpose |
|---------|--------|---------|
| `normalize_name(name)` | `src/utils/conference.py` | Canonicalize author names for matching |
| `normalize_title(title)` | `src/utils/conference.py` | Canonicalize paper titles for deduplication |
| `clean_member_name(name)` | `src/utils/conference.py` | Strip affiliations/roles from committee names |
| `PLACEHOLDER_NAMES` | `src/utils/conference.py` | Names to filter out ("TBD", "TBA", etc.) |
| `conf_area(conf)` | `src/utils/conference.py` | Map conference name → area ("systems"/"security") |
| `_normalize_affiliation(name)` | `src/generators/generate_combined_rankings.py` | YAML-driven affiliation canonicalization (uses `data/affiliation_rules.yaml`) |
| `_read_cache()` / `_write_cache()` | `src/utils/cache.py` | Atomic disk cache with TTL |
| `setup_logging()` | `src/utils/logging_config.py` | Centralized log configuration |

When adding normalization for a new entity, add it to the shared module — not inline.

## Logging

- Every module must use `logger = logging.getLogger(__name__)` at module level.
- Call `setup_logging()` from `src/utils/logging_config.py` in every `__main__` block.
- **Never use `print()`** — ruff rule T20 enforces this. Use `logger.info()` instead.
- Do not pass `flush=True` to logger methods — it is silently ignored.
- Use appropriate levels: `DEBUG` for verbose detail, `INFO` for progress,
  `WARNING` for recoverable issues, `ERROR` for actual failures only.
- Include identifying context in log messages (author name, conference, URL, count).

## Linting & Type Checking

- **ruff** is configured in `pyproject.toml` with `line-length = 120` and rules:
  `E, W, F, I, UP, B, SIM, PIE, RET, LOG, T20`.
- **mypy** is configured with `python_version = "3.10"` and `explicit_package_bases = true`.
- **pre-commit** hooks run ruff lint + format automatically on commit.
- Run `ruff check src/` and `ruff format --check src/` before committing.

### Pre-push gate

**Before every `git push`**, run the full lint suite **and** the test suite, and fix any errors:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy --follow-imports=silent src/models/ src/utils/
pytest tests/ -x -q
```

Do **not** push if any of these commands fail. Fix the issues first, then push.

## Secrets & Credentials

- **Never commit API keys, tokens, or credentials** to the repository.
- Use environment variables (`os.environ.get("KEY")`) with graceful fallback when missing.
- `.env.local` is gitignored — never track it. If it appears in git history, the key
  must be revoked immediately.
- CI secrets use `secrets.CROSS_REPO_TOKEN` (see CI Secrets section).

## Error Handling

- Network errors: retry with exponential backoff (reuse `_session_with_retries()`).
- Missing optional input files: log a warning with `logger.warning()` and skip gracefully.
- Output directories: always create with `os.makedirs(path, exist_ok=True)`.
- Pipeline steps that can fail: use `|| echo "⚠️ <step> skipped"` in bash; in Python, catch exceptions and continue.
- Wrap `.json()` and `json.load()` calls in `try/except (ValueError, JSONDecodeError)`.
- In enricher loops over authors/artifacts, isolate errors per item — one failure must
  not stop the entire batch.

## Testing

All new or modified logic **must** have corresponding tests in `tests/`.

### Test file layout

| Source module | Test file |
|---------------|-----------|
| `src/generators/generate_<name>.py` | `tests/test_<name>.py` |
| `src/enrichers/enrich_<name>.py` | `tests/test_enricher_<name>.py` |
| `src/utils/<name>.py` | `tests/test_<name>.py` |

### How to write tests

1. **Unit tests** for pure functions (normalization, scoring, ranking, URL parsing).
   Import the function directly; no fixtures or network needed.
2. **Fixture-based tests** for generators that read/write files. Use the `tmp_website`
   fixture from `conftest.py` (provides `_data/` + `assets/data/` directories).
   Use `sample_authors` / `sample_index` fixtures for author data.
3. **Integration tests** for multi-step workflows. Mark with `@pytest.mark.integration`.
4. **No network** — tests must never make HTTP calls. Mock or use cached fixture data.

### Conventions

- Use `pytest` (not `unittest`). Group related tests in classes (`class TestFeatureName:`).
- Use descriptive names: `test_deduplicates_coauthored_papers`, not `test_1`.
- For file I/O tests, use `tmp_path` (pytest built-in) or `tmp_website` (our fixture).
- Helper functions for writing/reading fixture data: `write_json()` / `read_json()` in `conftest.py`.
- Mark slow tests with `@pytest.mark.slow`.

### Running tests

```bash
# All tests
pytest tests/ -v

# Specific file
pytest tests/test_paper_index.py -v

# Skip slow tests (default in CI)
pytest tests/ -m "not slow"

# Integration only
pytest tests/ -m integration
```

### CI workflow

Tests run automatically on push/PR to `main` via `.github/workflows/tests.yml`
(Python 3.10 + 3.12). CI uses `requirements-ci.txt` (minimal deps, no heavy
packages). When adding a new import to test code, ensure it's in `requirements-ci.txt`.

## Naming Conventions

- Generators: `generate_<descriptive_noun>.py`
- Scrapers: `<platform>_scrape.py`
- Enrichers: `enrich_<what>.py`
- CLI arguments: `--snake_case` with sensible defaults
- Conference names: always uppercase (`OSDI`, `ACSAC`, `USENIXSEC`)
- Years: integers in Python, strings only when used as YAML/JSON keys
- All functions use snake_case; all JSON keys use snake_case
- Return `None` for single-value lookups that may fail; return empty `list`/`dict`
  for collection-producing functions
