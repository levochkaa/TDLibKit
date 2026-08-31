# TDLibKit arm64 Release size

The benchmark is a minimal UIKit host that creates a client and requests the
TDLib version. Both variants use the same Release settings, arm64 device
destination, dead stripping, stripping, and link-map generation. The measured
payload is the app executable plus every file under `Frameworks`; dSYM content
is excluded.

| Variant | Executable | Frameworks | Total | Delta |
| --- | ---: | ---: | ---: | ---: |
| TDLibKit 1.5.2 / JSON baseline | 50,303,240 | 33,887 | 50,337,127 | — |
| TDLibKit 2 native / full schema / Release `-O3` | 30,983,288 | 0 | 30,983,288 | -19,353,839 (-38.45%) |
| TDLibKit 2 native / full schema / MinSizeRel `-Os` | 25,546,472 | 0 | 25,546,472 | -24,790,655 (-49.25%) |
| TDLibKit 2 native / full schema / Release `-Oz` | 22,340,824 | 0 | 22,340,824 | -27,996,303 (-55.62%) |

The earlier 125 MB figure was an estimate, not a measured limit. The stored
regression threshold is therefore one byte below the actual same-host baseline:
`50,337,126`.

Build command:

```sh
cd Benchmarks/SizeHost
xcodegen generate --spec project.yml
xcodebuild -project TDLibKitSizeHost.xcodeproj \
  -scheme TDLibKitSizeHost -configuration Release -sdk iphoneos \
  -destination 'generic/platform=iOS' -derivedDataPath .derived-data \
  -archivePath .archives/NativeFullSchema.xcarchive archive \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  ONLY_ACTIVE_ARCH=YES ARCHS=arm64 SKIP_INSTALL=NO
../../scripts/check-size.sh
```

Release `-Oz` is selected because it is the smallest installed-app result and
passes the complete macOS/iOS test suite plus watchOS/tvOS/visionOS compile
gates. ThinLTO is rejected: its bitcode archive cannot be accepted by
`xcodebuild -create-xcframework -library`, so it never reaches the host-app
test/measurement gate.

The exact pre-change archive is retained locally as `Baseline.xcarchive`.
`Baseline/` contains an exact-version source rebuild for regenerating a baseline
link map; the original raw map was not preserved with the archive, so the
reproduced map is identified separately rather than presented as byte-identical
to the 50,337,127-byte artifact. `NativeFullSchema-LinkMap-arm64.txt.gz` is the
compressed final map.

The final link map contains `TDLibCxxBridge.o`,
`libTdStatic.a(Client.cpp.o)`, and `libTdStatic.a(GitCommitHash.cpp.o)`.
It contains zero `td_api_json`, `ClientJson`, `td_json_client`, `td_send`,
`td_receive`, or `td_execute` entries.
