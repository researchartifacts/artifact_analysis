"""Python pipeline orchestrator.

Replaces ``run_pipeline.sh`` with a Python-native orchestrator that uses
:mod:`src.stages` for dependency ordering and :mod:`src.config` for
configuration.  Independent stages within the same tier run in parallel
via :class:`concurrent.futures.ThreadPoolExecutor`.

Usage::

    python -m src.orchestrator                     # local staging
    python -m src.orchestrator --deploy            # write to live site
    python -m src.orchestrator --log-format json   # structured logs
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.config import PipelineConfig
from src.stages import STAGES, Stage, parallel_groups
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


# ── Stage → CLI arguments mapping ────────────────────────────────────────────


def _stage_args(stage: Stage, cfg: PipelineConfig) -> list[str]:
    """Return the CLI arguments for a given stage based on its module's argparse interface."""
    name = stage.name
    out = str(cfg.output_dir)
    dblp = str(cfg.dblp_file)
    regex = cfg.conf_regex

    mapping: dict[str, list[str]] = {
        "dblp_extract": ["--dblp_file", dblp],
        "statistics": ["--conf_regex", regex, "--output_dir", out],
        "repo_stats": ["--conf_regex", regex, "--output_dir", out],
        "artifact_availability": ["--conf_regex", regex, "--output_dir", out],
        "participation_stats": ["--dblp_file", dblp, "--output_dir", out],
        "author_stats": ["--dblp_file", dblp, "--data_dir", out, "--output_dir", out],
        "area_authors": ["--data_dir", out],
        "committee_stats": ["--conf_regex", regex, "--output_dir", out],
        "combined_rankings": ["--data_dir", out],
        "institution_rankings": ["--data_dir", out],
        "author_profiles": ["--data_dir", out],
        "search_data": ["--data_dir", out],
        "ranking_history": ["--data_dir", out],
        "visualizations": ["--data_dir", out],
    }
    return mapping.get(name, [])


# ── Pre-flight checks ───────────────────────────────────────────────────────


