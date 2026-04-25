import Vapor

final class RequestMetricsMiddleware: AsyncMiddleware {
    private let service: String
    init(service: String) { self.service = service }

    func respond(to request: Request, chainingTo next: any AsyncResponder) async throws -> Response {
        let path = request.url.path
        let startNS = DispatchTime.now().uptimeNanoseconds
        let response = try await next.respond(to: request)
        if path != "/health" && path != "/metrics" {
            let elapsed = DispatchTime.now().uptimeNanoseconds &- startNS
            await MetricsCollector.shared.record(
                method: request.method.rawValue,
                status: Int(response.status.code),
                duration: Double(elapsed) / 1_000_000_000.0
            )
        }
        return response
    }
}
