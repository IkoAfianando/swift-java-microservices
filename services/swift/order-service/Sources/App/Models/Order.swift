import Fluent
import Vapor

enum OrderStatus: String, Codable { case pending, confirmed, shipped, delivered, cancelled }

final class Order: Model, Content, @unchecked Sendable {
    static let schema = "orders"

    @ID var id: UUID?
    @Field(key: "user_id") var userId: UUID
    @Field(key: "status")  var status: OrderStatus
    @Field(key: "total")   var total: Double
    @Children(for: \.$order) var items: [OrderItem]
    @Timestamp(key: "created_at", on: .create) var createdAt: Date?
    @Timestamp(key: "updated_at", on: .update) var updatedAt: Date?

    init() {}
    init(userId: UUID, status: OrderStatus = .pending, total: Double = 0) {
        self.userId = userId
        self.status = status
        self.total  = total
    }
}

final class OrderItem: Model, Content, @unchecked Sendable {
    static let schema = "order_items"

    @ID var id: UUID?
    @Parent(key: "order_id")  var order: Order
    @Field(key: "product_id") var productId: UUID
    @Field(key: "quantity")   var quantity: Int
    @Field(key: "unit_price") var unitPrice: Double

    init() {}
    init(productId: UUID, quantity: Int, unitPrice: Double) {
        self.productId = productId
        self.quantity  = quantity
        self.unitPrice = unitPrice
    }
}

struct CreateOrderRequest: Content {
    var userId: UUID
    var items: [OrderItemRequest]
}

struct OrderItemRequest: Content {
    var productId: UUID
    var quantity: Int
}
