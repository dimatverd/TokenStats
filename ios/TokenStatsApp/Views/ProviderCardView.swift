import SwiftUI

struct ProviderCardView: View {
    let provider: ProviderSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Circle()
                    .fill(statusColor)
                    .frame(width: 10, height: 10)
                Text(provider.name)
                    .font(.headline)
                Spacer()
                if let cost = provider.costToday {
                    Text("$\(cost, specifier: "%.2f")")
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            if provider.status == .pending {
                Text("Waiting for data...")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                HStack(spacing: 16) {
                    if let rpm = provider.rpm {
                        MetricBadge(label: "RPM", pct: rpm.pct, value: "\(rpm.used)/\(rpm.limit)")
                    }
                    if let tpm = provider.tpm {
                        MetricBadge(label: "TPM", pct: tpm.pct, value: "\(formatted(tpm.used))/\(formatted(tpm.limit))")
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var statusColor: Color {
        switch provider.statusColor {
        case "green": return .green
        case "yellow": return .yellow
        case "red": return .red
        default: return .gray
        }
    }

    private func formatted(_ n: Int) -> String {
        if n >= 1_000_000 { return "\(n / 1_000_000)M" }
        if n >= 1_000 { return "\(n / 1_000)K" }
        return "\(n)"
    }
}

struct MetricBadge: View {
    let label: String
    let pct: Double
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            ProgressView(value: min(pct, 100), total: 100)
                .tint(pct >= 95 ? .red : pct >= 80 ? .yellow : .blue)
            Text(value)
                .font(.caption.monospacedDigit())
        }
    }
}
