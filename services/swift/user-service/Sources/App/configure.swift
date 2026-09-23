import Vapor
import Fluent
import FluentPostgresDriver
import Redis

public func configure(_ app: Application) async throws {
    let port = Int(Environment.get("PORT") ?? "8081") ?? 8081
    app.http.server.configuration.port = port
    app.http.server.configuration.hostname = "0.0.0.0"

    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    ContentConfiguration.global.use(encoder: encoder, for: .json)
    ContentConfiguration.global.use(decoder: decoder, for: .json)

    let databaseURL = Environment.get("DATABASE_URL")
        ?? "postgres://research:research_secret_2025@localhost:5432/swift_user_db"
    // Connection-pool parity with Java HikariCP maximum-pool-size.
    // Vapor sizes its pool per event loop, Hikari sizes it per process, so the
    // per-loop figure is derived from the pinned event-loop count rather than
    // hard coded. DB_POOL_PER_LOOP x NIO_SINGLETON_GROUP_LOOP_COUNT = HikariCP max.
    let poolPerLoop = Int(Environment.get("DB_POOL_PER_LOOP") ?? "2") ?? 2
    try app.databases.use(.postgres(url: databaseURL, maxConnectionsPerEventLoop: poolPerLoop), as: .psql)

    let redisURL = Environment.get("REDIS_URL") ?? "redis://localhost:6379"
    app.redis.configuration = try RedisConfiguration(url: redisURL)

    // Match Java BCryptPasswordEncoder(10).
    app.passwords.use(.bcrypt(cost: 10))

    app.migrations.add(CreateUser())
    try await app.autoMigrate()

    app.middleware.use(RequestMetricsMiddleware(service: "user-service"))
    app.middleware.use(ErrorMiddleware.default(environment: app.environment))

    try routes(app)
}
