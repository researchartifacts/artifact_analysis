#!/usr/bin/env python3
"""Export JSON Schema files from Pydantic models.

Generates one ``.schema.json`` file per model, matching the layout in the
``data-schemas`` repository.  Run this after modifying any model in
``src/models/`` to keep schemas in sync.

Usage:
    python -m src.models.export_schemas --output_dir ../data-schemas/schemas
"""

import argparse
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)
# Registry: (schema_filename, list_wrapper, model_class_import_path)
# list_wrapper == True means the top-level schema is ``type: array`` wrapping items.
SCHEMA_REGISTRY: list[tuple[str, bool, str, str]] = [
    # (filename, is_array, module, class_name)
    ("artifacts.schema.json", True, "src.models.artifacts", "Artifact"),
    ("artifacts_by_conference.schema.json", True, "src.models.artifacts_by_conference", "ConferenceEntry"),
    ("artifacts_by_year.schema.json", True, "src.models.artifacts_by_year", "YearCount"),
    ("author_index.schema.json", True, "src.models.author_index", "AuthorIndexEntry"),
    ("author_stats.schema.json", True, "src.models.author_stats", "AuthorStats"),
    ("combined_rankings.schema.json", True, "src.models.combined_rankings", "AuthorRanking"),
    ("institution_rankings.schema.json", True, "src.models.institution_rankings", "InstitutionRanking"),
    ("paper_index.schema.json", True, "src.models.paper_index", "Paper"),
    ("repo_stats.schema.json", True, "src.models.repo_stats", "RepoStatsEntry"),
    ("repo_stats_summary.schema.json", False, "src.models.repo_stats", "RepoStatsSummary"),
    ("search_data.schema.json", True, "src.models.search_data", "SearchEntry"),
    ("summary.schema.json", False, "src.models.summary", "Summary"),
]

BASE_URL = "https://reprodb.github.io/data-schemas/schemas"


def _import_class(module_path: str, class_name: str):
    """Dynamically import a class from a dotted module path."""
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def _make_array_schema(item_schema: dict[str, Any], title: str, description: str, schema_id: str) -> dict:
    """Wrap an item schema in a JSON Schema array with $defs."""
    from src.models import SCHEMA_VERSION

    # Pydantic generates a schema with $defs for nested models.
    # We hoist $defs to top level and use $ref for items.
    defs = item_schema.pop("$defs", {})

    # The main class schema becomes a $def entry
    class_name = item_schema.get("title", "Item")
    defs[class_name] = item_schema

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        "title": title,
        "description": description,
        "version": SCHEMA_VERSION,
        "type": "array",
        "items": {"$ref": f"#/$defs/{class_name}"},
        "$defs": defs,
    }


def _make_object_schema(obj_schema: dict[str, Any], schema_id: str) -> dict:
    """Add standard JSON Schema metadata to an object schema."""
    from src.models import SCHEMA_VERSION

    obj_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    obj_schema["$id"] = schema_id
    obj_schema["version"] = SCHEMA_VERSION
    return obj_schema


def export_all(output_dir: str) -> list[str]:
    """Export all registered schemas. Returns list of written file paths."""
    os.makedirs(output_dir, exist_ok=True)
    written = []

    for filename, is_array, module_path, class_name in SCHEMA_REGISTRY:
        cls = _import_class(module_path, class_name)
        schema = cls.model_json_schema()
        schema_id = f"{BASE_URL}/{filename}"

        if is_array:
            title = schema.get("title", class_name)
            description = schema.get("description", "")
            # Use the class docstring if model description is empty
            if not description and cls.__doc__:
                description = cls.__doc__.strip().split("\n")[0]
            final = _make_array_schema(schema, f"{title} Collection", description, schema_id)
        else:
            final = _make_object_schema(schema, schema_id)

        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=2, ensure_ascii=False)
            f.write("\n")

        written.append(path)
        logger.info(f"  {filename}")

    return written


def main():
    parser = argparse.ArgumentParser(description="Export JSON Schemas from Pydantic models.")
    parser.add_argument(
        "--output_dir",
        type=str,
        default="../data-schemas/schemas",
        help="Output directory for .schema.json files (default: ../data-schemas/schemas)",
    )
    args = parser.parse_args()

    logger.info(f"Exporting {len(SCHEMA_REGISTRY)} schemas to {args.output_dir}")
    written = export_all(args.output_dir)
    logger.info(f"\nDone. {len(written)} schema files written.")


if __name__ == "__main__":
    from src.utils.logging_config import setup_logging

    setup_logging()

    main()
