import Foundation

@MainActor
final class ProviderViewModel: ObservableObject {
    let providerId: String
    let providerName: String

    @Published var limits: [RateLimitMetric] = []
    @Published var usage: [UsageMetric] = []
    @Published var costs: CostMetric?
    @Published var isLoading = false
    @Published var error: String?

    init(providerId: String, providerName: String) {
        self.providerId = providerId
        self.providerName = providerName
    }

    func load() async {
        isLoading = true
        error = nil
        do {
            async let limitsReq = APIClient.shared.getLimits(provider: providerId)
            async let usageReq = APIClient.shared.getUsage(provider: providerId)
            async let costsReq = APIClient.shared.getCosts(provider: providerId)

            limits = try await limitsReq
            usage = try await usageReq
            costs = try await costsReq
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
