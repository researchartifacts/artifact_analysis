"""Save pipeline results to the reprodb-pipeline-results repository."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from src.config import PipelineConfig

logger = logging.getLogger(__name__)


def _run_git(*args: str, cwd: Path) -> str:
    """Run a git command, return stripped stdout (empty on failure)."""
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd, timeout=10).stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def save_results(cfg: PipelineConfig, *, message: str = "") -> None:
    """Copy pipeline outputs into the results repo and commit."""
    results = cfg.results_dir.resolve()
    output = cfg.output_dir.resolve()
    pipeline = Path.cwd().resolve()

    if not (results / ".git").is_dir():
        logger.error("Results repo not found: %s", results)
        return
    if not output.is_dir():
        logger.error("Output directory not found: %s", output)
        return

    now = datetime.now(tz=timezone.utc).astimezone()
    run_date = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    logger.info("Saving pipeline results to %s (%s)", results, ts)

    # -- 1. Cache archive -------------------------------------------------
    cache_dir = pipeline / ".cache"
    cache_tar = results / "cache.tar.gz"
    cache_tar.unlink(missing_ok=True)
    old_cache = results / "cache"
    if old_cache.is_dir():
        shutil.rmtree(old_cache)
    if cache_dir.is_dir():
        with tarfile.open(cache_tar, "w:gz") as tar:
            tar.add(str(cache_dir), arcname=".cache")

    # -- 2. Output data + SVG charts --------------------------------------
    charts_dst = results / "output" / "charts"
    charts_dst.mkdir(parents=True, exist_ok=True)
    data_tar = results / "output" / "data.tar.gz"
    data_tar.unlink(missing_ok=True)
    for old in ("_data", "assets"):
        p = results / "output" / old
        if p.is_dir():
            shutil.rmtree(p)

    data_files: list[Path] = []
    if (output / "_data").is_dir():
        data_files.extend((output / "_data").rglob("*.yml"))
    if (output / "assets" / "data").is_dir():
        data_files.extend((output / "assets" / "data").rglob("*.json"))
    if data_files:
        with tarfile.open(data_tar, "w:gz") as tar:
            for f in data_files:
                tar.add(str(f), arcname=str(f.relative_to(output)))

    charts_src = output / "assets" / "charts"
    if charts_src.is_dir():
        for svg in charts_src.glob("*.svg"):
            shutil.copy2(svg, charts_dst / svg.name)

    # -- 3. Input metadata ------------------------------------------------
    input_dir = results / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    if cfg.dblp_file.is_file():
        h = hashlib.sha256()
        with open(cfg.dblp_file, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
        st = cfg.dblp_file.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        (input_dir / "dblp_checksum.txt").write_text(f"{h.hexdigest()}\n{st.st_size} bytes, modified {mtime}\n")
    else:
        (input_dir / "dblp_checksum.txt").write_text("not available\n")

    for src_name, dst_name in [
        ("last_pipeline_args", "pipeline_args.txt"),
        ("last_pipeline.log", "pipeline.log"),
    ]:
        src = cfg.log_dir / src_name
        if src.is_file():
            shutil.copy2(src, input_dir / dst_name)

    dirty = "false" if _run_git("diff", "--quiet", cwd=pipeline) == "" else "true"
    cv_file = pipeline / "config" / "cache-version.txt"
    cv = cv_file.read_text().strip() if cv_file.is_file() else "none"
    lines = [
        f"timestamp: {ts}",
        "",
        "reprodb-pipeline:",
        f"  commit: {_run_git('rev-parse', 'HEAD', cwd=pipeline) or 'unknown'}",
        f"  branch: {_run_git('rev-parse', '--abbrev-ref', 'HEAD', cwd=pipeline) or 'unknown'}",
        f"  dirty: {dirty}",
        "",
        "website:",
        f"  commit: {_run_git('rev-parse', 'HEAD', cwd=output) or 'unknown'}",
        f"  branch: {_run_git('rev-parse', '--abbrev-ref', 'HEAD', cwd=output) or 'unknown'}",
        "",
        f"cache_version: {cv}",
    ]
    (input_dir / "run_metadata.txt").write_text("\n".join(lines) + "\n")

    # -- 4. Commit --------------------------------------------------------
    subprocess.run(["git", "add", "-A"], cwd=results, check=True, timeout=30)
    commit_msg = f"Pipeline run {run_date}" + (f" \u2014 {message}" if message else "")

    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=results, timeout=10).returncode == 0:
        logger.info("No changes since last snapshot \u2014 skipping commit")
    else:
        subprocess.run(
            ["git", "commit", "-m", commit_msg, "--quiet"],
            cwd=results,
            check=True,
            timeout=30,
        )
        logger.info("Committed: %s", commit_msg)

    # -- 5. Push (optional) -----------------------------------------------
    if cfg.push:
        gh = shutil.which("gh") or str(Path.home() / ".local" / "bin" / "gh")
        token = ""
        if Path(gh).is_file():
            with contextlib.suppress(subprocess.TimeoutExpired, OSError):
                token = subprocess.run(
                    [gh, "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                ).stdout.strip()
        push_cmd = (
            [
                "git",
                "push",
                f"https://vahldiek:{token}@github.com/reprodb/reprodb-pipeline-results.git",
                "main",
                "--force",
            ]
            if token
            else ["git", "push", "origin", "main"]
        )
        result = subprocess.run(
            push_cmd,
            cwd=results,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            if token and token in err:
                err = err.replace(token, "***")
            logger.warning("Push failed: %s", err)

    logger.info("Results saved to %s", results)
