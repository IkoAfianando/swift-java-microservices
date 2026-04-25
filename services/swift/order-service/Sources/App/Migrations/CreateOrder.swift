import Fluent

struct CreateOrder: AsyncMigration {
    func prepare(on database: any Database) async throws {
        try await database.schema("orders")
            .id()
            .field("user_id",    .uuid,     .required)
            .field("status",     .string,   .required)
            .field("total",      .double,   .required)
            .field("created_at", .datetime)
            .field("updated_at", .datetime)
            .create()

        try await database.schema("order_items")
            .id()
            .field("order_id",   .uuid,   .required, .references("orders", "id", onDelete: .cascade))
            .field("product_id", .uuid,   .required)
            .field("quantity",   .int,    .required)
            .field("unit_price", .double, .required)
            .create()
    }

    func revert(on database: any Database) async throws {
        try await database.schema("order_items").delete()
        try await database.schema("orders").delete()
    }
}
