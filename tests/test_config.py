"""Tests for PipelineConfig."""

from pathlib import Path

from src.config import PipelineConfig


class TestPipelineConfig:
    def test_defaults(self):
        cfg = PipelineConfig()
        assert cfg.output_dir == Path("output/staging")
        assert cfg.conf_regex == r".*20[12][0-9]"
        assert cfg.deploy is False

    def test_coerce_strings(self):
        cfg = PipelineConfig(output_dir="/tmp/out", data_dir="/tmp/data")  # type: ignore[arg-type]
        assert isinstance(cfg.output_dir, Path)
        assert isinstance(cfg.data_dir, Path)

    def test_auto_https_proxy(self):
        cfg = PipelineConfig(http_proxy="http://proxy:8080")
        assert cfg.https_proxy == "http://proxy:8080"

    def test_convenience_paths(self):
        cfg = PipelineConfig(output_dir=Path("/out"))
        assert cfg.assets_data == Path("/out/assets/data")
        assert cfg.jekyll_data == Path("/out/_data")

    def test_ensure_dirs(self, tmp_path):
        cfg = PipelineConfig(output_dir=tmp_path / "site", log_dir=tmp_path / "logs")
        cfg.ensure_dirs()
        assert (tmp_path / "site" / "assets" / "data").is_dir()
        assert (tmp_path / "site" / "_data").is_dir()
        assert (tmp_path / "logs").is_dir()

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_OUTPUT_DIR", "/env/out")
        monkeypatch.setenv("PIPELINE_DEPLOY", "true")
        monkeypatch.setenv("PIPELINE_CONF_REGEX", "OSDI2024")
        # Clear proxy env vars to avoid interference
        monkeypatch.delenv("http_proxy", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("https_proxy", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        cfg = PipelineConfig.from_env()
        assert cfg.output_dir == Path("/env/out")
        assert cfg.deploy is True
        assert cfg.conf_regex == "OSDI2024"
