import WidgetKit
import SwiftUI

struct TokenStatsComplicationProvider: TimelineProvider {
    typealias Entry = ComplicationEntry

    // MARK: - Placeholder

    func placeholder(in context: Context) -> ComplicationEntry {
        .placeholder
    }

    // MARK: - Snapshot

    func getSnapshot(in context: Context, completion: @escaping (ComplicationEntry) -> Void) {
        if context.isPreview {
            completion(.placeholder)
            return
        }
        fetchEntry { entry in
            completion(entry)
        }
    }

    // MARK: - Timeline

    func getTimeline(in context: Context, completion: @escaping (Timeline<ComplicationEntry>) -> Void) {
        fetchEntry { entry in
            // Refresh 15 minutes from now.
            let refreshDate = Calendar.current.date(byAdding: .minute, value: 15, to: entry.date) ?? entry.date.addingTimeInterval(900)
            let timeline = Timeline(entries: [entry], policy: .after(refreshDate))
            completion(timeline)
        }
    }

    // MARK: - Data Fetching

    private func fetchEntry(completion: @escaping (ComplicationEntry) -> Void) {
        Task {
            do {
                let summary = try await APIClient.shared.getSummary()
                let entry = ComplicationEntry(date: .now, providers: summary.providers)
                completion(entry)
            } catch {
                // On failure return an empty entry so the complication still renders.
                let entry = ComplicationEntry(date: .now, providers: [])
                completion(entry)
            }
        }
    }
}

// MARK: - Widget Definition

struct TokenStatsComplication: Widget {
    let kind = "TokenStatsComplication"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: TokenStatsComplicationProvider()) { entry in
            TokenStatsComplicationView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("TokenStats")
        .description("API usage and rate limits at a glance.")
        .supportedFamilies([
            .accessoryCircular,
            .accessoryRectangular,
            .accessoryInline,
            .accessoryCorner
        ])
    }
}

// MARK: - Previews

#if DEBUG
#Preview("Circular", as: .accessoryCircular) {
    TokenStatsComplication()
} timeline: {
    ComplicationEntry.placeholder
}

#Preview("Rectangular", as: .accessoryRectangular) {
    TokenStatsComplication()
} timeline: {
    ComplicationEntry.placeholder
}

#Preview("Inline", as: .accessoryInline) {
    TokenStatsComplication()
} timeline: {
    ComplicationEntry.placeholder
}

#Preview("Corner", as: .accessoryCorner) {
    TokenStatsComplication()
} timeline: {
    ComplicationEntry.placeholder
}
#endif
