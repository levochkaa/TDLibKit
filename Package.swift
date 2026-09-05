// swift-tools-version: 6.0

import PackageDescription
import Foundation

// Explicit opt-in for maintainers testing a freshly built, unpublished binary.
let useLocalTDStatic = ProcessInfo.processInfo.environment["TDLIBKIT_USE_LOCAL_TDSTATIC"] == "1"
let tdStatic: Target = useLocalTDStatic
    ? .binaryTarget(name: "TdStatic", path: "Artifacts/TdStatic.xcframework")
    : .binaryTarget(
        name: "TdStatic",
        url: "https://github.com/levochkaa/TDLibKit/releases/download/tdstatic-1.8.67-d1085f9c-preview.1/TdStatic.xcframework.zip",
        checksum: "9c4080f92cea892dd110ffa78c7cf4762fb2cb6c53ced6c107f1cd17eb048783"
    )

let package = Package(
    name: "TDLibKit",
    platforms: [
        .iOS(.v15),
        .macOS(.v12),
        .watchOS(.v8),
        .tvOS(.v15),
        .visionOS(.v1)
    ],
    products: [
        .library(name: "TDLibKit", type: .static, targets: ["TDLibKit"]),
        .library(name: "TDLibKitShared", type: .dynamic, targets: ["TDLibKit"]),
        .library(name: "TDLibCxxBridge", type: .static, targets: ["TDLibCxxBridge"])
    ],
    targets: [
        tdStatic,
        .target(
            name: "TDLibCxxBridge",
            dependencies: ["TdStatic"],
            path: "Sources/TDLibCxxBridge",
            publicHeadersPath: "include",
            cxxSettings: [
                .unsafeFlags([
                    "-std=c++17",
                    "-fno-exceptions",
                    "-fno-rtti",
                    "-fvisibility=hidden",
                    "-fvisibility-inlines-hidden"
                ])
            ],
            linkerSettings: [
                .linkedLibrary("c++"),
                .linkedLibrary("z")
            ]
        ),
        .target(
            name: "TDLibKit",
            dependencies: ["TDLibCxxBridge"],
            path: "Sources/TDLibKitNative",
            swiftSettings: [
                .interoperabilityMode(.Cxx)
            ]
        ),
        .testTarget(
            name: "TDLibKitTests",
            dependencies: ["TDLibKit", "TDLibCxxBridge"],
            path: "Tests/TDLibKitNativeTests",
            swiftSettings: [
                .interoperabilityMode(.Cxx)
            ]
        )
    ],
    cxxLanguageStandard: .cxx17
)
