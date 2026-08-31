#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
TD_DIR="$ROOT_DIR/Vendor/td"
BUILD_ROOT="$ROOT_DIR/.build/tdlib-native"
HEADERS_DIR="$ROOT_DIR/Native/Headers"
PINNED_COMMIT="d1085f9cebc5a62379991ae1652673954f229c1f"
OPENSSL_SUPPORT_COMMIT="6f43aba0ddd5a9f52f39775d0141bd4363614020"
OPENSSL_VERSION="3.1.5"
BUILD_JOBS=8

usage() {
  echo "Usage:"
  echo "  ./scripts/tdlib-native.sh generate"
  echo "  ./scripts/tdlib-native.sh openssl --platform <platform|all> [options]"
  echo "  ./scripts/tdlib-native.sh build --platform <platform> [options]"
  echo "  ./scripts/tdlib-native.sh universal --output <archive> <thin archives...>"
  echo "  ./scripts/tdlib-native.sh xcframework --macos <archive> --ios <archive> --ios-simulator <archive> [platform archives] [--output <path>]"
  echo "  ./scripts/tdlib-native.sh verify [--artifact <path>]"
  echo ""
  echo "Build options:"
  echo "  --configuration <Release|MinSizeRel>  Default: Release"
  echo "  --optimization <default|oz>           Default: default"
  echo "  --lto <on|off>                        Default: off"
  echo "  --openssl <prefix>                    Prefix containing include/, lib/libssl.a and lib/libcrypto.a"
  echo "  --arch <arm64|x86_64>                 Default: arm64"
  echo "  --output <archive>                    Output libTdStatic.a"
  echo "  --jobs <count>                        Parallel compile jobs. Default: 8"
  echo "  --skip-generate                       Reuse already generated pinned TD sources"
  echo ""
  echo "OpenSSL options:"
  echo "  --platform <platform|all>             Build an OpenSSL 3.1.5 prefix"
  echo "  --arch <arm64|x86_64>                 Default: arm64"
  echo "  --output-root <directory>             Default: .build/tdlib-native/openssl"
  echo "  --xcode <Xcode.app>                   Default: /Applications/Xcode-26.6.0.app"
}

fail() {
  echo "error: $*" >&2
  exit 1
}

verify_pin() {
  [[ -d "$TD_DIR/.git" || -f "$TD_DIR/.git" ]] || fail "Vendor/td submodule is not initialized"
  local actual
  actual="$(git -C "$TD_DIR" rev-parse HEAD)"
  [[ "$actual" == "$PINNED_COMMIT" ]] || fail "Vendor/td is $actual, expected $PINNED_COMMIT"
}

generate_sources() {
  verify_pin
  local generator="$BUILD_ROOT/generator"
  cmake -S "$TD_DIR" -B "$generator" \
    -DTD_GENERATE_SOURCE_FILES=ON \
    -DBUILD_TESTING=OFF \
    -DTD_ENABLE_JNI=OFF \
    -DTD_ENABLE_DOTNET=OFF \
    -DTD_INSTALL_SHARED_LIBRARIES=OFF \
    -DTD_INSTALL_STATIC_LIBRARIES=ON \
    -DCMAKE_BUILD_TYPE=Release
  cmake --build "$generator" --parallel "$BUILD_JOBS"

  mkdir -p "$HEADERS_DIR/td/telegram" "$HEADERS_DIR/td/tl"
  cp "$TD_DIR/td/telegram/Client.h" "$HEADERS_DIR/td/telegram/Client.h"
  cp "$TD_DIR/td/generate/auto/td/telegram/td_api.h" "$HEADERS_DIR/td/telegram/td_api.h"
  cp "$TD_DIR/td/generate/auto/td/telegram/td_api.hpp" "$HEADERS_DIR/td/telegram/td_api.hpp"
  cp "$TD_DIR/td/tl/TlObject.h" "$HEADERS_DIR/td/tl/TlObject.h"
}

