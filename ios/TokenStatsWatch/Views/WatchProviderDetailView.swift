import SwiftUI

struct WatchProviderDetailView: View {
    let provider: ProviderSummary

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                Text(provider.name)
                    .font(.headline)

                if let rpm = provider.rpm {
                    WatchGauge(label: "RPM", pct: rpm.pct, detail: "\(rpm.used)/\(rpm.limit)")
                }

                if let tpm = provider.tpm {
                    WatchGauge(label: "TPM", pct: tpm.pct, detail: "\(formatted(tpm.used))/\(formatted(tpm.limit))")
                }

                if let cost = provider.costToday {
                    VStack(spacing: 2) {
                        Text("Today")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("$\(cost, specifier: "%.2f")")
                            .font(.title3.monospacedDigit().bold())
                    }
                }
            }
            .padding()
        }
        .navigationTitle(provider.name)
    }

    private func formatted(_ n: Int) -> String {
        if n >= 1_000_000 { return "\(n / 1_000_000)M" }
        if n >= 1_000 { return "\(n / 1_000)K" }
        return "\(n)"
    }
}

struct WatchGauge: View {
    let label: String
    let pct: Double
    let detail: String

    var body: some View {
        Gauge(value: min(pct, 100), in: 0...100) {
            Text(label)
        } currentValueLabel: {
            Text("\(Int(pct))%")
                .font(.caption.bold())
        }
        .gaugeStyle(.accessoryLinear)
        .tint(pct >= 95 ? .red : pct >= 80 ? .yellow : .blue)

        Text(detail)
            .font(.caption2.monospacedDigit())
            .foregroundStyle(.secondary)
    }
}
