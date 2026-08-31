#!/bin/sh
set -ex

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"

PLATFORM="$1"
OS_LIST="$2"
NAME="$3"
ACTIONS=${4:-test}

if [[ $PLATFORM = "iOS-simulator" ]]; then
    SDK="iphonesimulator"
    TRIPLE="arm64-apple-ios15.0-simulator"
    if [[ -n $NAME ]]; then
        DESTINATION="platform=iOS Simulator,name=${NAME}"
    else
        DESTINATION="generic/platform=iOS Simulator"
    fi
elif [[ $PLATFORM = "macOS" ]]; then
    SDK="macosx"
    DESTINATION="platform=OS X"
elif [[ $PLATFORM = "watchOS-simulator" ]]; then
    SDK="watchsimulator"
    TRIPLE="arm64-apple-watchos8.0-simulator"
    if [[ -n $NAME ]]; then
        DESTINATION="platform=watchOS Simulator,name=${NAME}"
    else
        DESTINATION="generic/platform=watchOS Simulator"
    fi
elif [[ $PLATFORM = "tvOS-simulator" ]]; then
    SDK="appletvsimulator"
    TRIPLE="arm64-apple-tvos15.0-simulator"
    if [[ -n $NAME ]]; then
        DESTINATION="platform=tvOS Simulator,name=${NAME}"
    else
        DESTINATION="generic/platform=tvOS Simulator"
    fi
elif [[ $PLATFORM = "visionOS-simulator" ]]; then
    SDK="xrsimulator"
    TRIPLE="arm64-apple-xros1.0-simulator"
    if [[ -n $NAME ]]; then
        DESTINATION="platform=visionOS Simulator,name=${NAME}"
    else
        DESTINATION="generic/platform=visionOS Simulator"
    fi
else
    echo "Unknown SDK for platform \"$PLATFORM\""
    exit 1
fi

if [[ -z $NAME && $PLATFORM != "macOS" ]]; then
    if [[ $ACTIONS != "build" ]]; then
        echo "A named simulator is required for action \"$ACTIONS\""
        exit 1
    fi
    SDK_PATH="$(xcrun --sdk "$SDK" --show-sdk-path)"
    if [[ $PLATFORM = "visionOS-simulator" ]]; then
        # SwiftPM 6.3 doesn't propagate binary-target headers for xros triples
        # without an installed visionOS platform runtime. Compile against the
        # exact selected XCFramework slice explicitly in that SDK-only setup.
        swift build \
            --scratch-path "$ROOT_DIR/.build/visionos-gate" \
            --triple "$TRIPLE" \
            --sdk "$SDK_PATH" \
            -Xcxx "-I$ROOT_DIR/Artifacts/TdStatic.xcframework/xros-arm64-simulator/Headers"
    else
        swift build --triple "$TRIPLE" --sdk "$SDK_PATH"
    fi
    exit
fi

if [[ $OS_LIST != "" ]]; then
    for OS in $OS_LIST; do
        xcodebuild -scheme TDLibKit -sdk ${SDK} -destination "${DESTINATION},OS=${OS}" clean ${ACTIONS}
    done
else
    xcodebuild -scheme TDLibKit -sdk ${SDK} -destination "${DESTINATION}" clean ${ACTIONS}
fi
