import Vapor
import Fluent

struct OrderController: RouteCollection {
    let productServiceURL: String
    let userServiceURL: String

    func boot(routes: any RoutesBuilder) throws {
        routes.get(use: list)
        routes.post(use: create)
        routes.group(":orderID") { r in
            r.get(use: get)
            r.patch("status", use: updateStatus)
        }
    }

    func list(req: Request) async throws -> [Order] {
        try await Order.query(on: req.db).with(\.$items).sort(\.$createdAt, .descending).limit(50).all()
    }

    func create(req: Request) async throws -> Response {
        let body = try req.content.decode(CreateOrderRequest.self)

        // Fetch product prices from product-service
        var total: Double = 0
        var items: [(UUID, Int, Double)] = []
        for item in body.items {
            let url = "\(productServiceURL)/products/\(item.productId)"
            let res = try await req.client.get(URI(string: url))
            guard res.status == .ok,
                  let price = try? res.content.get(Double.self, at: "price") else {
                throw Abort(.badGateway, reason: "Could not fetch product \(item.productId)")
            }
            let lineTotal = price * Double(item.quantity)
            total += lineTotal
            items.append((item.productId, item.quantity, price))
        }

        let order = Order(userId: body.userId, status: .pending, total: total)
        try await order.save(on: req.db)

        for (pid, qty, price) in items {
            let oi = OrderItem(productId: pid, quantity: qty, unitPrice: price)
            oi.$order.id = order.id!
            try await oi.save(on: req.db)
        }

        try await order.$items.load(on: req.db)
        return try await order.encodeResponse(status: .created, for: req)
    }

    func get(req: Request) async throws -> Order {
        guard let id = req.parameters.get("orderID", as: UUID.self) else { throw Abort(.badRequest) }
        guard let order = try await Order.query(on: req.db).filter(\.$id == id).with(\.$items).first() else {
            throw Abort(.notFound)
        }
        return order
    }

    func updateStatus(req: Request) async throws -> Order {
        guard let id = req.parameters.get("orderID", as: UUID.self) else { throw Abort(.badRequest) }
        guard let order = try await Order.find(id, on: req.db) else { throw Abort(.notFound) }
        let newStatus = try req.content.get(OrderStatus.self, at: "status")
        order.status = newStatus
        try await order.save(on: req.db)
        return order
    }
}
