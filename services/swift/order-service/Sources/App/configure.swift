import Vapor
import Fluent
import FluentPostgresDriver
import Redis

public func configure(_ app: Application) async throws {
    let port = Int(Environment.get("PORT") ?? "8083") ?? 8083
    app.http.server.configuration.port = port
    app.http.server.configuration.hostname = "0.0.0.0"

    let databaseURL = Environment.get("DATABASE_URL")
        ?? "postgres://research:research_secret_2025@localhost:5432/swift_order_db"
    // 2 × 10 event loops = 20, matching Java HikariCP max-pool-size.
    try app.databases.use(.postgres(url: databaseURL, maxConnectionsPerEventLoop: 2), as: .psql)

    let redisURL = Environment.get("REDIS_URL") ?? "redis://localhost:6379"
    app.redis.configuration = try RedisConfiguration(url: redisURL)

    app.migrations.add(CreateOrder())
    try await app.autoMigrate()

    app.middleware.use(RequestMetricsMiddleware(service: "order-service"))
    app.middleware.use(ErrorMiddleware.default(environment: app.environment))

    let productURL = Environment.get("PRODUCT_SERVICE_URL") ?? "http://localhost:8082"
    let userURL    = Environment.get("USER_SERVICE_URL")    ?? "http://localhost:8081"

    app.get("health") { _ in
        ["status": "ok", "service": "swift-order-service", "language": "swift"]
    }
    app.get("metrics") { _ -> Response in
        let body = await MetricsCollector.shared.text(service: "order-service")
        return Response(status: .ok,
                       headers: ["Content-Type": "text/plain; version=0.0.4"],
                       body: .init(string: body))
    }

    let orders = app.grouped("orders")
    try orders.register(collection: OrderController(productServiceURL: productURL, userServiceURL: userURL))
}
