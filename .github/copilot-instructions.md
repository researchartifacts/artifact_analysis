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
| `generate_author_stats.py` | `author_stats.schema.json` |
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
