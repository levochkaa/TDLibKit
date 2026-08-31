# Binary evidence

The exact pre-change and final arm64 executables are retained in the local
benchmark archives. Their SHA-256 values are:

- baseline: `fd23d54636cda9bbac950721d03d44f720a87b5c88ec083cc0c69b90733f2af1`;
- native full schema: `fdefd21f0553acbe0b2c1bc8786c2e6c67c1ac19c48c3182057c66c3de025fd6`.

Selected `xcrun size -m` values:

| Mach-O region | TDLibKit 1.5.2 | TDLibKit 2 native |
| --- | ---: | ---: |
| `__TEXT` segment | 42,795,008 | 18,874,368 |
| `__text` section | 37,350,836 | 16,646,160 |
| `__TEXT,__const` | 1,853,263 | 514,912 |
| `__DATA_CONST` segment | 2,637,824 | 1,671,168 |
| `__DATA` segment | 3,866,624 | 245,760 |
| `__LINKEDIT` segment | 4,423,680 | 1,589,248 |

`otool -L` shows no TDLib dynamic library in the final app. Both hosts load the
system C++, zlib, Foundation, UIKit, and Swift runtime libraries. The baseline
contains a 33,887-byte codeless `TDLibFramework.framework`; the final
`Frameworks` payload is zero.

The final map is `NativeFullSchema-LinkMap-arm64.txt.gz`. It names
`TDLibCxxBridge.o`, `libTdStatic.a(Client.cpp.o)`, and
`libTdStatic.a(GitCommitHash.cpp.o)`, and contains zero matches for
`td_api_json`, `ClientJson`, `td_json_client`, `td_send`, `td_receive`, or
`td_execute`. The stripped baseline exposes seven defined global symbols in
`xcrun nm`; the final executable exposes only its Mach-O header symbol, which is
consistent with hidden TDLib/bridge visibility.

The original raw baseline map was not retained in its archive. The exact-version
rebuild under `Baseline/` produced a 49,712,999-byte app, 624,128 bytes below the
preserved 50,337,127-byte artifact. Its map is therefore stored as
`Baseline-Reproduced-LinkMap-arm64.txt.gz` and is explicitly not claimed to be
byte-identical evidence for the original binary.
