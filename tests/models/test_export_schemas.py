"""Tests for src/models/export_schemas — JSON Schema export."""

import json
import os

from src.models.export_schemas import SCHEMA_REGISTRY, export_all


class TestExportAll:
    def test_writes_all_schemas(self, tmp_path):
        written = export_all(str(tmp_path))
        assert len(written) == len(SCHEMA_REGISTRY)
        for path in written:
            assert os.path.exists(path)

    def test_valid_json(self, tmp_path):
        written = export_all(str(tmp_path))
        for path in written:
            with open(path) as f:
                schema = json.load(f)
            assert "$schema" in schema
            assert "$id" in schema

    def test_array_schemas_have_items(self, tmp_path):
        export_all(str(tmp_path))
        for filename, is_array, _, _ in SCHEMA_REGISTRY:
            if is_array:
                with open(tmp_path / filename) as f:
                    schema = json.load(f)
                assert schema["type"] == "array"
                assert "items" in schema

    def test_object_schemas_have_properties(self, tmp_path):
        export_all(str(tmp_path))
        for filename, is_array, _, _ in SCHEMA_REGISTRY:
            if not is_array:
                with open(tmp_path / filename) as f:
                    schema = json.load(f)
                assert "properties" in schema or "$defs" in schema

    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "nested" / "schemas"
        export_all(str(out))
        assert out.exists()

    def test_idempotent(self, tmp_path):
        export_all(str(tmp_path))
        first = {f: (tmp_path / f).read_text() for f in os.listdir(tmp_path)}
        export_all(str(tmp_path))
        second = {f: (tmp_path / f).read_text() for f in os.listdir(tmp_path)}
        assert first == second
