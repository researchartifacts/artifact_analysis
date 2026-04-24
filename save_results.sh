#!/bin/bash
# Save pipeline run results to the reprodb-pipeline-results repository.
#
# Usage: ./save_results.sh [--results_dir DIR] [--output_dir DIR] [--message MSG]
#                          [--push] [--https_proxy URL]
#
# This copies cache, output, and input metadata into the results repo and commits.
# If --push is given, pushes to the remote.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
DATA_DIR="$SCRIPT_DIR/data"
LOG_DIR="$SCRIPT_DIR/logs"
DBLP_FILE="$DATA_DIR/dblp/dblp.xml.gz"
CACHE_VERSION_FILE="$SCRIPT_DIR/config/cache-version.txt"

RESULTS_DIR="../reprodb-pipeline-results"
OUTPUT_DIR="../reprodb.github.io"
EXTRA_MSG=""
DO_PUSH=false

while [ $# -gt 0 ]; do
    case "$1" in
        --results_dir)  RESULTS_DIR="$2";  shift 2 ;;
        --output_dir)   OUTPUT_DIR="$2";   shift 2 ;;
        --message)      EXTRA_MSG="$2";    shift 2 ;;
        --push)         DO_PUSH=true;      shift ;;
        --https_proxy)  export https_proxy="$2" HTTPS_PROXY="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ ! -d "$RESULTS_DIR/.git" ]; then
    echo "❌ Results repository not found: $RESULTS_DIR"
    echo "   Initialize it first: git init $RESULTS_DIR"
    exit 1
fi

if [ ! -d "$OUTPUT_DIR" ]; then
    echo "❌ Output directory not found: $OUTPUT_DIR"
    exit 1
fi

RESULTS_DIR="$(cd "$RESULTS_DIR" && pwd)"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
RUN_DATE="$(date '+%Y-%m-%d')"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

echo "📦 Saving pipeline results to $RESULTS_DIR"
echo "   Output dir: $OUTPUT_DIR"
echo "   Date: $RUN_TIMESTAMP"

# ── 1. Cache (tar archive — thousands of small files compress well) ───────────
echo "  [1/4] Archiving cache..."
rm -f "$RESULTS_DIR/cache.tar.gz"
rm -rf "$RESULTS_DIR/cache"   # remove old uncompressed tree if present
tar -czf "$RESULTS_DIR/cache.tar.gz" -C "$SCRIPT_DIR" .cache 2>/dev/null || true

# ── 2. Output (tar data files, keep charts as individual SVGs for diffing) ────
echo "  [2/4] Syncing output..."
mkdir -p "$RESULTS_DIR/output/charts"

# Tar YAML + JSON data files (some are multi-MB)
rm -f "$RESULTS_DIR/output/data.tar.gz"
rm -rf "$RESULTS_DIR/output/_data" "$RESULTS_DIR/output/assets"  # remove old uncompressed trees
_tmplist="$(mktemp)"
{
    find "$OUTPUT_DIR/_data" -name '*.yml' 2>/dev/null
    find "$OUTPUT_DIR/assets/data" -name '*.json' 2>/dev/null
} > "$_tmplist"
if [ -s "$_tmplist" ]; then
    tar -czf "$RESULTS_DIR/output/data.tar.gz" \
        -C "$OUTPUT_DIR" \
        --files-from=<(sed "s|^$OUTPUT_DIR/||" "$_tmplist") \
        2>/dev/null || true
fi
rm -f "$_tmplist"

# Copy charts individually (small SVGs, useful to diff between runs)
for f in "$OUTPUT_DIR"/assets/charts/*.svg; do
    [ -f "$f" ] && cp "$f" "$RESULTS_DIR/output/charts/"
done

# ── 3. Input metadata ────────────────────────────────────────────────────────
echo "  [3/4] Recording input metadata..."
mkdir -p "$RESULTS_DIR/input"

# DBLP checksum (the file is ~1GB, so store checksum not the file)
if [ -f "$DBLP_FILE" ]; then
    sha256sum "$DBLP_FILE" | awk '{print $1}' > "$RESULTS_DIR/input/dblp_checksum.txt"
    stat --format='%s bytes, modified %y' "$DBLP_FILE" 2>/dev/null \
        >> "$RESULTS_DIR/input/dblp_checksum.txt" || true
else
    echo "not available" > "$RESULTS_DIR/input/dblp_checksum.txt"
fi

# Record pipeline arguments if available
if [ -f "$LOG_DIR/last_pipeline_args" ]; then
    cp "$LOG_DIR/last_pipeline_args" "$RESULTS_DIR/input/pipeline_args.txt"
fi

# Record pipeline log if available
if [ -f "$LOG_DIR/last_pipeline.log" ]; then
    cp "$LOG_DIR/last_pipeline.log" "$RESULTS_DIR/input/pipeline.log"
fi

# Record git revisions of the source repos
{
    echo "timestamp: $RUN_TIMESTAMP"
    echo ""
    echo "reprodb-pipeline:"
    echo "  commit: $(cd "$SCRIPT_DIR" && git rev-parse HEAD 2>/dev/null || echo 'unknown')"
    echo "  branch: $(cd "$SCRIPT_DIR" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
    echo "  dirty: $(cd "$SCRIPT_DIR" && git diff --quiet 2>/dev/null && echo 'false' || echo 'true')"
    echo ""
    echo "website:"
    echo "  commit: $(cd "$OUTPUT_DIR" && git rev-parse HEAD 2>/dev/null || echo 'unknown')"
    echo "  branch: $(cd "$OUTPUT_DIR" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
    echo ""
    echo "cache_version: $(cat "$CACHE_VERSION_FILE" 2>/dev/null || echo 'none (cache was empty or no cache-version.txt)')"
} > "$RESULTS_DIR/input/run_metadata.txt"

# ── 4. Commit ─────────────────────────────────────────────────────────────────
echo "  [4/4] Committing..."
cd "$RESULTS_DIR"

git add -A

# Build commit message
COMMIT_MSG="Pipeline run $RUN_DATE"
if [ -n "$EXTRA_MSG" ]; then
    COMMIT_MSG="$COMMIT_MSG — $EXTRA_MSG"
fi

# Check if there are changes to commit
if git diff --cached --quiet; then
    echo "  ℹ️  No changes since last snapshot — skipping commit"
else
    git commit -m "$COMMIT_MSG" --quiet
    echo "  ✅ Committed: $COMMIT_MSG"
fi

# ── 5. Push (optional) ───────────────────────────────────────────────────────
if [ "$DO_PUSH" = true ]; then
    echo "  Pushing to remote..."
    _gh="$(command -v gh 2>/dev/null || echo "$HOME/.local/bin/gh")"
    if [ -x "$_gh" ]; then
        TOKEN="$("$_gh" auth token 2>/dev/null || true)"
        if [ -n "$TOKEN" ]; then
            git push "https://vahldiek:${TOKEN}@github.com/reprodb/reprodb-pipeline-results.git" main --force 2>&1 \
                || echo "  ⚠️  Push failed (repo may not exist on GitHub yet)"
        else
            git push origin main 2>&1 || echo "  ⚠️  Push failed"
        fi
    else
        git push origin main 2>&1 || echo "  ⚠️  Push failed"
    fi
fi

echo "📦 Results saved to $RESULTS_DIR"
