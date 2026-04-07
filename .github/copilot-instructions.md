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
The XML file is downloaded by `scripts/download_dblp.sh` and parsed by `src/utils/dblp_extract.py`.
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

## CI Secrets

All cross-repo workflows use `secrets.CROSS_REPO_TOKEN` (a PAT with push access to
sibling repos under the `reprodb` org). Do **not** create separate tokens
per workflow. Workflows that use it:

- `update-stats.yml` — pushes to `reprodb.github.io` and `reprodb-pipeline-results`
- `dblp-author-analysis.yml` — pushes to `reprodb.github.io`
- `export-schemas.yml` — pushes to `data-schemas`

## Caching Conventions

- All HTTP calls must use `_session_with_retries()` from `src/scrapers/sys_sec_scrape.py`.
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
