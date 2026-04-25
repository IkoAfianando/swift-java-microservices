import Fluent
import Vapor

final class User: Model, Content, @unchecked Sendable {
    static let schema = "users"

    @ID var id: UUID?
    @Field(key: "name")     var name: String
    @Field(key: "email")    var email: String
    @Field(key: "password") var passwordHash: String
    @Timestamp(key: "created_at", on: .create) var createdAt: Date?
    @Timestamp(key: "updated_at", on: .update) var updatedAt: Date?

    init() {}

    init(id: UUID? = nil, name: String, email: String, passwordHash: String) {
        self.id           = id
        self.name         = name
        self.email        = email
        self.passwordHash = passwordHash
    }
}

struct UserDTO: Content {
    var id: UUID?
    var name: String
    var email: String
    var createdAt: Date?

    init(from user: User) {
        self.id        = user.id
        self.name      = user.name
        self.email     = user.email
        self.createdAt = user.createdAt
    }
}

struct CreateUserRequest: Content, Validatable {
    var name: String
    var email: String
    var password: String

    static func validations(_ validations: inout Validations) {
        validations.add("name",     as: String.self, is: !.empty && .count(2...100))
        validations.add("email",    as: String.self, is: .email)
        validations.add("password", as: String.self, is: .count(8...))
    }
}

struct LoginRequest: Content {
    var email: String
    var password: String
}

struct LoginResponse: Content {
    var token: String
    var user: UserDTO
}
