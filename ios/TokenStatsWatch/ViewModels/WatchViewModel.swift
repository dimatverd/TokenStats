import Foundation

@MainActor
final class WatchViewModel: ObservableObject {
    @Published var providers: [ProviderSummary] = []
    @Published var isLoading = false
    @Published var error: String?

    func load() async {
        isLoading = true
        do {
            let summary = try await APIClient.shared.getSummary()
            providers = summary.providers
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
