import WidgetKit
import SwiftUI

// MARK: - Timeline Entry

struct ProviderEntry: TimelineEntry {
    let date: Date
    let providers: [ProviderSummary]
    let isPlaceholder: Bool

    static var placeholder: ProviderEntry {
        ProviderEntry(
            date: .now,
            providers: [
                ProviderSummary(
                    providerId: "openai",
                    name: "OpenAI",
                    status: .ok,
                    rpm: LimitSummary(used: 45, limit: 60, pct: 75),
                    tpm: LimitSummary(used: 80000, limit: 150000, pct: 53.3),
                    costToday: 12.50,
                    costMonth: 142.30,
                    budgetMonth: 200,
                    budgetPct: 71.15
                ),
                ProviderSummary(
                    providerId: "anthropic",
                    name: "Anthropic",
                    status: .ok,
                    rpm: LimitSummary(used: 30, limit: 50, pct: 60),
                    tpm: LimitSummary(used: 40000, limit: 100000, pct: 40),
                    costToday: 8.20,
                    costMonth: 95.00,
                    budgetMonth: 150,
                    budgetPct: 63.3
                )
            ],
            isPlaceholder: true
        )
    }

    static var empty: ProviderEntry {
        ProviderEntry(date: .now, providers: [], isPlaceholder: false)
    }
}

// MARK: - Shared Timeline Provider

struct SummaryTimelineProvider: TimelineProvider {
    typealias Entry = ProviderEntry

    func placeholder(in context: Context) -> ProviderEntry {
        .placeholder
    }

    func getSnapshot(in context: Context, completion: @escaping (ProviderEntry) -> Void) {
        if context.isPreview {
            completion(.placeholder)
            return
        }
        Task {
            let entry = await fetchEntry()
            completion(entry)
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ProviderEntry>) -> Void) {
        Task {
            let entry = await fetchEntry()
            let refreshDate = Date().addingTimeInterval(15 * 60)
            let timeline = Timeline(entries: [entry], policy: .after(refreshDate))
            completion(timeline)
        }
    }

    private func fetchEntry() async -> ProviderEntry {
        do {
            let summary = try await APIClient.shared.getSummary()
            return ProviderEntry(
                date: .now,
                providers: summary.providers,
                isPlaceholder: false
            )
        } catch {
            return .empty
        }
    }
}

// MARK: - Single Provider Intent + Provider

struct SingleProviderTimelineProvider: AppIntentTimelineProvider {
    typealias Entry = ProviderEntry
    typealias Intent = SelectProviderIntent

    func placeholder(in context: Context) -> ProviderEntry {
        .placeholder
    }

    func snapshot(for configuration: SelectProviderIntent, in context: Context) async -> ProviderEntry {
        if context.isPreview {
            return .placeholder
        }
        return await fetchEntry(for: configuration.providerId)
    }

    func timeline(for configuration: SelectProviderIntent, in context: Context) async -> Timeline<ProviderEntry> {
        let entry = await fetchEntry(for: configuration.providerId)
        let refreshDate = Date().addingTimeInterval(15 * 60)
        return Timeline(entries: [entry], policy: .after(refreshDate))
    }

    private func fetchEntry(for providerId: String?) async -> ProviderEntry {
        do {
            let summary = try await APIClient.shared.getSummary()
            if let targetId = providerId,
               let provider = summary.providers.first(where: { $0.providerId == targetId }) {
                return ProviderEntry(date: .now, providers: [provider], isPlaceholder: false)
            }
            // Fall back to first provider if none selected
            if let first = summary.providers.first {
                return ProviderEntry(date: .now, providers: [first], isPlaceholder: false)
            }
            return .empty
        } catch {
            return .empty
        }
    }
}

// MARK: - App Intent for Provider Selection

import AppIntents

struct SelectProviderIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Select Provider"
    static var description: IntentDescription = "Choose which provider to display."

    @Parameter(title: "Provider ID")
    var providerId: String?

    init() {}

    init(providerId: String) {
        self.providerId = providerId
    }
}

// MARK: - Color Helpers

extension ProviderSummary {
    var swiftUIStatusColor: Color {
        switch statusColor {
        case "green": return .green
        case "yellow": return .yellow
        case "red": return .red
        default: return .gray
        }
    }
}

func formattedNumber(_ n: Int) -> String {
    if n >= 1_000_000 { return "\(n / 1_000_000)M" }
    if n >= 1_000 { return "\(n / 1_000)K" }
    return "\(n)"
}

func pctColor(_ pct: Double) -> Color {
    if pct >= 95 { return .red }
    if pct >= 80 { return .yellow }
    return .green
}
