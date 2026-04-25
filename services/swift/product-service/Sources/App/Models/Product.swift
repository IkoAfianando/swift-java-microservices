import Fluent
import Vapor

final class Product: Model, Content, @unchecked Sendable {
    static let schema = "products"

    @ID var id: UUID?
    @Field(key: "name")        var name: String
    @Field(key: "description") var description: String
    @Field(key: "price")       var price: Double
    @Field(key: "stock")       var stock: Int
    @Timestamp(key: "created_at", on: .create) var createdAt: Date?
    @Timestamp(key: "updated_at", on: .update) var updatedAt: Date?

    init() {}

    init(id: UUID? = nil, name: String, description: String = "", price: Double, stock: Int) {
        self.id          = id
        self.name        = name
        self.description = description
        self.price       = price
        self.stock       = stock
    }
}

struct CreateProductRequest: Content, Validatable {
    var name: String
    var description: String?
    var price: Double
    var stock: Int

    static func validations(_ validations: inout Validations) {
        validations.add("name",  as: String.self, is: !.empty)
        validations.add("price", as: Double.self, is: .range(0...))
        validations.add("stock", as: Int.self,    is: .range(0...))
    }
}
