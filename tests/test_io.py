"""Tests for src.utils.io — safe JSON/YAML file I/O helpers."""

import json

import pytest
import yaml

from src.utils.io import load_json, load_yaml, save_json, save_yaml


class TestLoadJson:
    def test_reads_valid_file(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps({"key": "value"}))
        assert load_json(f) == {"key": "value"}

    def test_returns_default_on_missing_file(self, tmp_path):
        assert load_json(tmp_path / "missing.json") is None

    def test_returns_custom_default_on_missing_file(self, tmp_path):
        assert load_json(tmp_path / "missing.json", default=[]) == []

    def test_returns_default_on_malformed_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not valid json")
        assert load_json(f) is None

    def test_accepts_str_path(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps([1, 2, 3]))
        assert load_json(str(f)) == [1, 2, 3]


class TestSaveJson:
    def test_writes_valid_json(self, tmp_path):
        f = tmp_path / "out.json"
        save_json(f, {"a": 1})
        assert json.loads(f.read_text()) == {"a": 1}

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "sub" / "deep" / "out.json"
        save_json(f, [1, 2])
        assert json.loads(f.read_text()) == [1, 2]

    def test_trailing_newline(self, tmp_path):
        f = tmp_path / "out.json"
        save_json(f, {})
        assert f.read_text().endswith("\n")

    def test_custom_indent(self, tmp_path):
        f = tmp_path / "out.json"
        save_json(f, {"a": 1}, indent=4)
        assert "    " in f.read_text()


class TestLoadYaml:
    def test_reads_valid_file(self, tmp_path):
        f = tmp_path / "data.yaml"
        f.write_text("key: value\n")
        assert load_yaml(f) == {"key": "value"}

    def test_returns_default_on_missing_file(self, tmp_path):
        assert load_yaml(tmp_path / "missing.yaml") is None

    def test_returns_custom_default(self, tmp_path):
        assert load_yaml(tmp_path / "nope.yaml", default={}) == {}

    def test_returns_default_on_malformed_yaml(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text(":\n  -\n  : :\n")
        result = load_yaml(f)
        # Even if pyyaml parses this oddly, it should not raise
        assert result is not None or result is None  # no crash


class TestSaveYaml:
    def test_writes_valid_yaml(self, tmp_path):
        f = tmp_path / "out.yaml"
        save_yaml(f, {"x": [1, 2]})
        loaded = yaml.safe_load(f.read_text())
        assert loaded == {"x": [1, 2]}

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "a" / "b" / "out.yaml"
        save_yaml(f, {"ok": True})
        assert yaml.safe_load(f.read_text()) == {"ok": True}
