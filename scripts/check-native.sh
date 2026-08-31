#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PINNED_COMMIT="d1085f9cebc5a62379991ae1652673954f229c1f"

cd "$ROOT_DIR"

actual_commit="$(git -C Vendor/td rev-parse HEAD)"
[[ "$actual_commit" == "$PINNED_COMMIT" ]] || {
  echo "error: Vendor/td is $actual_commit, expected $PINNED_COMMIT" >&2
  exit 1
}

./scripts/generate_native_schema.py --check

artifact="$ROOT_DIR/Artifacts/TdStatic.xcframework"
if [[ ! -d "$artifact" ]]; then
  swift package resolve
  artifact="$(find "$ROOT_DIR/.build/artifacts" -type d -name TdStatic.xcframework -print -quit)"
  [[ -n "$artifact" ]] || {
    echo "error: SwiftPM did not resolve TdStatic.xcframework" >&2
    exit 1
  }
fi
./scripts/tdlib-native.sh verify --artifact "$artifact"

banned='TDLibFramework|TDLibKitDynamic|TdJsonStatic|TdJson|td_json_client|td_send|td_receive|td_execute|JSONEncoder|JSONDecoder|JSONSerialization|@extra|UUID'
checked_paths=(Package.swift Sources/TDLibCxxBridge Sources/TDLibKitNative Tests/TDLibKitNativeTests)
[[ ! -f Package.resolved ]] || checked_paths+=(Package.resolved)
if rg -n "$banned" "${checked_paths[@]}"; then
  echo "error: forbidden transport/dependency API found" >&2
  exit 1
fi

rg -q '#include "td/telegram/Client.h"' Sources/TDLibCxxBridge/Bridge.cpp
rg -q '#include "td/telegram/td_api.h"' Sources/TDLibCxxBridge/Bridge.cpp
rg -q '#include "td/telegram/td_api.hpp"' Sources/TDLibCxxBridge/Bridge.cpp
rg -q 'interoperabilityMode\(\.Cxx\)' Package.swift

echo "native graph gate passed"
