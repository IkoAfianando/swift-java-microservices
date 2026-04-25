import Vapor
import Fluent
import Redis

struct ProductController: RouteCollection {
    func boot(routes: any RoutesBuilder) throws {
        routes.get(use: list)
        routes.post(use: create)
        routes.group(":productID") { r in
            r.get(use: get)
            r.put(use: update)
            r.delete(use: delete)
        }
    }

    func list(req: Request) async throws -> [Product] {
        let key = RedisKey("products:list")
        if let cached = try? await req.cacheGetJSON(key, as: [Product].self) {
            return cached
        }
        let products = try await Product.query(on: req.db).sort(\.$name).all()
        try? await req.cacheSetJSON(key, value: products, ttl: 30)
        return products
    }

    func create(req: Request) async throws -> Response {
        try CreateProductRequest.validate(content: req)
        let body = try req.content.decode(CreateProductRequest.self)
        let product = Product(name: body.name, description: body.description ?? "", price: body.price, stock: body.stock)
        try await product.save(on: req.db)
        await req.cacheDelete(RedisKey("products:list"))
        return try await product.encodeResponse(status: .created, for: req)
    }

    func get(req: Request) async throws -> Product {
        guard let id = req.parameters.get("productID", as: UUID.self) else { throw Abort(.badRequest) }
        let key = RedisKey("product:\(id)")
        if let cached = try? await req.cacheGetJSON(key, as: Product.self) { return cached }
        guard let p = try await Product.find(id, on: req.db) else { throw Abort(.notFound) }
        try? await req.cacheSetJSON(key, value: p, ttl: 60)
        return p
    }

    func update(req: Request) async throws -> Product {
        guard let id = req.parameters.get("productID", as: UUID.self) else { throw Abort(.badRequest) }
        guard let product = try await Product.find(id, on: req.db) else { throw Abort(.notFound) }
        let body = try req.content.decode(CreateProductRequest.self)
        product.name        = body.name
        product.description = body.description ?? ""
        product.price       = body.price
        product.stock       = body.stock
        try await product.save(on: req.db)
        await req.cacheDelete(RedisKey("product:\(id)"))
        await req.cacheDelete(RedisKey("products:list"))
        return product
    }

    func delete(req: Request) async throws -> HTTPStatus {
        guard let id = req.parameters.get("productID", as: UUID.self) else { throw Abort(.badRequest) }
        guard let product = try await Product.find(id, on: req.db) else { throw Abort(.notFound) }
        try await product.delete(on: req.db)
        await req.cacheDelete(RedisKey("product:\(id)"))
        await req.cacheDelete(RedisKey("products:list"))
        return .noContent
    }
}

extension Request {
    func cacheGetJSON<T: Codable>(_ key: RedisKey, as type: T.Type) async throws -> T? {
        guard let str = try await redis.get(key, as: String.self).get() else { return nil }
        return try JSONDecoder().decode(T.self, from: Data(str.utf8))
    }

    func cacheSetJSON<T: Codable>(_ key: RedisKey, value: T, ttl: Int) async throws {
        let str = String(data: try JSONEncoder().encode(value), encoding: .utf8) ?? ""
        _ = try await redis.setex(key, to: str, expirationInSeconds: ttl).get()
    }

    func cacheDelete(_ key: RedisKey) async {
        _ = try? await redis.delete(key).get()
    }
}
