# ReproDB Pipeline

Pipeline for collecting, analyzing, and publishing research artifact evaluation
data from systems and security conferences.

## Quick Start

```bash
# Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the full pipeline (local staging)
./run_pipeline.sh

# Run the full pipeline (deploy to website)
./run_pipeline.sh --deploy

# Run tests
pytest tests/ -v
```

## Documentation Sections

- **[CLI Reference](cli/)** — Command-line arguments for all pipeline scripts
- **[Data Schemas](https://reprodb.github.io/data-schemas/)** — JSON Schema definitions for all output formats
- **[API Reference](reference/)** — Python module documentation
