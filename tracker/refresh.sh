#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EVENTS_TMP=$(mktemp)
ERR_TMP=$(mktemp)
trap 'rm -f "$EVENTS_TMP" "$ERR_TMP"' EXIT

SWIFT_SRC="$SITE_DIR/fetch_evidence.swift"
SWIFT_BIN="$SITE_DIR/fetch_evidence"

# Compile the EventKit fetcher once (or when the source changes). ~0.3s to run
# thereafter — vs ~90s for the old Calendar.app AppleScript whose-filter.
if [ ! -x "$SWIFT_BIN" ] || [ "$SWIFT_SRC" -nt "$SWIFT_BIN" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Compiling fetch_evidence ..."
  swiftc -O "$SWIFT_SRC" -o "$SWIFT_BIN"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pulling Evidence. calendar via EventKit ..."
set +e
"$SWIFT_BIN" >"$EVENTS_TMP" 2>"$ERR_TMP"
FETCH_EXIT=$?
set -e

# Guard: bail before touching local data if the fetch failed.
if [ "$FETCH_EXIT" -ne 0 ]; then
  echo "ERROR: fetch_evidence exited $FETCH_EXIT — aborting (local data untouched)."
  echo "stderr:"; cat "$ERR_TMP"
  echo "(exit 2 = no calendar access; exit 3 = no Evidence. calendar)"
  exit 1
fi
if [ ! -s "$EVENTS_TMP" ]; then
  echo "ERROR: fetch produced no output — aborting (local data untouched)."
  echo "stderr:"; cat "$ERR_TMP"
  exit 1
fi

EVENT_COUNT=$(wc -l < "$EVENTS_TMP" | tr -d ' ')
echo "Got $EVENT_COUNT events. Building data.json + breakdown_data.json (local only) ..."

python3 "$SITE_DIR/build_data.py" "$SITE_DIR" < "$EVENTS_TMP"
python3 "$SITE_DIR/build_breakdown.py" "$SITE_DIR" < "$EVENTS_TMP"

# Local-only: just open index.html in a browser to view.
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Built locally. View: open $SITE_DIR/index.html"
