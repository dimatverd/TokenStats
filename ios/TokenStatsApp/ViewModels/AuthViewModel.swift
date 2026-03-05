import Foundation

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var isAuthenticated = false
    @Published var isLoading = false
    @Published var error: String?

    init() {
        isAuthenticated = KeychainService.accessToken != nil
    }

    func login(email: String, password: String) async {
        isLoading = true
        error = nil
        do {
            _ = try await APIClient.shared.login(email: email, password: password)
            isAuthenticated = true
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func register(email: String, password: String) async {
        isLoading = true
        error = nil
        do {
            _ = try await APIClient.shared.register(email: email, password: password)
            isAuthenticated = true
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func logout() {
        APIClient.shared.logout()
        isAuthenticated = false
    }
}
