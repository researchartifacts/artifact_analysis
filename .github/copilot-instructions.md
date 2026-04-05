# Artifact Analysis — Copilot Instructions

## Data Schema Awareness

All JSON/YAML data structures produced by this pipeline are formally documented in
**[researchartifacts/data-schemas](https://github.com/researchartifacts/data-schemas)**.

When modifying any generator in `src/generators/`, check whether the change affects
the output schema (adding/removing/renaming fields, changing types, changing nesting).
If it does, **also update the corresponding schema file** in the sibling
`../data-schemas/schemas/` directory.

### Schema mapping

| Generator | Schema file(s) |
|-----------|---------------|
| `generate_statistics.py` | `summary.schema.json`, `artifacts_by_conference.schema.json`, `artifacts_by_year.schema.json`, `artifacts.schema.json` |
| `generate_repo_stats.py` | `repo_stats.schema.json`, `repo_stats_summary.schema.json` |
| `generate_combined_rankings.py` | `combined_rankings.schema.json` |
| `generate_institution_rankings.py` | `institution_rankings.schema.json` |
| `generate_author_stats.py` | `author_stats.schema.json`, `paper_index.schema.json` |
| `generate_search_data.py` | `search_data.schema.json` |

### How to update schemas

1. Edit the generator in `src/generators/`.
2. Open the corresponding `.schema.json` file in `../data-schemas/schemas/`.
3. Update `properties`, `required`, `$defs`, or `description` to match the new output.
4. Run `cd ../data-schemas && .venv/bin/python -c "import json,jsonschema; s=json.load(open('schemas/FILE.schema.json')); jsonschema.Draft202012Validator.check_schema(s); print('OK')"` to verify.
5. Commit changes to **both** repos.

### Validation

After running the pipeline locally, validate output against schemas:

```bash
cd ../data-schemas
.venv/bin/python -c "
import json, jsonschema, pathlib
schema = json.load(open('schemas/artifacts.schema.json'))
data = json.load(open('../artifact_analysis_results/output/artifacts.json'))
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

## Caching Conventions

- All HTTP calls must use `_session_with_retries()` from `src/scrapers/sys_sec_scrape.py`.
- Cache responses in `.cache/` with appropriate TTL: 30 days for stable data, 7 days for URL liveness (negative), 90 days for URL existence (positive).
- Use `_read_cache()` / `_write_cache()` helpers for consistency.
- DBLP extracted data lives in `.cache/dblp_extracted/` and is invalidated by mtime of the XML file.
- Never commit `.cache/` — it is gitignored.

## Error Handling

- Network errors: retry with exponential backoff (reuse `_session_with_retries()`).
- Missing optional input files: warn with `print("⚠️ ...")` and skip gracefully.
- Output directories: always create with `os.makedirs(path, exist_ok=True)`.
- Pipeline steps that can fail: use `|| echo "⚠️ <step> skipped"` in bash; in Python, catch exceptions and continue.

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