def _detect_github_token() -> None:
    """Try to auto-detect GITHUB_TOKEN from ``gh`` CLI if not set."""
    if os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"):
        return
    gh = shutil.which("gh") or Path.home() / ".local" / "bin" / "gh"
    if Path(gh).is_file():
        try:
            result = subprocess.run(
                [str(gh), "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            token = result.stdout.strip()
            if token:
                os.environ["GITHUB_TOKEN"] = token
                logger.info("Using GitHub token from gh CLI (5,000 req/hr)")
                return
        except (subprocess.TimeoutExpired, OSError):
            pass
    logger.warning("No GITHUB_TOKEN set — limited to 60 GitHub API requests/hr")


def _seed_staging(cfg: PipelineConfig) -> None:
    """Copy existing website data into staging so incremental generators work."""
    live_site = Path("../reprodb.github.io")
    if str(cfg.output_dir) != "output/staging" or not live_site.is_dir():
        return
    logger.info("Seeding staging directory from reprodb.github.io...")
    for subdir in ("_data", "assets/data", "assets/charts"):
        src = live_site / subdir
        dst = cfg.output_dir / subdir
        dst.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            for item in src.iterdir():
                target = dst / item.name
                if not target.exists():
                    if item.is_dir():
                        shutil.copytree(item, target)
                    else:
                        shutil.copy2(item, target)


def _check_dblp(cfg: PipelineConfig) -> None:
    """Run the DBLP download script if it exists."""
    script = Path("scripts/download_dblp.sh")
    if not script.is_file():
        return
    logger.info("Checking DBLP freshness...")
    try:
        subprocess.run(["bash", str(script), "--auto"], check=False, timeout=600)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("DBLP download check failed: %s", e)


def _should_skip(stage: Stage, cfg: PipelineConfig) -> bool:
    """Return True if a stage should be skipped due to missing prerequisites."""
    if stage.name in ("dblp_extract", "participation_stats", "author_stats") and not cfg.dblp_file.is_file():
        logger.warning("Skipping %s — DBLP file not found: %s", stage.name, cfg.dblp_file)
        return True
    return False


# ── Stage execution ──────────────────────────────────────────────────────────


def _run_stage(stage: Stage, cfg: PipelineConfig, python: str) -> tuple[str, bool, float]:
    """Run a single stage as a subprocess. Returns (name, success, elapsed)."""
    if _should_skip(stage, cfg):
        return stage.name, True, 0.0

    cmd = [python, "-m", stage.module, *_stage_args(stage, cfg)]
    logger.info("▶ %s: %s", stage.name, stage.description)
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        elapsed = time.monotonic() - start
        if result.stdout:
            for line in result.stdout.rstrip().split("\n"):
                logger.info("  %s", line)
        if result.returncode != 0:
            for line in (result.stderr or "").rstrip().split("\n"):
                if line:
                    logger.error("  %s", line)
            if stage.optional:
                logger.warning("⚠ %s failed (optional, continuing)", stage.name)
                return stage.name, True, elapsed
            logger.error("✗ %s failed (exit %d)", stage.name, result.returncode)
            return stage.name, False, elapsed
        logger.info("✓ %s completed (%.1fs)", stage.name, elapsed)
        return stage.name, True, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        logger.error("✗ %s timed out after %.0fs", stage.name, elapsed)
        return stage.name, False, elapsed
    except OSError as e:
        elapsed = time.monotonic() - start
        logger.error("✗ %s failed to start: %s", stage.name, e)
        return stage.name, False, elapsed


# ── Main orchestrator ────────────────────────────────────────────────────────


def run_pipeline(cfg: PipelineConfig, *, max_workers: int = 4) -> bool:
    """Execute the full pipeline using the stage dependency graph.

    Returns True if all required stages succeeded.
    """
    cfg.ensure_dirs()
    _detect_github_token()
    _seed_staging(cfg)
    _check_dblp(cfg)

    if cfg.http_proxy:
        os.environ.setdefault("http_proxy", cfg.http_proxy)
        os.environ.setdefault("HTTP_PROXY", cfg.http_proxy)
    if cfg.https_proxy:
        os.environ.setdefault("https_proxy", cfg.https_proxy)
        os.environ.setdefault("HTTPS_PROXY", cfg.https_proxy)

    python = sys.executable
    groups = parallel_groups(STAGES)
    total_stages = sum(len(g) for g in groups)
    completed = 0
    failed: list[str] = []
    timings: dict[str, float] = {}

    pipeline_start = time.monotonic()

    for tier_idx, tier in enumerate(groups):
        logger.info("── Tier %d/%d (%d stages) ──", tier_idx + 1, len(groups), len(tier))

        if len(tier) == 1:
            name, ok, elapsed = _run_stage(tier[0], cfg, python)
            completed += 1
            timings[name] = elapsed
            if not ok:
                failed.append(name)
                return False
        else:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(tier))) as pool:
                futures = {pool.submit(_run_stage, stage, cfg, python): stage for stage in tier}
                for future in as_completed(futures):
                    name, ok, elapsed = future.result()
                    completed += 1
                    timings[name] = elapsed
                    if not ok:
                        failed.append(name)

            if failed:
                logger.error("Pipeline aborted — required stage(s) failed: %s", ", ".join(failed))
                return False

    total_elapsed = time.monotonic() - pipeline_start
    logger.info("Pipeline complete! %d/%d stages in %.1fs", completed, total_stages, total_elapsed)

    # Log timing summary
    for name, elapsed in sorted(timings.items(), key=lambda x: -x[1]):
        if elapsed > 0:
            logger.info("  %-25s %6.1fs", name, elapsed)

    return True


# ── CLI ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    from src.utils.logging_config import add_log_level_arg

    parser = argparse.ArgumentParser(
        description="Run the ReproDB data-generation pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--output_dir", type=str, default=None, help="Output directory")
    parser.add_argument("--conf_regex", type=str, default=None, help="Conference regex filter")
    parser.add_argument("--http_proxy", type=str, default=None)
    parser.add_argument("--https_proxy", type=str, default=None)
    parser.add_argument("--deploy", action="store_true", help="Write directly to reprodb.github.io")
    parser.add_argument("--save-results", action="store_true", help="Save results snapshot")
    parser.add_argument("--results_dir", type=str, default=None)
    parser.add_argument("--push", action="store_true", help="Push results after saving")
    parser.add_argument("--max-workers", type=int, default=4, help="Max parallel stages per tier")
    add_log_level_arg(parser)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    setup_logging(args.log_level, log_format=args.log_format)

    # Build config from CLI args, falling back to defaults
    kwargs: dict[str, object] = {}
    if args.output_dir:
        kwargs["output_dir"] = args.output_dir
    elif args.deploy:
        kwargs["output_dir"] = "../reprodb.github.io"
        kwargs["deploy"] = True
    if args.conf_regex:
        kwargs["conf_regex"] = args.conf_regex
    if args.http_proxy:
        kwargs["http_proxy"] = args.http_proxy
    if args.https_proxy:
        kwargs["https_proxy"] = args.https_proxy
    if args.save_results:
        kwargs["save_results"] = True
    if args.results_dir:
        kwargs["results_dir"] = args.results_dir
    if args.push:
        kwargs["push"] = True

    cfg = PipelineConfig(**kwargs)  # type: ignore[arg-type]
    logger.info("Output directory: %s", cfg.output_dir)
    logger.info("Conference regex: %s", cfg.conf_regex)

    success = run_pipeline(cfg, max_workers=args.max_workers)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
