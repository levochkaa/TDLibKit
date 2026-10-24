// swift-tools-version: 6.0

import PackageDescription
import Foundation

// Explicit opt-in for maintainers testing a freshly built, unpublished binary.
let useLocalTDStatic = ProcessInfo.processInfo.environment["TDLIBKIT_USE_LOCAL_TDSTATIC"] == "1"
let tdStatic: Target = useLocalTDStatic
    ? .binaryTarget(name: "TdStatic", path: "Artifacts/TdStatic.xcframework")
    : .binaryTarget(
        name: "TdStatic",
        url: "https://github.com/levochkaa/TDLibKit/releases/download/2.0.1-tdlib-1.8.69-ea3f69ce/TdStatic.xcframework.zip",
        checksum: "2586dc135df4557ff413c6658373b1efde85c9693928199019aef9ca4e54b8d3"
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
