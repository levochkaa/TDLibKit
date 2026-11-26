// swift-tools-version: 6.0

import PackageDescription
import Foundation

// Explicit opt-in for maintainers testing a freshly built, unpublished binary.
let useLocalTDStatic = ProcessInfo.processInfo.environment["TDLIBKIT_USE_LOCAL_TDSTATIC"] == "1"
let tdStatic: Target = useLocalTDStatic
    ? .binaryTarget(name: "TdStatic", path: "Artifacts/TdStatic.xcframework")
    : .binaryTarget(
        name: "TdStatic",
        url: "https://github.com/levochkaa/TDLibKit/releases/download/2.0.2-tdlib-1.8.71-e7ac61dd/TdStatic.xcframework.zip",
        checksum: "70608b6d0638841779238f741abf51412124b00f278b9c48fb024db42e6f7eac"
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