build_openssl() {
  local platform=""
  local arch="arm64"
  local output_root="$BUILD_ROOT/openssl"
  local xcode="/Applications/Xcode-26.6.0.app"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --platform) platform="$2"; shift 2 ;;
      --arch) arch="$2"; shift 2 ;;
      --output-root) output_root="$2"; shift 2 ;;
      --xcode) xcode="$2"; shift 2 ;;
      *) fail "Unknown OpenSSL option: $1" ;;
    esac
  done

  case "$platform" in
    all|macos|ios|ios-simulator|watchos|watchos-simulator|tvos|tvos-simulator|visionos|visionos-simulator) ;;
    *) fail "unsupported OpenSSL --platform: $platform" ;;
  esac
  [[ "$arch" == "arm64" || "$arch" == "x86_64" ]] ||
    fail "--arch must be arm64 or x86_64"
  if [[ "$arch" == "x86_64" ]]; then
    case "$platform" in
      ios-simulator|watchos-simulator|tvos-simulator|visionos-simulator) ;;
      *) fail "x86_64 OpenSSL is supported only for a single simulator platform" ;;
    esac
  fi
  [[ -d "$xcode/Contents/Developer" ]] || fail "Xcode not found: $xcode"
  [[ "$output_root" == /* ]] || output_root="$ROOT_DIR/$output_root"

  local support_dir="$BUILD_ROOT/Python-Apple-support"
  if [[ ! -d "$support_dir/.git" ]]; then
    [[ ! -e "$support_dir" ]] || fail "$support_dir exists but is not a Git checkout"
    git init "$support_dir"
    git -C "$support_dir" remote add origin https://github.com/beeware/Python-Apple-support.git
    git -C "$support_dir" fetch --depth 1 origin "$OPENSSL_SUPPORT_COMMIT"
    git -C "$support_dir" checkout --detach FETCH_HEAD
  fi

  local actual_support_commit
  actual_support_commit="$(git -C "$support_dir" rev-parse HEAD)"
  [[ "$actual_support_commit" == "$OPENSSL_SUPPORT_COMMIT" ]] ||
    fail "Python-Apple-support is $actual_support_commit, expected $OPENSSL_SUPPORT_COMMIT"

  local patch="$TD_DIR/example/ios/Python-Apple-support.patch"
  if git -C "$support_dir" apply --check "$patch" 2>/dev/null; then
    git -C "$support_dir" apply "$patch"
  elif ! git -C "$support_dir" apply --reverse --check "$patch" 2>/dev/null; then
    fail "Python-Apple-support checkout has changes incompatible with the pinned TD patch"
  fi
  grep -q "^OPENSSL_VERSION=$OPENSSL_VERSION$" "$support_dir/Makefile" ||
    fail "patched Python-Apple-support does not select OpenSSL $OPENSSL_VERSION"

  local platforms=()
  if [[ "$platform" == "all" ]]; then
    platforms=(macos ios ios-simulator watchos watchos-simulator tvos tvos-simulator visionos visionos-simulator)
  else
    platforms=("$platform")
  fi

  local item support_name source_prefix destination library archs
  for item in "${platforms[@]}"; do
    case "$item" in
      macos) support_name="macOS" ;;
      ios) support_name="iOS" ;;
      ios-simulator) support_name="iOS-simulator" ;;
      watchos) support_name="watchOS" ;;
      watchos-simulator) support_name="watchOS-simulator" ;;
      tvos) support_name="tvOS" ;;
      tvos-simulator) support_name="tvOS-simulator" ;;
      visionos) support_name="visionOS" ;;
      visionos-simulator) support_name="visionOS-simulator" ;;
    esac

    DEVELOPER_DIR="$xcode/Contents/Developer" \
      SOURCE_DATE_EPOCH=1 ZERO_AR_DATE=1 \
      make -C "$support_dir" "OpenSSL-$support_name"

    source_prefix="$support_dir/merge/$support_name/openssl"
    [[ -d "$source_prefix/include/openssl" ]] || fail "OpenSSL headers missing for $item"
    destination="$output_root/$item"
    rm -rf "$destination"
    mkdir -p "$destination/lib"
    cp -R "$source_prefix/include" "$destination/include"
    for library in libssl.a libcrypto.a; do
      [[ -f "$source_prefix/lib/$library" ]] || fail "$library missing for $item"
      archs="$(lipo -archs "$source_prefix/lib/$library")"
      if [[ "$archs" == "$arch" ]]; then
        cp "$source_prefix/lib/$library" "$destination/lib/$library"
      else
        lipo "$source_prefix/lib/$library" -thin "$arch" -output "$destination/lib/$library"
      fi
      [[ "$(lipo -archs "$destination/lib/$library")" == "$arch" ]] ||
        fail "$destination/lib/$library is not $arch-only"
    done
    echo "$destination"
  done
}

find_archive() {
  local build_dir="$1"
  local name="$2"
  local path
  path="$(find "$build_dir" -type f -name "lib${name}.a" -print -quit)"
  [[ -n "$path" ]] || fail "lib${name}.a was not produced in $build_dir"
  echo "$path"
}

build_tdstatic() {
  local platform=""
  local arch="arm64"
  local configuration="Release"
  local optimization="default"
  local lto="off"
  local openssl=""
  local output=""
  local skip_generate="false"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --platform) platform="$2"; shift 2 ;;
      --arch) arch="$2"; shift 2 ;;
      --configuration) configuration="$2"; shift 2 ;;
      --optimization) optimization="$2"; shift 2 ;;
      --lto) lto="$2"; shift 2 ;;
      --openssl) openssl="$2"; shift 2 ;;
      --output) output="$2"; shift 2 ;;
      --jobs) BUILD_JOBS="$2"; shift 2 ;;
      --skip-generate) skip_generate="true"; shift ;;
      *) fail "Unknown build option: $1" ;;
    esac
  done

  case "$platform" in
    macos|ios|ios-simulator|watchos|watchos-simulator|tvos|tvos-simulator|visionos|visionos-simulator) ;;
    *) fail "unsupported --platform: $platform" ;;
  esac
  [[ "$configuration" == "Release" || "$configuration" == "MinSizeRel" ]] ||
    fail "--configuration must be Release or MinSizeRel"
  [[ "$optimization" == "default" || "$optimization" == "oz" ]] ||
    fail "--optimization must be default or oz"
  [[ "$lto" == "on" || "$lto" == "off" ]] || fail "--lto must be on or off"
  [[ "$arch" == "arm64" || "$arch" == "x86_64" ]] ||
    fail "--arch must be arm64 or x86_64"
  if [[ "$arch" == "x86_64" ]]; then
    case "$platform" in
      macos|ios-simulator|watchos-simulator|tvos-simulator|visionos-simulator) ;;
      *) fail "x86_64 is supported only for macOS and simulator platforms" ;;
    esac
  fi
  [[ "$BUILD_JOBS" =~ ^[1-9][0-9]*$ ]] || fail "--jobs must be a positive integer"

  if [[ -z "$openssl" && "$platform" == "macos" ]]; then
    openssl="/opt/homebrew/opt/openssl@3"
  fi
  [[ -n "$openssl" ]] || fail "--openssl is required for $platform"
  openssl="$(cd "$openssl" && pwd -P)"
  [[ -f "$openssl/lib/libssl.a" ]] || fail "Missing $openssl/lib/libssl.a"
  [[ -f "$openssl/lib/libcrypto.a" ]] || fail "Missing $openssl/lib/libcrypto.a"
  [[ -d "$openssl/include/openssl" ]] || fail "Missing OpenSSL headers in $openssl/include"

  if [[ "$skip_generate" != "true" ]]; then
    generate_sources
  fi

  local variant="${platform}-${configuration}-${optimization}-lto-${lto}"
  [[ "$arch" == "arm64" ]] || variant="${variant}-${arch}"
  local build_dir="$BUILD_ROOT/build/$variant"
  local product_dir="$BUILD_ROOT/products/$variant"
  mkdir -p "$build_dir" "$product_dir"
  if [[ -z "$output" ]]; then
    output="$product_dir/libTdStatic.a"
  elif [[ "$output" != /* ]]; then
    output="$ROOT_DIR/$output"
  fi
  mkdir -p "$(dirname "$output")"

  local lto_flag="OFF"
  [[ "$lto" == "on" ]] && lto_flag="ON"

  local c_flags="-DNDEBUG -ffunction-sections -fdata-sections -fvisibility=hidden"
  local cxx_flags="$c_flags -fvisibility-inlines-hidden -fno-exceptions -fno-rtti"
  if [[ "$optimization" == "oz" ]]; then
    c_flags="-Oz $c_flags"
    cxx_flags="-Oz $cxx_flags"
  elif [[ "$configuration" == "MinSizeRel" ]]; then
    c_flags="-Os $c_flags"
    cxx_flags="-Os $cxx_flags"
  else
    c_flags="-O3 $c_flags"
    cxx_flags="-O3 $cxx_flags"
  fi

  local platform_args=()
  local cmake_fresh=()
  if [[ "$platform" == "macos" ]]; then
    platform_args+=(
      "-DCMAKE_OSX_ARCHITECTURES=$arch"
      "-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0"
    )
  else
    local ios_platform=""
    local deployment_target=""
    local target_triple=""
    case "$platform" in
      ios) ios_platform="OS"; deployment_target="15.0" ;;
      ios-simulator) ios_platform="SIMULATOR"; deployment_target="15.0" ;;
      watchos) ios_platform="WATCHOS"; deployment_target="8.0" ;;
      watchos-simulator) ios_platform="WATCHSIMULATOR"; deployment_target="8.0" ;;
      tvos) ios_platform="TVOS"; deployment_target="15.0" ;;
      tvos-simulator) ios_platform="TVSIMULATOR"; deployment_target="15.0" ;;
      visionos) ios_platform="VISIONOS"; target_triple="$arch-apple-xros1.0" ;;
      visionos-simulator) ios_platform="VISIONSIMULATOR"; target_triple="$arch-apple-xros1.0-simulator" ;;
    esac
    platform_args+=(
      "-DCMAKE_TOOLCHAIN_FILE=$TD_DIR/CMake/iOS.cmake"
      "-DIOS_PLATFORM=$ios_platform"
      "-DIOS_ARCH=$arch"
      "-DIOS_DEPLOYMENT_TARGET=$deployment_target"
    )
    if [[ -n "$target_triple" ]]; then
      # TD's pinned iOS.cmake spells the visionOS deployment option as
      # -mxros-version-min, which current Apple Clang doesn't accept. Keep the
      # upstream file immutable and select the canonical target triple here.
      platform_args+=(
        "-DCMAKE_C_FLAGS=-target $target_triple"
        "-DCMAKE_CXX_FLAGS=-target $target_triple"
        "-DCMAKE_EXE_LINKER_FLAGS=-target $target_triple"
      )
      cmake_fresh=(--fresh)
    fi
  fi

  cmake ${cmake_fresh[@]+"${cmake_fresh[@]}"} -S "$TD_DIR" -B "$build_dir" \
    "${platform_args[@]}" \
    -DBUILD_TESTING=OFF \
    -DTD_ENABLE_JNI=OFF \
    -DTD_ENABLE_DOTNET=OFF \
    -DTD_ENABLE_LTO="$lto_flag" \
    -DTD_INSTALL_SHARED_LIBRARIES=OFF \
    -DTD_INSTALL_STATIC_LIBRARIES=ON \
    -DOPENSSL_FOUND=ON \
    -DOPENSSL_INCLUDE_DIR="$openssl/include" \
    -DOPENSSL_SSL_LIBRARY="$openssl/lib/libssl.a" \
    -DOPENSSL_CRYPTO_LIBRARY="$openssl/lib/libcrypto.a" \
    -DOPENSSL_LIBRARIES="$openssl/lib/libcrypto.a;$openssl/lib/libssl.a" \
    -DCMAKE_BUILD_TYPE="$configuration" \
    -DCMAKE_C_FLAGS_RELEASE="$c_flags" \
    -DCMAKE_CXX_FLAGS_RELEASE="$cxx_flags" \
    -DCMAKE_C_FLAGS_MINSIZEREL="$c_flags" \
    -DCMAKE_CXX_FLAGS_MINSIZEREL="$cxx_flags"

  ZERO_AR_DATE=1 cmake --build "$build_dir" --target tdclient --parallel "$BUILD_JOBS"

  local archives=()
  local name
  for name in tdclient tdcore tdapi tdmtproto tdactor tdnet tddb tde2e tdutils tdsqlite; do
    archives+=("$(find_archive "$build_dir" "$name")")
  done
  archives+=("$openssl/lib/libssl.a" "$openssl/lib/libcrypto.a")

  libtool -static -D -o "$output" "${archives[@]}"
  ranlib "$output"
  verify_thin_archive "$output"
  echo "$output"
}

verify_thin_archive() {
  local archive="$1"
  local banned_members='^(td_api_json_[0-9]+\.cpp\.o|ClientJson\.cpp\.o|td_json_client\.cpp\.o|td_log\.cpp\.o)$'
  local banned_symbols='(_td_send$|_td_receive$|_td_execute$|td_json_client|ClientJson)'

  if ar -t "$archive" | grep -E "$banned_members"; then
    fail "JSON transport object found in $archive"
  fi
  if nm -gU "$archive" 2>/dev/null | grep -E "$banned_symbols"; then
    fail "JSON transport symbol found in $archive"
  fi
}

verify_artifact() {
  local artifact="$ROOT_DIR/Artifacts/TdStatic.xcframework"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --artifact) artifact="$2"; shift 2 ;;
      *) fail "Unknown verify option: $1" ;;
    esac
  done
  [[ "$artifact" == /* ]] || artifact="$ROOT_DIR/$artifact"
  [[ -d "$artifact" ]] || fail "Artifact not found: $artifact"

  local temp_dir
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/tdlibkit-verify.XXXXXX")"
  trap 'rm -rf "$temp_dir"' EXIT

  local library
  while IFS= read -r library; do
    local archs
    archs="$(lipo -archs "$library")"
    local arch
    for arch in $archs; do
      local thin="$temp_dir/$(basename "$library")-$arch.a"
      if [[ "$archs" == "$arch" ]]; then
        cp "$library" "$thin"
      else
        lipo "$library" -thin "$arch" -output "$thin"
      fi
      verify_thin_archive "$thin"
    done
  done < <(find "$artifact" -type f -name '*.a' | sort)

  trap - EXIT
  rm -rf "$temp_dir"
  echo "Verified native-only artifact: $artifact"
}

create_universal_archive() {
  local output=""
  local archives=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --output) output="$2"; shift 2 ;;
      *) archives+=("$1"); shift ;;
    esac
  done
  [[ -n "$output" ]] || fail "universal --output is required"
  [[ "${#archives[@]}" -ge 2 ]] || fail "universal requires at least two thin archives"
  [[ "$output" == /* ]] || output="$ROOT_DIR/$output"
  [[ "$output" != "$ROOT_DIR" && "$output" != "/" ]] || fail "Unsafe output path"

  local resolved=()
  local archive archive_archs all_archs=""
  for archive in "${archives[@]}"; do
    [[ "$archive" == /* ]] || archive="$ROOT_DIR/$archive"
    [[ -f "$archive" ]] || fail "Archive not found: $archive"
    archive_archs="$(lipo -archs "$archive")"
    [[ "$archive_archs" != *" "* ]] || fail "Input must be thin: $archive"
    [[ " $all_archs " != *" $archive_archs "* ]] || fail "Duplicate architecture: $archive_archs"
    all_archs="$all_archs $archive_archs"
    resolved+=("$archive")
  done

  mkdir -p "$(dirname "$output")"
  lipo -create "${resolved[@]}" -output "$output"

  local temp_dir arch thin
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/tdlibkit-universal.XXXXXX")"
  trap 'rm -rf "$temp_dir"' EXIT
  for arch in $(lipo -archs "$output"); do
    thin="$temp_dir/libTdStatic-$arch.a"
    lipo "$output" -thin "$arch" -output "$thin"
    verify_thin_archive "$thin"
  done
  trap - EXIT
  rm -rf "$temp_dir"
  echo "$output"
}

create_xcframework() {
  local macos=""
  local ios=""
  local simulator=""
  local watchos=""
  local watchos_simulator=""
  local tvos=""
  local tvos_simulator=""
  local visionos=""
  local visionos_simulator=""
  local output="$ROOT_DIR/Artifacts/TdStatic.xcframework"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --macos) macos="$2"; shift 2 ;;
      --ios) ios="$2"; shift 2 ;;
      --ios-simulator) simulator="$2"; shift 2 ;;
      --watchos) watchos="$2"; shift 2 ;;
      --watchos-simulator) watchos_simulator="$2"; shift 2 ;;
      --tvos) tvos="$2"; shift 2 ;;
      --tvos-simulator) tvos_simulator="$2"; shift 2 ;;
      --visionos) visionos="$2"; shift 2 ;;
      --visionos-simulator) visionos_simulator="$2"; shift 2 ;;
      --output) output="$2"; shift 2 ;;
      *) fail "Unknown xcframework option: $1" ;;
    esac
  done
  [[ -f "$macos" && -f "$ios" && -f "$simulator" ]] || fail "All three archive paths are required"
  [[ "$output" == /* ]] || output="$ROOT_DIR/$output"
  [[ "$output" != "$ROOT_DIR" && "$output" != "/" ]] || fail "Unsafe output path"
  local arguments=(
    -create-xcframework
    -library "$macos" -headers "$HEADERS_DIR"
    -library "$ios" -headers "$HEADERS_DIR"
    -library "$simulator" -headers "$HEADERS_DIR"
  )
  local optional_library
  for optional_library in "$watchos" "$watchos_simulator" "$tvos" "$tvos_simulator" "$visionos" "$visionos_simulator"; do
    if [[ -n "$optional_library" ]]; then
      [[ -f "$optional_library" ]] || fail "Archive not found: $optional_library"
      arguments+=(-library "$optional_library" -headers "$HEADERS_DIR")
    fi
  done
  rm -rf "$output"
  xcodebuild "${arguments[@]}" -output "$output"
  verify_artifact --artifact "$output"
}

command="${1:-}"
[[ -n "$command" ]] || { usage; exit 1; }
shift

case "$command" in
  generate) generate_sources ;;
  openssl) build_openssl "$@" ;;
  build) build_tdstatic "$@" ;;
  universal) create_universal_archive "$@" ;;
  xcframework) create_xcframework "$@" ;;
  verify) verify_artifact "$@" ;;
  help|--help|-h) usage ;;
  *) usage; fail "Unknown command: $command" ;;
esac
