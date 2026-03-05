import Foundation

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var providers: [ProviderSummary] = []
    @Published var updatedAt: Date?
    @Published var isLoading = false
    @Published var error: String?

    private var refreshTask: Task<Void, Never>?

    func load() async {
        isLoading = true
        error = nil
        do {
            let summary = try await APIClient.shared.getSummary()
            providers = summary.providers
            updatedAt = summary.updatedAt
            evaluateLiveActivities()
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    /// Evaluates all providers and starts/updates/ends Live Activities
    /// for any that cross the 80% usage threshold.
    private func evaluateLiveActivities() {
        guard #available(iOS 16.1, *) else { return }
        let manager = LiveActivityManager.shared
        for provider in providers {
            manager.evaluateProvider(provider)
        }
    }

    func startAutoRefresh(interval: TimeInterval = 30) {
        refreshTask?.cancel()
        refreshTask = Task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(interval))
            }
        }
    }

    func stopAutoRefresh() {
        refreshTask?.cancel()
    }
}
