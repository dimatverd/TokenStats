import Foundation

enum APIError: LocalizedError {
    case unauthorized
    case serverError(Int, String)
    case networkError(Error)
    case decodingError(Error)

    var errorDescription: String? {
        switch self {
        case .unauthorized: return "Session expired. Please log in again."
        case .serverError(let code, let msg): return "Server error (\(code)): \(msg)"
        case .networkError(let err): return "Network error: \(err.localizedDescription)"
        case .decodingError(let err): return "Data error: \(err.localizedDescription)"
        }
    }
}

actor APIClient {
    static let shared = APIClient()

    #if DEBUG
    private var baseURL = "http://localhost:8000"
    #else
    private var baseURL = "https://api.tokenstats.app"
    #endif

    private let session: URLSession
    private let decoder: JSONDecoder

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        self.session = URLSession(configuration: config)

        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601
    }

    func setBaseURL(_ url: String) {
        self.baseURL = url
    }

    // MARK: - Auth

    func login(email: String, password: String) async throws -> TokenResponse {
        let body = LoginRequest(email: email, password: password)
        let response: TokenResponse = try await post("/auth/login", body: body, auth: false)
        KeychainService.accessToken = response.accessToken
        KeychainService.refreshToken = response.refreshToken
        return response
    }

    func register(email: String, password: String) async throws -> RegisterResponse {
        let body = RegisterRequest(email: email, password: password)
        let response: RegisterResponse = try await post("/auth/register", body: body, auth: false)
        KeychainService.accessToken = response.accessToken
        KeychainService.refreshToken = response.refreshToken
        return response
    }

    func logout() {
        KeychainService.accessToken = nil
        KeychainService.refreshToken = nil
    }

    // MARK: - API v1

    func getSummary() async throws -> SummaryResponse {
        try await get("/api/v1/summary")
    }

    func getLimits(provider: String) async throws -> [RateLimitMetric] {
        try await get("/api/v1/limits/\(provider)")
    }

    func getUsage(provider: String) async throws -> [UsageMetric] {
        try await get("/api/v1/usage/\(provider)")
    }

    func getCosts(provider: String) async throws -> CostMetric? {
        try await get("/api/v1/costs/\(provider)")
    }

    func addProvider(provider: String, apiKey: String, tier: String?, label: String?) async throws {
        let body = AddProviderRequest(provider: provider, apiKey: apiKey, tier: tier, label: label)
        let _: EmptyResponse = try await post("/auth/providers", body: body, auth: true)
    }

    // MARK: - HTTP helpers

    private func get<T: Decodable>(_ path: String) async throws -> T {
        var request = URLRequest(url: URL(string: baseURL + path)!)
        request.httpMethod = "GET"
        try await addAuth(&request)
        return try await perform(request)
    }

    private func post<T: Decodable, B: Encodable>(_ path: String, body: B, auth: Bool = true) async throws -> T {
        var request = URLRequest(url: URL(string: baseURL + path)!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        if auth { try await addAuth(&request) }
        return try await perform(request)
    }

    private func perform<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.networkError(URLError(.badServerResponse))
        }

        if http.statusCode == 401 {
            // Try refresh
            if let refreshed = try? await refreshTokens() {
                KeychainService.accessToken = refreshed.accessToken
                KeychainService.refreshToken = refreshed.refreshToken
                var retryRequest = request
                retryRequest.setValue("Bearer \(refreshed.accessToken)", forHTTPHeaderField: "Authorization")
                let (retryData, retryResponse) = try await session.data(for: retryRequest)
                if let retryHttp = retryResponse as? HTTPURLResponse, retryHttp.statusCode == 401 {
                    throw APIError.unauthorized
                }
                return try decoder.decode(T.self, from: retryData)
            }
            throw APIError.unauthorized
        }

        guard (200...299).contains(http.statusCode) else {
            let msg = (try? JSONDecoder().decode(ErrorDetail.self, from: data))?.detail ?? "Unknown error"
            throw APIError.serverError(http.statusCode, msg)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    private func addAuth(_ request: inout URLRequest) async throws {
        guard let token = KeychainService.accessToken else {
            throw APIError.unauthorized
        }
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }

    private func refreshTokens() async throws -> TokenResponse {
        guard let refreshToken = KeychainService.refreshToken else {
            throw APIError.unauthorized
        }
        var request = URLRequest(url: URL(string: baseURL + "/auth/token")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["refresh_token": refreshToken]
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.unauthorized
        }
        return try decoder.decode(TokenResponse.self, from: data)
    }
}

private struct ErrorDetail: Decodable {
    let detail: String
}

private struct EmptyResponse: Decodable {}
