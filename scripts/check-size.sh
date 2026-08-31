#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
LIMIT_FILE="$ROOT_DIR/Benchmarks/SizeHost/size-limit-bytes.txt"
APP="${1:-$ROOT_DIR/Benchmarks/SizeHost/.archives/NativeFullSchema.xcarchive/Products/Applications/TDLibKitSizeHost.app}"
EXECUTABLE="$APP/TDLibKitSizeHost"

[[ -f "$EXECUTABLE" ]] || { echo "error: missing size-host executable: $EXECUTABLE" >&2; exit 1; }
limit="$(tr -d '[:space:]' < "$LIMIT_FILE")"
[[ "$limit" =~ ^[0-9]+$ ]] || { echo "error: invalid byte limit in $LIMIT_FILE" >&2; exit 1; }

executable_bytes="$(stat -f %z "$EXECUTABLE")"
frameworks_bytes=0
if [[ -d "$APP/Frameworks" ]]; then
  frameworks_bytes="$(find "$APP/Frameworks" -type f -exec stat -f %z {} + | awk '{sum += $1} END {print sum + 0}')"
fi
total_bytes=$((executable_bytes + frameworks_bytes))

echo "executable_bytes=$executable_bytes"
echo "frameworks_bytes=$frameworks_bytes"
echo "total_bytes=$total_bytes"
echo "limit_bytes=$limit"

if (( total_bytes > limit )); then
  echo "error: size regression: $total_bytes > $limit" >&2
  exit 1
fi

echo "size gate passed"
