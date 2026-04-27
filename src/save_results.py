"""Save pipeline results to the reprodb-pipeline-results repository.

Saves pipeline results into the results repository so the
orchestrator can call it directly when ``--save-results`` is passed.

Steps:
    1. Archive ``.cache/`` → ``results_dir/cache.tar.gz``
    2. Archive output YAML/JSON → ``results_dir/output/data.tar.gz``,
       copy SVG charts individually for easy diffing
    3. Record input metadata (DBLP hash, git revisions, pipeline args)
    4. ``git add -A && git commit``
    5. Optionally push (when ``cfg.push`` is *True*)
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from src.config import PipelineConfig

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _file_hash(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_info(repo_dir: Path) -> dict[str, str]:
    """Collect git revision info for a repository."""
    info: dict[str, str] = {}
    try:
        info["commit"] = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=repo_dir,
                timeout=10,
            ).stdout.strip()
            or "unknown"
        )
        info["branch"] = (
            subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=repo_dir,
                timeout=10,
            ).stdout.strip()
            or "unknown"
        )
        info["dirty"] = str(
            subprocess.run(
                ["git", "diff", "--quiet"],
                cwd=repo_dir,
                timeout=10,
            ).returncode
            != 0
        ).lower()
    except (subprocess.TimeoutExpired, OSError):
        info.setdefault("commit", "unknown")
        info.setdefault("branch", "unknown")
        info.setdefault("dirty", "unknown")
    return info


def _gh_token() -> str | None:
    """Try to get a GitHub token from the ``gh`` CLI."""
    gh = shutil.which("gh") or str(Path.home() / ".local" / "bin" / "gh")
    if not Path(gh).is_file():
        return None
    try:
        result = subprocess.run(
            [gh, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        token = result.stdout.strip()
        return token or None
    except (subprocess.TimeoutExpired, OSError):
        return None


# ── Main entry point ─────────────────────────────────────────────────────────


def save_results(cfg: PipelineConfig, *, message: str = "") -> None:
    """Copy pipeline outputs into the results repo and commit.

    Parameters
    ----------
    cfg:
        Pipeline configuration (``results_dir``, ``output_dir``, ``push``, etc.).
    message:
        Optional extra text appended to the commit message.
    """
    results_dir = cfg.results_dir.resolve()
    output_dir = cfg.output_dir.resolve()
    pipeline_dir = Path.cwd().resolve()

    # ── Validate ─────────────────────────────────────────────────────────
    if not (results_dir / ".git").is_dir():
        logger.error("Results repository not found: %s", results_dir)
        logger.error("  Initialize it first: git init %s", results_dir)
        return

    if not output_dir.is_dir():
        logger.error("Output directory not found: %s", output_dir)
        return

    now = datetime.now(tz=timezone.utc).astimezone()
    run_date = now.strftime("%Y-%m-%d")
    run_timestamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")

    logger.info("Saving pipeline results to %s", results_dir)
    logger.info("  Output dir: %s", output_dir)
    logger.info("  Date: %s", run_timestamp)

    # ── 1. Cache archive ─────────────────────────────────────────────────
    logger.info("  [1/4] Archiving cache...")
    cache_dir = pipeline_dir / ".cache"
    cache_tar = results_dir / "cache.tar.gz"
    cache_tar.unlink(missing_ok=True)
    old_cache = results_dir / "cache"
    if old_cache.is_dir():
        shutil.rmtree(old_cache)
    if cache_dir.is_dir():
        with tarfile.open(cache_tar, "w:gz") as tar:
            tar.add(str(cache_dir), arcname=".cache")

    # ── 2. Output (data archive + SVG charts) ───────────────────────────
    logger.info("  [2/4] Syncing output...")
    charts_dst = results_dir / "output" / "charts"
    charts_dst.mkdir(parents=True, exist_ok=True)

    # Tar YAML + JSON data files
    data_tar = results_dir / "output" / "data.tar.gz"
    data_tar.unlink(missing_ok=True)
    # Remove old uncompressed trees
    for old in ("_data", "assets"):
        p = results_dir / "output" / old
        if p.is_dir():
            shutil.rmtree(p)

    data_files: list[Path] = []
    yml_dir = output_dir / "_data"
    json_dir = output_dir / "assets" / "data"
    if yml_dir.is_dir():
        data_files.extend(yml_dir.rglob("*.yml"))
    if json_dir.is_dir():
        data_files.extend(json_dir.rglob("*.json"))

    if data_files:
        with tarfile.open(data_tar, "w:gz") as tar:
            for f in data_files:
                arcname = str(f.relative_to(output_dir))
                tar.add(str(f), arcname=arcname)

    # Copy SVG charts individually (useful to diff between runs)
    charts_src = output_dir / "assets" / "charts"
    if charts_src.is_dir():
        for svg in charts_src.glob("*.svg"):
            shutil.copy2(svg, charts_dst / svg.name)

    # ── 3. Input metadata ────────────────────────────────────────────────
    logger.info("  [3/4] Recording input metadata...")
    input_dir = results_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    # DBLP checksum
    dblp_cksum = input_dir / "dblp_checksum.txt"
    if cfg.dblp_file.is_file():
        digest = _file_hash(cfg.dblp_file)
        stat = cfg.dblp_file.stat()
        dblp_cksum.write_text(
            f"{digest}\n{stat.st_size} bytes, modified {datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)}\n"
        )
    else:
        dblp_cksum.write_text("not available\n")

    # Pipeline args log
    args_file = cfg.log_dir / "last_pipeline_args"
    if args_file.is_file():
        shutil.copy2(args_file, input_dir / "pipeline_args.txt")

    # Pipeline log
    log_file = cfg.log_dir / "last_pipeline.log"
    if log_file.is_file():
        shutil.copy2(log_file, input_dir / "pipeline.log")

    # Git revisions of source repos
    pipeline_git = _git_info(pipeline_dir)
    website_git = _git_info(output_dir)
    cache_version_file = pipeline_dir / "config" / "cache-version.txt"
    cache_version = (
        cache_version_file.read_text().strip()
        if cache_version_file.is_file()
        else "none (cache was empty or no cache-version.txt)"
    )

    metadata_lines = [
        f"timestamp: {run_timestamp}",
        "",
        "reprodb-pipeline:",
        f"  commit: {pipeline_git.get('commit', 'unknown')}",
        f"  branch: {pipeline_git.get('branch', 'unknown')}",
        f"  dirty: {pipeline_git.get('dirty', 'unknown')}",
        "",
        "website:",
        f"  commit: {website_git.get('commit', 'unknown')}",
        f"  branch: {website_git.get('branch', 'unknown')}",
        "",
        f"cache_version: {cache_version}",
    ]
    (input_dir / "run_metadata.txt").write_text("\n".join(metadata_lines) + "\n")

    # ── 4. Commit ────────────────────────────────────────────────────────
    logger.info("  [4/4] Committing...")
    subprocess.run(["git", "add", "-A"], cwd=results_dir, check=True, timeout=30)

    commit_msg = f"Pipeline run {run_date}"
    if message:
        commit_msg += f" — {message}"

    # Check if there are changes to commit
    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=results_dir,
        timeout=10,
    )
    if diff_result.returncode == 0:
        logger.info("  No changes since last snapshot — skipping commit")
    else:
        subprocess.run(
            ["git", "commit", "-m", commit_msg, "--quiet"],
            cwd=results_dir,
            check=True,
            timeout=30,
        )
        logger.info("  Committed: %s", commit_msg)

    # ── 5. Push (optional) ───────────────────────────────────────────────
    if cfg.push:
        logger.info("  Pushing to remote...")
        token = _gh_token()
        push_url = f"https://vahldiek:{token}@github.com/reprodb/reprodb-pipeline-results.git" if token else None
        push_cmd: list[str] = (
            ["git", "push", push_url, "main", "--force"] if push_url else ["git", "push", "origin", "main"]
        )
        push_result = subprocess.run(
            push_cmd,
            cwd=results_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if push_result.returncode != 0:
            err = push_result.stderr.strip()
            # Sanitize potential token from error output
            if token and token in err:
                err = err.replace(token, "***")
            logger.warning("Push failed: %s", err)

    logger.info("Results saved to %s", results_dir)
