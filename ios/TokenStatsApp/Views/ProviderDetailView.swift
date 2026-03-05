import SwiftUI
import Charts

struct ProviderDetailView: View {
    let providerId: String
    let providerName: String
    @StateObject private var vm: ProviderViewModel

    init(providerId: String, providerName: String) {
        self.providerId = providerId
        self.providerName = providerName
        _vm = StateObject(wrappedValue: ProviderViewModel(providerId: providerId, providerName: providerName))
    }

    var body: some View {
        List {
            if !vm.limits.isEmpty {
                Section("Rate Limits") {
                    ForEach(vm.limits) { limit in
                        RateLimitRow(limit: limit)
                    }
                }
            }

            if let history = vm.history, !history.points.isEmpty {
                Section("History") {
                    HistoryChartView(history: history)
                }
            }

            if !vm.usage.isEmpty {
                Section("Token Usage") {
                    UsageChartView(usage: vm.usage)
                        .frame(height: 200)

                    ForEach(vm.usage) { u in
                        HStack {
                            Text(u.model)
                                .font(.subheadline)
                            Spacer()
                            Text("\(formatted(u.totalTokens)) tokens")
                                .font(.subheadline.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            if let costs = vm.costs {
                Section("Costs") {
                    HStack {
                        Text("Total")
                            .font(.headline)
                        Spacer()
                        Text("$\(costs.totalUsd, specifier: "%.2f")")
                            .font(.title2.monospacedDigit().bold())
                    }
                }
            }

            if vm.limits.isEmpty && vm.usage.isEmpty && vm.costs == nil && !vm.isLoading {
                ContentUnavailableView(
                    "No Data Yet",
                    systemImage: "clock.arrow.circlepath",
                    description: Text("Data will appear after the next polling cycle.")
                )
            }
        }
        .navigationTitle(providerName)
        .refreshable {
            await vm.load()
        }
        .task {
            await vm.load()
        }
        .overlay {
            if vm.isLoading && vm.limits.isEmpty {
                ProgressView()
            }
        }
    }

    private func formatted(_ n: Int) -> String {
        if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
        if n >= 1_000 { return String(format: "%.1fK", Double(n) / 1_000) }
        return "\(n)"
    }
}

struct RateLimitRow: View {
    let limit: RateLimitMetric

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(limit.model)
                .font(.subheadline.bold())

            HStack(spacing: 16) {
                GaugeView(label: "RPM", pct: limit.rpmPct, used: limit.rpmUsed, total: limit.rpmLimit)
                GaugeView(label: "TPM", pct: limit.tpmPct, used: limit.tpmUsed, total: limit.tpmLimit)
            }
        }
        .padding(.vertical, 4)
    }
}

struct GaugeView: View {
    let label: String
    let pct: Double
    let used: Int
    let total: Int

    var body: some View {
        VStack(spacing: 4) {
            Gauge(value: min(pct, 100), in: 0...100) {
                Text(label)
            } currentValueLabel: {
                Text("\(Int(pct))%")
                    .font(.caption.bold())
            }
            .gaugeStyle(.accessoryCircular)
            .tint(pct >= 95 ? .red : pct >= 80 ? .yellow : .blue)

            Text("\(used)/\(total)")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }
}

struct UsageChartView: View {
    let usage: [UsageMetric]

    var body: some View {
        Chart(usage) { u in
            BarMark(
                x: .value("Model", u.model),
                y: .value("Tokens", u.totalTokens)
            )
            .foregroundStyle(by: .value("Type", "Total"))
        }
        .chartLegend(.hidden)
    }
}
