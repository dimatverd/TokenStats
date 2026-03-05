import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @StateObject private var vm = DashboardViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if vm.providers.isEmpty && !vm.isLoading {
                    ContentUnavailableView(
                        "No Providers",
                        systemImage: "key.fill",
                        description: Text("Add an API key in Settings to start monitoring.")
                    )
                } else {
                    List {
                        ForEach(vm.providers) { provider in
                            NavigationLink(value: provider) {
                                ProviderCardView(provider: provider)
                            }
                        }

                        if let updatedAt = vm.updatedAt {
                            Section {
                                Text("Updated \(updatedAt, style: .relative) ago")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .navigationTitle("TokenStats")
            .navigationDestination(for: ProviderSummary.self) { provider in
                ProviderDetailView(providerId: provider.providerId, providerName: provider.name)
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    NavigationLink(destination: SettingsView()) {
                        Image(systemName: "gearshape")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await vm.load() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(vm.isLoading)
                }
            }
            .refreshable {
                await vm.load()
            }
            .task {
                await vm.load()
                vm.startAutoRefresh()
            }
            .onDisappear {
                vm.stopAutoRefresh()
            }
        }
    }
}

extension ProviderSummary: Hashable {
    static func == (lhs: ProviderSummary, rhs: ProviderSummary) -> Bool {
        lhs.providerId == rhs.providerId
    }
    func hash(into hasher: inout Hasher) {
        hasher.combine(providerId)
    }
}
