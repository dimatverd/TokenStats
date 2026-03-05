import SwiftUI
import WidgetKit

// MARK: - Summary Widget (Medium / Large)

struct SummaryWidget: Widget {
    let kind = "SummaryWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: SummaryTimelineProvider()) { entry in
            SummaryWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("All Providers")
        .description("Overview of all configured providers with status, RPM%, and cost.")
        .supportedFamilies([.systemMedium, .systemLarge])
    }
}

// MARK: - Views

struct SummaryWidgetView: View {
    let entry: ProviderEntry

    var body: some View {
        if entry.providers.isEmpty && !entry.isPlaceholder {
            emptyView
        } else {
            providerList
        }
    }

    private var emptyView: some View {
        VStack(spacing: 8) {
            Image(systemName: "key.fill")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No Providers")
                .font(.headline)
            Text("Add an API key in the app.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var providerList: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("TokenStats")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                Spacer()
                Text(entry.date, style: .time)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            ForEach(entry.providers.prefix(5)) { provider in
                SummaryProviderRow(provider: provider)
            }

            if entry.providers.count > 5 {
                Text("+\(entry.providers.count - 5) more")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)
        }
    }
}

struct SummaryProviderRow: View {
    let provider: ProviderSummary

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(provider.swiftUIStatusColor)
                .frame(width: 8, height: 8)

            Text(provider.name)
                .font(.subheadline.weight(.medium))
                .lineLimit(1)

            Spacer(minLength: 4)

            if let rpm = provider.rpm {
                rpmBadge(rpm)
            }

            if let cost = provider.costToday {
                Text("$\(cost, specifier: "%.2f")")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .frame(minWidth: 48, alignment: .trailing)
            }
        }
    }

    private func rpmBadge(_ rpm: LimitSummary) -> some View {
        HStack(spacing: 4) {
            Text("\(Int(rpm.pct))%")
                .font(.caption2.monospacedDigit().bold())
                .foregroundStyle(pctColor(rpm.pct))
            Text("RPM")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(minWidth: 52, alignment: .trailing)
    }
}

// MARK: - Preview

#Preview("Medium", as: .systemMedium) {
    SummaryWidget()
} timeline: {
    ProviderEntry.placeholder
}

#Preview("Large", as: .systemLarge) {
    SummaryWidget()
} timeline: {
    ProviderEntry.placeholder
}
