import Foundation

enum ProviderStatus: String, Codable {
    case ok
    case stale
    case pending
    case error
}

struct RateLimitMetric: Codable, Identifiable {
    var id: String { model }
    let model: String
    let rpmLimit: Int
    let rpmUsed: Int
    let rpmPct: Double
    let tpmLimit: Int
    let tpmUsed: Int
    let tpmPct: Double

    enum CodingKeys: String, CodingKey {
        case model
        case rpmLimit = "rpm_limit"
        case rpmUsed = "rpm_used"
        case rpmPct = "rpm_pct"
        case tpmLimit = "tpm_limit"
        case tpmUsed = "tpm_used"
        case tpmPct = "tpm_pct"
    }
}

struct UsageMetric: Codable, Identifiable {
    var id: String { model }
    let model: String
    let inputTokens: Int
    let outputTokens: Int
    let totalTokens: Int
    let periodStart: Date
    let periodEnd: Date

    enum CodingKeys: String, CodingKey {
        case model
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case totalTokens = "total_tokens"
        case periodStart = "period_start"
        case periodEnd = "period_end"
    }
}

struct CostMetric: Codable {
    let totalUsd: Double
    let periodStart: Date
    let periodEnd: Date
    let breakdown: [[String: AnyCodableValue]]

    enum CodingKeys: String, CodingKey {
        case totalUsd = "total_usd"
        case periodStart = "period_start"
        case periodEnd = "period_end"
        case breakdown
    }
}

struct LimitSummary: Codable {
    let used: Int
    let limit: Int
    let pct: Double
}

struct ProviderSummary: Codable, Identifiable {
    var id: String { providerId }
    let providerId: String
    let name: String
    let status: ProviderStatus
    let rpm: LimitSummary?
    let tpm: LimitSummary?
    let costToday: Double?
    let costMonth: Double?
    let budgetMonth: Double?
    let budgetPct: Double?

    enum CodingKeys: String, CodingKey {
        case providerId = "id"
        case name, status, rpm, tpm
        case costToday = "cost_today"
        case costMonth = "cost_month"
        case budgetMonth = "budget_month"
        case budgetPct = "budget_pct"
    }

    var statusColor: String {
        switch status {
        case .ok:
            let maxPct = max(rpm?.pct ?? 0, tpm?.pct ?? 0)
            if maxPct >= 95 { return "red" }
            if maxPct >= 80 { return "yellow" }
            return "green"
        case .stale: return "yellow"
        case .pending: return "gray"
        case .error: return "red"
        }
    }
}

struct SummaryResponse: Codable {
    let providers: [ProviderSummary]
    let updatedAt: Date?

    enum CodingKeys: String, CodingKey {
        case providers
        case updatedAt = "updated_at"
    }
}

// Helper for decoding arbitrary JSON values in breakdown
enum AnyCodableValue: Codable {
    case string(String)
    case double(Double)
    case int(Int)
    case bool(Bool)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Int.self) { self = .int(v) }
        else if let v = try? container.decode(Double.self) { self = .double(v) }
        else if let v = try? container.decode(Bool.self) { self = .bool(v) }
        else if let v = try? container.decode(String.self) { self = .string(v) }
        else { self = .string("") }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        }
    }
}
