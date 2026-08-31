#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
ARCHIVE="${1:-}"
LABEL="${2:-}"

[[ -f "$ARCHIVE" ]] || { echo "error: candidate archive is required" >&2; exit 1; }
[[ "$LABEL" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "error: safe output label is required" >&2; exit 1; }

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/tdlibkit-size-variant.XXXXXX")"
trap 'rm -rf "$TEMP_ROOT"' EXIT
PACKAGE_DIR="$TEMP_ROOT/TDLibKit"
HOST_DIR="$TEMP_ROOT/SizeHost"
OUTPUT_ARCHIVE="$ROOT_DIR/Benchmarks/SizeHost/.archives/$LABEL.xcarchive"

[[ ! -e "$OUTPUT_ARCHIVE" ]] || { echo "error: output already exists: $OUTPUT_ARCHIVE" >&2; exit 1; }
mkdir -p "$PACKAGE_DIR/Artifacts" "$HOST_DIR"
cp "$ROOT_DIR/Package.swift" "$PACKAGE_DIR/Package.swift"
cp -R "$ROOT_DIR/Sources" "$PACKAGE_DIR/Sources"
cp -R "$ROOT_DIR/Tests" "$PACKAGE_DIR/Tests"
cp -R "$ROOT_DIR/Benchmarks/SizeHost/Sources" "$HOST_DIR/Sources"

xcodebuild -create-xcframework \
  -library "$ARCHIVE" -headers "$ROOT_DIR/Native/Headers" \
  -output "$PACKAGE_DIR/Artifacts/TdStatic.xcframework"

sed "s#__TDLIBKIT_PACKAGE__#$PACKAGE_DIR#" \
  "$ROOT_DIR/Benchmarks/SizeHost/variant-project.yml.in" > "$HOST_DIR/project.yml"
xcodegen generate --spec "$HOST_DIR/project.yml" --project "$HOST_DIR"
xcodebuild \
  -project "$HOST_DIR/TDLibKitSizeHost.xcodeproj" \
  -scheme TDLibKitSizeHost \
  -configuration Release \
  -sdk iphoneos \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$TEMP_ROOT/DerivedData" \
  -archivePath "$OUTPUT_ARCHIVE" \
  archive \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  ONLY_ACTIVE_ARCH=YES ARCHS=arm64 SKIP_INSTALL=NO

"$ROOT_DIR/scripts/check-size.sh" \
  "$OUTPUT_ARCHIVE/Products/Applications/TDLibKitSizeHost.app"
