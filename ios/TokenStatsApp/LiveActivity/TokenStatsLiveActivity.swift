import ActivityKit
import SwiftUI
import WidgetKit

// MARK: - Attributes

struct TokenStatsAttributes: ActivityAttributes {
    /// The provider name (e.g. "OpenAI", "Anthropic")
    let providerName: String
    /// The limit type being tracked
    let limitType: LimitType

    enum LimitType: String, Codable, Hashable {
        case rpm = "RPM"
        case tpm = "TPM"
    }

    // MARK: - Content State

    struct ContentState: Codable, Hashable {
        /// Current usage percentage (0...100)
        let pct: Double
        /// Number of units used
        let used: Int
        /// Total limit
        let limit: Int

        var remaining: Int { max(limit - used, 0) }

        var tintColor: String {
            if pct >= 95 { return "red" }
            if pct >= 80 { return "yellow" }
            return "green"
        }
    }
}

// MARK: - Live Activity Widget

@available(iOS 16.1, *)
struct TokenStatsLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: TokenStatsAttributes.self) { context in
            // Lock Screen / Banner view
            lockScreenView(context: context)
        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded regions
                DynamicIslandExpandedRegion(.leading) {
                    Label(context.attributes.providerName, systemImage: providerIcon(for: context.attributes.providerName))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("\(Int(context.state.pct))%")
                        .font(.title2.bold())
                        .foregroundColor(color(for: context.state.pct))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(spacing: 6) {
                        Gauge(value: context.state.pct, in: 0...100) {
                            Text(context.attributes.limitType.rawValue)
                        } currentValueLabel: {
                            Text("\(Int(context.state.pct))%")
                        }
                        .gaugeStyle(.accessoryLinear)
                        .tint(color(for: context.state.pct))

                        Text("\(formatNumber(context.state.remaining)) remaining")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    .padding(.top, 4)
                }
            } compactLeading: {
                Image(systemName: providerIcon(for: context.attributes.providerName))
                    .foregroundColor(color(for: context.state.pct))
            } compactTrailing: {
                Text("\(Int(context.state.pct))%")
                    .font(.caption.bold())
                    .foregroundColor(color(for: context.state.pct))
            } minimal: {
                Text("\(Int(context.state.pct))%")
                    .font(.caption2)
                    .foregroundColor(color(for: context.state.pct))
            }
        }
    }

    // MARK: - Lock Screen View

    @ViewBuilder
    private func lockScreenView(context: ActivityViewContext<TokenStatsAttributes>) -> some View {
        HStack(spacing: 12) {
            Image(systemName: providerIcon(for: context.attributes.providerName))
                .font(.title2)
                .foregroundColor(color(for: context.state.pct))

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(context.attributes.providerName)
                        .font(.headline)
                    Spacer()
                    Text("\(Int(context.state.pct))%")
                        .font(.headline.bold())
                        .foregroundColor(color(for: context.state.pct))
                }

                ProgressView(value: context.state.pct, total: 100)
                    .tint(color(for: context.state.pct))

                HStack {
                    Text(context.attributes.limitType.rawValue)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Spacer()
                    Text("\(formatNumber(context.state.used)) / \(formatNumber(context.state.limit))")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
    }

    // MARK: - Helpers

    private func color(for pct: Double) -> Color {
        if pct >= 95 { return .red }
        if pct >= 80 { return .yellow }
        return .green
    }

    private func providerIcon(for name: String) -> String {
        switch name.lowercased() {
        case let n where n.contains("openai"):
            return "brain.head.profile"
        case let n where n.contains("anthropic"):
            return "sparkle"
        case let n where n.contains("google"):
            return "globe"
        default:
            return "chart.bar.fill"
        }
    }

    private func formatNumber(_ value: Int) -> String {
        if value >= 1_000_000 {
            return String(format: "%.1fM", Double(value) / 1_000_000)
        } else if value >= 1_000 {
            return String(format: "%.1fK", Double(value) / 1_000)
        }
        return "\(value)"
    }
}
