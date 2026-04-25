import Vapor

public func routes(_ app: Application) throws {
    app.get("health") { _ in
        ["status": "ok", "service": "swift-user-service", "language": "swift"]
    }

    app.get("metrics") { _ -> Response in
        let body = await MetricsCollector.shared.text(service: "user-service")
        return Response(status: .ok,
                       headers: ["Content-Type": "text/plain; version=0.0.4"],
                       body: .init(string: body))
    }

    let users = app.grouped("users")
    try users.register(collection: UserController())

    app.post("auth", "login") { req in
        try await UserController().login(req: req)
    }
}
