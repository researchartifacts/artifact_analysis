# Artifact Analysis

Pipeline for collecting, analyzing, and publishing research artifact evaluation
data from systems and security conferences.

## Quick Start

```bash
# Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the full pipeline
./run_pipeline.sh --output_dir ../researchartifacts.github.io

# Run tests
pytest tests/ -v
```

## Documentation Sections

- **[CLI Reference](cli/)** — Command-line arguments for all 40 scripts
- **[Data Schemas](schemas/)** — Pydantic models defining all output formats
- **[API Reference](reference/)** — Python module documentation
