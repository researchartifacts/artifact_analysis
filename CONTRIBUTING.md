# Contributing to ReproDB Pipeline

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Pre-push Checklist

**Run all three before every push:**

```bash
ruff check src/ tests/           # Lint errors
ruff format --check src/ tests/  # Formatting (CI enforces this)
pytest tests/ -x -q              # Tests
```

CI runs both `ruff check` **and** `ruff format --check`. Missing either will fail
the lint job. Use `ruff format src/ tests/` to auto-fix formatting.

## Adding New Conference Data

When adding a new conference year that requires web scraping:

1. Run the scraper locally — external sites (USENIX, CHES, PETS, ACSAC) block GitHub
   Actions IPs, so CI cannot fetch live data.
2. Append the scraped committee data to `data/local_committees.yaml`.
3. Update `USENIX_KNOWN_YEARS` in `src/scrapers/scrape_committee_web.py` if needed.
4. CI uses `SKIP_USENIX_SCRAPE=1` to skip live scraping and read from the YAML fallback.

## Code Style

- **ruff** enforces formatting and linting (config in `pyproject.toml`, `line-length = 120`).
- Use `logger.info()` instead of `print()` (ruff rule T20).
- Use `logging.getLogger(__name__)` at module level.

## Tests

- All new or modified logic needs tests in `tests/`.
- Tests must not make HTTP calls — mock or use fixture data.
- Run with `pytest tests/ -v`.

## CI Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `tests.yml` | Push/PR to main | Lint + tests (Python 3.10 & 3.12) |
| `update-stats.yml` | Monthly / manual | Full pipeline run, pushes to website |
| `dblp-author-analysis.yml` | Monthly / manual | DBLP author analysis |
| `export-schemas.yml` | Push (when `src/models/` changes) | Export JSON schemas |

See `.github/copilot-instructions.md` for detailed conventions.
