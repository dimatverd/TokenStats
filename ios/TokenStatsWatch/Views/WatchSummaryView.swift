import SwiftUI

struct WatchSummaryView: View {
    @StateObject private var vm = WatchViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if vm.providers.isEmpty && !vm.isLoading {
                    Text("No providers configured.\nSet up in iPhone app.")
                        .font(.caption)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                } else {
                    List(vm.providers) { provider in
                        NavigationLink(value: provider) {
                            WatchProviderRow(provider: provider)
                        }
                    }
                }
            }
            .navigationTitle("TokenStats")
            .navigationDestination(for: ProviderSummary.self) { provider in
                WatchProviderDetailView(provider: provider)
            }
            .task {
                await vm.load()
            }
        }
    }
}

struct WatchProviderRow: View {
    let provider: ProviderSummary

    var body: some View {
        HStack {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
            VStack(alignment: .leading) {
                Text(provider.name)
                    .font(.headline)
                if let rpm = provider.rpm {
                    Text("RPM \(Int(rpm.pct))%")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if let cost = provider.costToday {
                Text("$\(cost, specifier: "%.0f")")
                    .font(.caption.monospacedDigit())
            }
        }
    }

    private var color: Color {
        switch provider.statusColor {
        case "green": return .green
        case "yellow": return .yellow
        case "red": return .red
        default: return .gray
        }
    }
}
