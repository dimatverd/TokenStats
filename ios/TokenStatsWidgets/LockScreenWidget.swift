import SwiftUI
import WidgetKit

// MARK: - Lock Screen Circular Widget (% remaining)

struct LockScreenCircularWidget: Widget {
    let kind = "LockScreenCircular"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(
            kind: kind,
            intent: SelectProviderIntent.self,
            provider: SingleProviderTimelineProvider()
        ) { entry in
            LockScreenCircularView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Rate Limit")
        .description("Circular gauge showing RPM % remaining for a provider.")
        .supportedFamilies([.accessoryCircular])
    }
}

// MARK: - Lock Screen Rectangular Widget (provider + %)

struct LockScreenRectangularWidget: Widget {
    let kind = "LockScreenRectangular"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(
            kind: kind,
            intent: SelectProviderIntent.self,
            provider: SingleProviderTimelineProvider()
        ) { entry in
            LockScreenRectangularView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Provider Status")
        .description("Provider name with RPM and TPM usage percentages.")
        .supportedFamilies([.accessoryRectangular])
    }
}

// MARK: - Circular View

struct LockScreenCircularView: View {
    let entry: ProviderEntry

    var body: some View {
        if let provider = entry.providers.first,
           let rpm = provider.rpm {
            let remaining = max(0, 100 - rpm.pct)
            Gauge(value: remaining, in: 0...100) {
                EmptyView()
            } currentValueLabel: {
                Text("\(Int(remaining))")
                    .font(.system(.body, design: .rounded, weight: .bold))
            } minimumValueLabel: {
                Text("")
            } maximumValueLabel: {
                Text("")
            }
            .gaugeStyle(.accessoryCircular)
            .widgetAccentable()
        } else {
            Gauge(value: 0, in: 0...100) {
                EmptyView()
            } currentValueLabel: {
                Image(systemName: "questionmark")
                    .font(.caption)
            }
            .gaugeStyle(.accessoryCircular)
        }
    }
}

// MARK: - Rectangular View

struct LockScreenRectangularView: View {
    let entry: ProviderEntry

    var body: some View {
        if let provider = entry.providers.first {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Image(systemName: statusIcon(for: provider))
                        .font(.caption2)
                        .widgetAccentable()
                    Text(provider.name)
                        .font(.headline)
                        .lineLimit(1)
                }

                if let rpm = provider.rpm {
                    HStack(spacing: 0) {
                        Text("RPM ")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("\(Int(rpm.pct))%")
                            .font(.caption2.monospacedDigit().bold())

                        if let tpm = provider.tpm {
                            Text("  TPM ")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text("\(Int(tpm.pct))%")
                                .font(.caption2.monospacedDigit().bold())
                        }
                    }

                    ProgressView(value: min(rpm.pct, 100), total: 100)
                        .widgetAccentable()
                }

                if rpm == nil, let cost = provider.costToday {
                    Text("$\(cost, specifier: "%.2f") today")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        } else {
            VStack(alignment: .leading, spacing: 2) {
                Text("TokenStats")
                    .font(.headline)
                Text("No provider selected")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var rpm: LimitSummary? {
        entry.providers.first?.rpm
    }

    private func statusIcon(for provider: ProviderSummary) -> String {
        switch provider.statusColor {
        case "green": return "checkmark.circle.fill"
        case "yellow": return "exclamationmark.triangle.fill"
        case "red": return "xmark.circle.fill"
        default: return "circle.dotted"
        }
    }
}

// MARK: - Previews

#Preview("Circular", as: .accessoryCircular) {
    LockScreenCircularWidget()
} timeline: {
    ProviderEntry.placeholder
}

#Preview("Rectangular", as: .accessoryRectangular) {
    LockScreenRectangularWidget()
} timeline: {
    ProviderEntry.placeholder
}
