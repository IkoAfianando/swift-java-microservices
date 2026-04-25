import Foundation

actor MetricsCollector {
    static let shared = MetricsCollector()
    private init() {}

    // Buckets mirror Spring Boot Micrometer's percentiles-histogram default so
    // Prometheus histogram_quantile() compares identically across stacks.
    private let buckets: [Double] = [
        0.001, 0.001048576, 0.001398101, 0.001747626, 0.002097151, 0.002446676,
        0.002796201, 0.003145726, 0.003495251, 0.003844776, 0.004194304, 0.005592405,
        0.006990506, 0.008388607, 0.009786708, 0.011184809, 0.01258291, 0.013981011,
        0.015379112, 0.016777216, 0.022369621, 0.027962026, 0.033554431, 0.039146836,
        0.044739241, 0.050331646, 0.055924051, 0.061516456, 0.067108864, 0.089478485,
        0.1, 0.111848106, 0.134217727, 0.156587348, 0.178956969, 0.20132659,
        0.223696211, 0.246065832, 0.25, 0.268435456, 0.357913941, 0.447392426,
        0.5, 0.536870911, 0.626349396, 0.715827881, 0.805306366, 0.894784851,
        0.984263336, 1.0, 1.073741824, 1.431655765, 1.789569706, 2.147483647,
        2.505397588, 2.863311529, 3.22122547, 3.579139411, 3.937053352, 4.294967296,
        5.726623061, 7.158278826, 8.589934591, 10.021590356, 11.453246121,
        12.884901886, 14.316557651, 15.748213416, 17.179869184, 22.906492245,
        28.633115306, 30.0
    ]
    private var counts: [String: Int64] = [:]
    private var sums:   [String: Double] = [:]
    private var bkts:   [String: [Int: Int64]] = [:]

    func record(method: String, status: Int, duration: Double) {
        let key = "\(method)|\(status)"
        counts[key, default: 0] += 1
        sums[key, default: 0] += duration
        for (i, le) in buckets.enumerated() where duration <= le {
            if bkts[key] == nil { bkts[key] = [:] }
            bkts[key]![i, default: 0] += 1
        }
    }

    func text(service: String) -> String {
        var lines = [
            "# HELP service_up Service is up",
            "# TYPE service_up gauge",
            "service_up{language=\"swift\",service=\"\(service)\"} 1"
        ]

        if let rss = processRSSBytes() {
            lines += [
                "# HELP process_resident_memory_bytes Resident set size in bytes",
                "# TYPE process_resident_memory_bytes gauge",
                "process_resident_memory_bytes{language=\"swift\",service=\"\(service)\"} \(rss)"
            ]
        }

        if !counts.isEmpty {
            lines += [
                "# HELP http_requests_total Total HTTP requests handled",
                "# TYPE http_requests_total counter"
            ]
            for (key, count) in counts {
                let (m, s) = split(key)
                lines.append("http_requests_total{method=\"\(m)\",status=\"\(s)\",language=\"swift\",service=\"\(service)\"} \(count)")
            }

            lines += [
                "# HELP http_request_duration_seconds HTTP request duration in seconds",
                "# TYPE http_request_duration_seconds histogram"
            ]
            for (key, buckMap) in bkts {
                let (m, s) = split(key)
                let base = "method=\"\(m)\",status=\"\(s)\",language=\"swift\",service=\"\(service)\""
                for (i, le) in buckets.enumerated() {
                    lines.append("http_request_duration_seconds_bucket{\(base),le=\"\(le)\"} \(buckMap[i] ?? 0)")
                }
                let total = counts[key] ?? 0
                lines.append("http_request_duration_seconds_bucket{\(base),le=\"+Inf\"} \(total)")
                lines.append("http_request_duration_seconds_sum{\(base)} \(String(format: "%.9f", sums[key] ?? 0))")
                lines.append("http_request_duration_seconds_count{\(base)} \(total)")
            }
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private func split(_ key: String) -> (String, String) {
        let parts = key.components(separatedBy: "|")
        return (parts.first ?? "GET", parts.last ?? "200")
    }

    private func processRSSBytes() -> Int64? {
        guard let content = try? String(contentsOfFile: "/proc/self/status", encoding: .utf8) else { return nil }
        for line in content.components(separatedBy: "\n") {
            guard line.hasPrefix("VmRSS:") else { continue }
            let parts = line.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
            if parts.count >= 2, let kb = Int64(parts[1]) { return kb * 1024 }
        }
        return nil
    }
}
