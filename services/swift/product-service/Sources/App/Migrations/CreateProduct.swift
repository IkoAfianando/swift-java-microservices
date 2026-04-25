import Fluent

struct CreateProduct: AsyncMigration {
    func prepare(on database: any Database) async throws {
        try await database.schema("products")
            .id()
            .field("name",        .string,  .required)
            .field("description", .string,  .required)
            .field("price",       .double,  .required)
            .field("stock",       .int,     .required)
            .field("created_at",  .datetime)
            .field("updated_at",  .datetime)
            .create()
    }

    func revert(on database: any Database) async throws {
        try await database.schema("products").delete()
    }
}
