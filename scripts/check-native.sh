#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

cd "$ROOT_DIR"

python3 scripts/native_versions.py --verify

./scripts/generate_native_schema.py --check

artifact="$ROOT_DIR/Artifacts/TdStatic.xcframework"
if [[ "${TDLIBKIT_USE_LOCAL_TDSTATIC:-0}" != "1" ]]; then
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
if rg -n '\.unsafeFlags\(' Package.swift; then
  echo "error: unsafeFlags prevent semantic-version package dependencies" >&2
  exit 1
fi

echo "native graph gate passed"
