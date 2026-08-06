// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CaucoHost",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "CaucoHostCore", targets: ["CaucoHostCore"]),
        .executable(name: "CaucoHost", targets: ["CaucoHost"])
    ],
    targets: [
        .target(name: "CaucoHostCore"),
        .executableTarget(name: "CaucoHost", dependencies: ["CaucoHostCore"]),
        .testTarget(name: "CaucoHostCoreTests", dependencies: ["CaucoHostCore"])
    ]
)
