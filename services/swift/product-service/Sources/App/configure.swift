import Vapor
import Fluent
import FluentPostgresDriver
import Redis

public func configure(_ app: Application) async throws {
    let port = Int(Environment.get("PORT") ?? "8082") ?? 8082
    app.http.server.configuration.port = port
    app.http.server.configuration.hostname = "0.0.0.0"

    let databaseURL = Environment.get("DATABASE_URL")
        ?? "postgres://research:research_secret_2025@localhost:5432/swift_product_db"
    // 2 × 10 event loops = 20, matching Java HikariCP max-pool-size.
    try app.databases.use(.postgres(url: databaseURL, maxConnectionsPerEventLoop: 2), as: .psql)

    let redisURL = Environment.get("REDIS_URL") ?? "redis://localhost:6379"
    app.redis.configuration = try RedisConfiguration(url: redisURL)

    app.migrations.add(CreateProduct())
    try await app.autoMigrate()

    app.middleware.use(RequestMetricsMiddleware(service: "product-service"))
    app.middleware.use(ErrorMiddleware.default(environment: app.environment))

    app.get("health") { _ in
        ["status": "ok", "service": "swift-product-service", "language": "swift"]
    }
    app.get("metrics") { _ -> Response in
        let body = await MetricsCollector.shared.text(service: "product-service")
        return Response(status: .ok,
                       headers: ["Content-Type": "text/plain; version=0.0.4"],
                       body: .init(string: body))
    }

    let products = app.grouped("products")
    try products.register(collection: ProductController())
}
