"""Pipeline configuration dataclass.

Centralises the arguments shared across generators, enrichers, and the
pipeline orchestrator so that configuration is validated once at startup
rather than scattered across individual ``argparse`` blocks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Immutable configuration for a single pipeline run."""

    # ── Paths ────────────────────────────────────────────────────────────
    output_dir: Path = field(default_factory=lambda: Path("output/staging"))
    data_dir: Path = field(default_factory=lambda: Path("data"))
    results_dir: Path = field(default_factory=lambda: Path("../reprodb-pipeline-results"))
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    dblp_file: Path = field(default_factory=lambda: Path("data/dblp/dblp.xml.gz"))

    # ── Scraping / filtering ────────────────────────────────────────────
    conf_regex: str = r".*20[12][0-9]"

    # ── Proxy settings ──────────────────────────────────────────────────
    http_proxy: str | None = None
    https_proxy: str | None = None

    # ── Pipeline behaviour ──────────────────────────────────────────────
    deploy: bool = False
    save_results: bool = False
    push: bool = False
    refresh: bool = False

    def __post_init__(self) -> None:
        """Coerce strings to Path and resolve proxy defaults."""
        self.output_dir = Path(self.output_dir)
        self.data_dir = Path(self.data_dir)
        self.results_dir = Path(self.results_dir)
        self.log_dir = Path(self.log_dir)
        self.dblp_file = Path(self.dblp_file)

        # Mirror the shell script's auto-detection behaviour
        if self.https_proxy is None and self.http_proxy is not None:
            self.https_proxy = self.http_proxy

    @classmethod
    def from_env(cls) -> PipelineConfig:
        """Build config from environment variables (``PIPELINE_*``)."""
        kwargs: dict[str, object] = {}
        env_map = {
            "PIPELINE_OUTPUT_DIR": "output_dir",
            "PIPELINE_DATA_DIR": "data_dir",
            "PIPELINE_RESULTS_DIR": "results_dir",
            "PIPELINE_LOG_DIR": "log_dir",
            "PIPELINE_DBLP_FILE": "dblp_file",
            "PIPELINE_CONF_REGEX": "conf_regex",
            "PIPELINE_DEPLOY": "deploy",
            "PIPELINE_SAVE_RESULTS": "save_results",
            "PIPELINE_PUSH": "push",
            "PIPELINE_REFRESH": "refresh",
        }
        for env_key, attr in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                if attr in ("deploy", "save_results", "push", "refresh"):
                    kwargs[attr] = val.lower() in ("1", "true", "yes")
                else:
                    kwargs[attr] = val

        # Proxy from standard env vars
        kwargs.setdefault("http_proxy", os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY"))
        kwargs.setdefault("https_proxy", os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY"))

        return cls(**kwargs)  # type: ignore[arg-type]

    @property
    def assets_data(self) -> Path:
        """``<output_dir>/assets/data`` convenience path."""
        return self.output_dir / "assets" / "data"

    @property
    def jekyll_data(self) -> Path:
        """``<output_dir>/_data`` convenience path."""
        return self.output_dir / "_data"

    def ensure_dirs(self) -> None:
        """Create required output directories."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_data.mkdir(parents=True, exist_ok=True)
        self.jekyll_data.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
