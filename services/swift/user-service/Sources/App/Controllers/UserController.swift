import Vapor
import Fluent
import Redis

struct UserController: RouteCollection {
    func boot(routes: any RoutesBuilder) throws {
        routes.get(use: list)
        routes.post(use: create)
        routes.group(":userID") { user in
            user.get(use: get)
            user.put(use: update)
            user.delete(use: delete)
        }
    }

    func list(req: Request) async throws -> [UserDTO] {
        let cacheKey = RedisKey("users:list")
        if let cached = try? await req.cacheGetJSON(cacheKey, as: [UserDTO].self) {
            return cached
        }
        let users = try await User.query(on: req.db)
            .sort(\.$createdAt, .descending).limit(100).all()
        let dtos = users.map(UserDTO.init)
        try? await req.cacheSetJSON(cacheKey, value: dtos, ttl: 30)
        return dtos
    }

    func create(req: Request) async throws -> Response {
        try CreateUserRequest.validate(content: req)
        let body = try req.content.decode(CreateUserRequest.self)
        guard try await User.query(on: req.db).filter(\.$email == body.email).first() == nil else {
            throw Abort(.conflict, reason: "Email already registered")
        }
        // Async hash runs on threadPool so the event loop stays free.
        let hash = try await req.password.async.hash(body.password).get()
        let user = User(name: body.name, email: body.email, passwordHash: hash)
        try await user.save(on: req.db)
        await req.cacheDelete(RedisKey("users:list"))
        return try await UserDTO(from: user).encodeResponse(status: .created, for: req)
    }

    func get(req: Request) async throws -> UserDTO {
        guard let id = req.parameters.get("userID", as: UUID.self) else {
            throw Abort(.badRequest)
        }
        let cacheKey = RedisKey("user:\(id)")
        if let cached = try? await req.cacheGetJSON(cacheKey, as: UserDTO.self) {
            return cached
        }
        guard let user = try await User.find(id, on: req.db) else { throw Abort(.notFound) }
        let dto = UserDTO(from: user)
        try? await req.cacheSetJSON(cacheKey, value: dto, ttl: 60)
        return dto
    }

    func update(req: Request) async throws -> UserDTO {
        guard let id = req.parameters.get("userID", as: UUID.self) else { throw Abort(.badRequest) }
        guard let user = try await User.find(id, on: req.db) else { throw Abort(.notFound) }
        let body = try req.content.decode(CreateUserRequest.self)
        user.name  = body.name
        user.email = body.email
        try await user.save(on: req.db)
        await req.cacheDelete(RedisKey("user:\(id)"))
        await req.cacheDelete(RedisKey("users:list"))
        return UserDTO(from: user)
    }

    func delete(req: Request) async throws -> HTTPStatus {
        guard let id = req.parameters.get("userID", as: UUID.self) else { throw Abort(.badRequest) }
        guard let user = try await User.find(id, on: req.db) else { throw Abort(.notFound) }
        try await user.delete(on: req.db)
        await req.cacheDelete(RedisKey("user:\(id)"))
        await req.cacheDelete(RedisKey("users:list"))
        return .noContent
    }

    func login(req: Request) async throws -> LoginResponse {
        let body = try req.content.decode(LoginRequest.self)
        guard let user = try await User.query(on: req.db).filter(\.$email == body.email).first() else {
            throw Abort(.unauthorized, reason: "Invalid credentials")
        }
        guard try await req.password.async.verify(body.password, created: user.passwordHash).get() else {
            throw Abort(.unauthorized, reason: "Invalid credentials")
        }
        let token = [UInt8].random(count: 32).base64
        try? await req.cacheSetJSON(RedisKey("session:\(token)"), value: user.id!.uuidString, ttl: 3600)
        return LoginResponse(token: token, user: UserDTO(from: user))
    }
}

// Request-level Redis cache helpers (avoids naming conflicts with RedisClient protocol)
extension Request {
    func cacheGetJSON<T: Codable>(_ key: RedisKey, as type: T.Type) async throws -> T? {
        let future = redis.get(key, as: String.self)
        guard let str = try await future.get() else { return nil }
        return try JSONDecoder().decode(T.self, from: Data(str.utf8))
    }

    func cacheSetJSON<T: Codable>(_ key: RedisKey, value: T, ttl: Int) async throws {
        let data = try JSONEncoder().encode(value)
        let str  = String(data: data, encoding: .utf8) ?? ""
        _ = try await redis.setex(key, to: str, expirationInSeconds: ttl).get()
    }

    func cacheDelete(_ key: RedisKey) async {
        _ = try? await redis.delete(key).get()
    }
}
