// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "OrderService",
    platforms: [.macOS(.v13)],
    dependencies: [
        .package(url: "https://github.com/vapor/vapor.git",                  from: "4.99.3"),
        .package(url: "https://github.com/vapor/fluent.git",                 from: "4.9.0"),
        .package(url: "https://github.com/vapor/fluent-postgres-driver.git", from: "2.9.0"),
        .package(url: "https://github.com/vapor/redis.git",                  from: "4.10.0"),
    ],
    targets: [
        .executableTarget(
            name: "App",
            dependencies: [
                .product(name: "Vapor",                package: "vapor"),
                .product(name: "Fluent",               package: "fluent"),
                .product(name: "FluentPostgresDriver", package: "fluent-postgres-driver"),
                .product(name: "Redis",                package: "redis"),
            ],
            path: "Sources/App"
        ),
    ]
)
