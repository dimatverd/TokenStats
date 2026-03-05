import SwiftUI
import WidgetKit

// MARK: - Timeline Entry

struct ComplicationEntry: TimelineEntry {
    let date: Date
    let providers: [ProviderSummary]

    /// Maximum RPM percentage across all providers.
    var maxRpmPct: Double {
        providers.compactMap { $0.rpm?.pct }.max() ?? 0
    }

    /// Maximum TPM percentage across all providers.
    var maxTpmPct: Double {
        providers.compactMap { $0.tpm?.pct }.max() ?? 0
    }

    /// The higher of max RPM% and max TPM%.
    var peakUsagePct: Double {
        max(maxRpmPct, maxTpmPct)
    }

    /// Total cost today across all providers.
    var totalCostToday: Double {
        providers.compactMap { $0.costToday }.reduce(0, +)
    }

    /// Short label pairs for inline display, e.g. "CL: 5%"
    var inlineText: String {
        let items = providers.prefix(3).map { p -> String in
            let abbrev = abbreviation(for: p.name)
            let pct = Int(max(p.rpm?.pct ?? 0, p.tpm?.pct ?? 0))
            return "\(abbrev): \(pct)%"
        }
        return items.joined(separator: " | ")
    }

    static let placeholder = ComplicationEntry(
        date: .now,
        providers: [
            ProviderSummary(
                providerId: "anthropic",
                name: "Anthropic",
                status: .ok,
                rpm: LimitSummary(used: 30, limit: 600, pct: 5.0),
                tpm: LimitSummary(used: 5000, limit: 100000, pct: 5.0),
                costToday: 1.23,
                costMonth: 34.56,
                budgetMonth: 100.0,
                budgetPct: 34.56
            ),
            ProviderSummary(
                providerId: "openai",
                name: "OpenAI",
                status: .ok,
                rpm: LimitSummary(used: 70, limit: 600, pct: 11.7),
                tpm: LimitSummary(used: 12000, limit: 100000, pct: 12.0),
                costToday: 2.45,
                costMonth: 56.78,
                budgetMonth: 200.0,
                budgetPct: 28.39
            )
        ]
    )
}

// MARK: - Helpers

private func abbreviation(for name: String) -> String {
    switch name.lowercased() {
    case let n where n.contains("anthropic"): return "CL"
    case let n where n.contains("openai"): return "OA"
    case let n where n.contains("google"): return "GG"
    case let n where n.contains("cohere"): return "CO"
    case let n where n.contains("mistral"): return "MI"
    default:
        return String(name.prefix(2)).uppercased()
    }
}

private func gaugeColor(for pct: Double) -> Color {
    if pct >= 95 { return .red }
    if pct >= 80 { return .yellow }
    return .green
}

// MARK: - Accessory Circular

/// Circular gauge showing peak usage % across all providers.
struct AccessoryCircularView: View {
    let entry: ComplicationEntry

    var body: some View {
        let pct = entry.peakUsagePct / 100.0
        Gauge(value: pct) {
            Text("TS")
                .font(.system(size: 8, weight: .semibold))
        } currentValueLabel: {
            Text("\(Int(entry.peakUsagePct))")
                .font(.system(size: 14, weight: .bold, design: .rounded))
        }
        .gaugeStyle(.accessoryCircular)
        .tint(gaugeColor(for: entry.peakUsagePct))
    }
}

// MARK: - Accessory Rectangular

/// Rectangular view: provider name + RPM% bar + daily cost.
struct AccessoryRectangularView: View {
    let entry: ComplicationEntry

    var body: some View {
        if let top = topProvider {
            VStack(alignment: .leading, spacing: 2) {
                Text(top.name)
                    .font(.system(size: 12, weight: .semibold))
                    .widgetAccentable()

                let rpmPct = top.rpm?.pct ?? 0
                ProgressView(value: min(rpmPct / 100.0, 1.0)) {
                    Text("RPM \(Int(rpmPct))%")
                        .font(.system(size: 10))
                }
                .tint(gaugeColor(for: rpmPct))

                Text("$\(entry.totalCostToday, specifier: "%.2f") today")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }
        } else {
            VStack(alignment: .leading, spacing: 2) {
                Text("TokenStats")
                    .font(.system(size: 12, weight: .semibold))
                Text("No providers")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }
        }
    }

    /// Provider with the highest peak usage.
    private var topProvider: ProviderSummary? {
        entry.providers.max { a, b in
            max(a.rpm?.pct ?? 0, a.tpm?.pct ?? 0) < max(b.rpm?.pct ?? 0, b.tpm?.pct ?? 0)
        }
    }
}

// MARK: - Accessory Inline

/// Inline text: "CL: 5% | OA: 12%"
struct AccessoryInlineView: View {
    let entry: ComplicationEntry

    var body: some View {
        Text(entry.inlineText.isEmpty ? "TokenStats" : entry.inlineText)
    }
}

// MARK: - Accessory Corner

/// Corner gauge showing peak usage %.
struct AccessoryCornerView: View {
    let entry: ComplicationEntry

    var body: some View {
        let pct = entry.peakUsagePct / 100.0
        Text("\(Int(entry.peakUsagePct))%")
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .widgetLabel {
                Gauge(value: pct) {
                    Text("API")
                } currentValueLabel: {
                    Text("\(Int(entry.peakUsagePct))%")
                } minimumValueLabel: {
                    Text("0")
                } maximumValueLabel: {
                    Text("100")
                }
                .tint(gaugeColor(for: entry.peakUsagePct))
            }
    }
}

// MARK: - Unified Complication View

struct TokenStatsComplicationView: View {
    @Environment(\.widgetFamily) var family
    let entry: ComplicationEntry

    var body: some View {
        switch family {
        case .accessoryCircular:
            AccessoryCircularView(entry: entry)
        case .accessoryRectangular:
            AccessoryRectangularView(entry: entry)
        case .accessoryInline:
            AccessoryInlineView(entry: entry)
        case .accessoryCorner:
            AccessoryCornerView(entry: entry)
        @unknown default:
            AccessoryCircularView(entry: entry)
        }
    }
}
