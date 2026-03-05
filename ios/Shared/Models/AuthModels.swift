import Foundation

struct LoginRequest: Codable {
    let email: String
    let password: String
}

struct RegisterRequest: Codable {
    let email: String
    let password: String
}

struct TokenResponse: Codable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
    }
}

struct RegisterResponse: Codable {
    let id: Int
    let email: String
    let createdAt: Date
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case id, email
        case createdAt = "created_at"
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
    }
}

struct AddProviderRequest: Codable {
    let provider: String
    let apiKey: String
    let tier: String?
    let label: String?

    enum CodingKeys: String, CodingKey {
        case provider
        case apiKey = "api_key"
        case tier, label
    }
}
