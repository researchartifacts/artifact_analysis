#!/bin/bash
# Download DBLP XML database (~3GB compressed) for author matching
# Usage: ./download_dblp.sh [--auto] [http_proxy] [https_proxy]
# --auto: non-interactive mode, downloads if missing or outdated

AUTO=false
if [ "$1" = "--auto" ]; then
    AUTO=true
    shift
fi

[ -n "$1" ] && export http_proxy="$1" HTTP_PROXY="$1"
[ -n "$2" ] && export https_proxy="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DBLP_URL="https://dblp.org/xml/dblp.xml.gz"
DBLP_FILE="dblp.xml.gz"

[ -n "$http_proxy" ] && echo "http_proxy: $http_proxy"
[ -n "$https_proxy" ] && echo "https_proxy: $https_proxy"

# Check if file already exists and whether it's up to date
if [ -f "$DBLP_FILE" ]; then
    FILE_SIZE=$(du -m "$DBLP_FILE" | cut -f1)
    LOCAL_DATE=$(date -r "$DBLP_FILE" +%s 2>/dev/null || stat -c %Y "$DBLP_FILE" 2>/dev/null)

    # Fetch remote Last-Modified header
    REMOTE_HEADER=$(curl -sI --max-time 10 -L "$DBLP_URL" 2>/dev/null | grep -i '^Last-Modified:')
    REMOTE_DATE=""
    if [ -n "$REMOTE_HEADER" ]; then
        REMOTE_DATE=$(date -d "$(echo "$REMOTE_HEADER" | sed 's/^[^:]*: //')" +%s 2>/dev/null)
    fi

    if [ -n "$REMOTE_DATE" ] && [ -n "$LOCAL_DATE" ] && [ "$LOCAL_DATE" -ge "$REMOTE_DATE" ]; then
        echo "✅ $DBLP_FILE is up to date (${FILE_SIZE}MB)"
        exit 0
    elif [ -n "$REMOTE_DATE" ]; then
        LOCAL_PRETTY=$(date -d @"$LOCAL_DATE" +%Y-%m-%d 2>/dev/null)
        REMOTE_PRETTY=$(date -d @"$REMOTE_DATE" +%Y-%m-%d 2>/dev/null)
        echo "⚠️  $DBLP_FILE is outdated (local: $LOCAL_PRETTY, remote: $REMOTE_PRETTY)"
    else
        echo "⚠️  $DBLP_FILE exists (${FILE_SIZE}MB), could not check remote date"
        # If we can't check and file exists, assume it's fine in auto mode
        $AUTO && exit 0
    fi

    if ! $AUTO; then
        read -p "Re-download? (y/N): " -n 1 -r
        echo ""
        [[ ! $REPLY =~ ^[Yy]$ ]] && exit 0
    fi
    rm -f "$DBLP_FILE"
fi

# Test connectivity
if ! curl -s --max-time 10 -I "$DBLP_URL" > /dev/null 2>&1; then
    echo "❌ Cannot connect to dblp.org (proxy: $https_proxy)"
    exit 1
fi

echo "Downloading $DBLP_URL ..."
curl -L --progress-bar --retry 3 --retry-delay 5 --max-time 0 -o "$DBLP_FILE" "$DBLP_URL"
DOWNLOAD_STATUS=$?

if [ $DOWNLOAD_STATUS -eq 0 ] && [ -f "$DBLP_FILE" ]; then
    FILE_SIZE=$(du -m "$DBLP_FILE" | cut -f1)
    if [ $FILE_SIZE -lt 500 ]; then
        echo "⚠️  File too small (${FILE_SIZE}MB, expected ~1000MB compressed) — download may be truncated"
        exit 1
    fi
    echo "✅ Download complete (${FILE_SIZE}MB)"
else
    echo "❌ Download failed (status $DOWNLOAD_STATUS)"
    exit 1
fi
