import SwiftUI
import WidgetKit

// MARK: - Provider Detail Widget (Small / Medium)

struct ProviderWidget: Widget {
    let kind = "ProviderWidget"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(
            kind: kind,
            intent: SelectProviderIntent.self,
            provider: SingleProviderTimelineProvider()
        ) { entry in
            ProviderWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Provider Detail")
        .description("RPM gauge, TPM gauge, and cost for a single provider.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

// MARK: - Views

struct ProviderWidgetView: View {
    @Environment(\.widgetFamily) var family
    let entry: ProviderEntry

    var body: some View {
        if let provider = entry.providers.first {
            switch family {
            case .systemSmall:
                smallView(provider)
            default:
                mediumView(provider)
            }
        } else {
            emptyView
        }
    }

    // MARK: - Empty

    private var emptyView: some View {
        VStack(spacing: 6) {
            Image(systemName: "gauge.with.needle")
                .font(.title3)
                .foregroundStyle(.secondary)
            Text("Select a provider")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Small

    private func smallView(_ provider: ProviderSummary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack(spacing: 6) {
                Circle()
                    .fill(provider.swiftUIStatusColor)
                    .frame(width: 8, height: 8)
                Text(provider.name)
                    .font(.caption.bold())
                    .lineLimit(1)
            }

            Spacer(minLength: 0)

            // RPM Gauge
            if let rpm = provider.rpm {
                GaugeView(label: "RPM", pct: rpm.pct, detail: "\(rpm.used)/\(rpm.limit)")
            }

            // Cost
            if let cost = provider.costToday {
                HStack {
                    Text("Today")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("$\(cost, specifier: "%.2f")")
                        .font(.caption.monospacedDigit().bold())
                }
            }
        }
    }

    // MARK: - Medium

    private func mediumView(_ provider: ProviderSummary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack(spacing: 6) {
                Circle()
                    .fill(provider.swiftUIStatusColor)
                    .frame(width: 8, height: 8)
                Text(provider.name)
                    .font(.subheadline.bold())
                    .lineLimit(1)
                Spacer()
                Text(entry.date, style: .time)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            HStack(spacing: 16) {
                // RPM Gauge
                if let rpm = provider.rpm {
                    CircularGaugeView(
                        label: "RPM",
                        pct: rpm.pct,
                        used: rpm.used,
                        limit: rpm.limit
                    )
                }

                // TPM Gauge
                if let tpm = provider.tpm {
                    CircularGaugeView(
                        label: "TPM",
                        pct: tpm.pct,
                        used: tpm.used,
                        limit: tpm.limit
                    )
                }

                Spacer(minLength: 0)

                // Cost column
                VStack(alignment: .trailing, spacing: 4) {
                    if let costToday = provider.costToday {
                        VStack(alignment: .trailing, spacing: 1) {
                            Text("Today")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text("$\(costToday, specifier: "%.2f")")
                                .font(.callout.monospacedDigit().bold())
                        }
                    }
                    if let costMonth = provider.costMonth {
                        VStack(alignment: .trailing, spacing: 1) {
                            Text("Month")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text("$\(costMonth, specifier: "%.0f")")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                    if let budgetPct = provider.budgetPct {
                        Text("\(Int(budgetPct))% of budget")
                            .font(.caption2)
                            .foregroundStyle(pctColor(budgetPct))
                    }
                }
            }
        }
    }
}

// MARK: - Gauge Components

struct GaugeView: View {
    let label: String
    let pct: Double
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(Int(pct))%")
                    .font(.caption2.monospacedDigit().bold())
                    .foregroundStyle(pctColor(pct))
            }
            ProgressView(value: min(pct, 100), total: 100)
                .tint(pctColor(pct))
            Text(detail)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }
}

struct CircularGaugeView: View {
    let label: String
    let pct: Double
    let used: Int
    let limit: Int

    var body: some View {
        VStack(spacing: 4) {
            Gauge(value: min(pct, 100), in: 0...100) {
                EmptyView()
            } currentValueLabel: {
                Text("\(Int(pct))%")
                    .font(.caption2.monospacedDigit().bold())
            }
            .gaugeStyle(.accessoryCircular)
            .tint(Gradient(colors: [.green, .yellow, .red]))
            .scaleEffect(0.85)

            Text(label)
                .font(.caption2.bold())
                .foregroundStyle(.secondary)

            Text("\(formattedNumber(used))/\(formattedNumber(limit))")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.tertiary)
        }
    }
}

// MARK: - Preview

#Preview("Small", as: .systemSmall) {
    ProviderWidget()
} timeline: {
    ProviderEntry.placeholder
}

#Preview("Medium", as: .systemMedium) {
    ProviderWidget()
} timeline: {
    ProviderEntry.placeholder
}
