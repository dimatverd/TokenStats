import SwiftUI
import Charts

enum TimeRange: String, CaseIterable, Identifiable {
    case oneHour = "1h"
    case sixHours = "6h"
    case twentyFourHours = "24h"

    var id: String { rawValue }

    var seconds: TimeInterval {
        switch self {
        case .oneHour: return 3_600
        case .sixHours: return 21_600
        case .twentyFourHours: return 86_400
        }
    }
}

struct HistoryChartView: View {
    let history: HistoryResponse

    @State private var selectedRange: TimeRange = .twentyFourHours

    private var filteredPoints: [HistoryPoint] {
        let cutoff = Date().addingTimeInterval(-selectedRange.seconds)
        return history.points.filter { $0.timestamp >= cutoff }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Picker("Time Range", selection: $selectedRange) {
                ForEach(TimeRange.allCases) { range in
                    Text(range.rawValue).tag(range)
                }
            }
            .pickerStyle(.segmented)

            if filteredPoints.isEmpty {
                Text("No history data for this time range.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 24)
            } else {
                rateLimitChart
                costChart
            }
        }
    }

    // MARK: - Rate Limit Chart (RPM% and TPM% lines with threshold lines)

    private var rateLimitChart: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Rate Limit Usage")
                .font(.subheadline.bold())

            Chart {
                ForEach(filteredPoints) { point in
                    LineMark(
                        x: .value("Time", point.timestamp),
                        y: .value("Percent", point.rpmPct)
                    )
                    .foregroundStyle(.blue)
                    .symbol(Circle())
                    .symbolSize(16)
                    .interpolationMethod(.catmullRom)
                }
                .foregroundStyle(by: .value("Metric", "RPM %"))

                ForEach(filteredPoints) { point in
                    LineMark(
                        x: .value("Time", point.timestamp),
                        y: .value("Percent", point.tpmPct)
                    )
                    .foregroundStyle(.purple)
                    .symbol(Circle())
                    .symbolSize(16)
                    .interpolationMethod(.catmullRom)
                }
                .foregroundStyle(by: .value("Metric", "TPM %"))

                // Warning threshold at 80%
                RuleMark(y: .value("Warning", 80))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [6, 4]))
                    .foregroundStyle(.yellow)
                    .annotation(position: .trailing, alignment: .leading) {
                        Text("80%")
                            .font(.caption2)
                            .foregroundStyle(.yellow)
                    }

                // Critical threshold at 95%
                RuleMark(y: .value("Critical", 95))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [6, 4]))
                    .foregroundStyle(.red)
                    .annotation(position: .trailing, alignment: .leading) {
                        Text("95%")
                            .font(.caption2)
                            .foregroundStyle(.red)
                    }
            }
            .chartForegroundStyleScale([
                "RPM %": Color.blue,
                "TPM %": Color.purple
            ])
            .chartYScale(domain: 0...105)
            .chartYAxis {
                AxisMarks(values: [0, 25, 50, 75, 100]) { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let v = value.as(Int.self) {
                            Text("\(v)%")
                                .font(.caption2)
                        }
                    }
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                    AxisGridLine()
                    AxisValueLabel(format: .dateTime.hour().minute())
                }
            }
            .frame(height: 200)
        }
    }

    // MARK: - Cost Accumulation Chart (area chart)

    private var costChart: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Cost Accumulation")
                .font(.subheadline.bold())

            Chart {
                ForEach(cumulativeCostPoints) { point in
                    AreaMark(
                        x: .value("Time", point.timestamp),
                        y: .value("Cost", point.cumulativeCost)
                    )
                    .foregroundStyle(
                        .linearGradient(
                            colors: [Color.green.opacity(0.4), Color.green.opacity(0.05)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .interpolationMethod(.catmullRom)

                    LineMark(
                        x: .value("Time", point.timestamp),
                        y: .value("Cost", point.cumulativeCost)
                    )
                    .foregroundStyle(.green)
                    .interpolationMethod(.catmullRom)
                }
            }
            .chartYAxis {
                AxisMarks { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let v = value.as(Double.self) {
                            Text("$\(v, specifier: "%.2f")")
                                .font(.caption2)
                        }
                    }
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                    AxisGridLine()
                    AxisValueLabel(format: .dateTime.hour().minute())
                }
            }
            .frame(height: 160)
        }
    }

    // MARK: - Helpers

    private var cumulativeCostPoints: [CumulativeCostPoint] {
        let sorted = filteredPoints.sorted { $0.timestamp < $1.timestamp }
        var cumulative = 0.0
        return sorted.map { point in
            cumulative += point.costUsd
            return CumulativeCostPoint(timestamp: point.timestamp, cumulativeCost: cumulative)
        }
    }
}

private struct CumulativeCostPoint: Identifiable {
    var id: Date { timestamp }
    let timestamp: Date
    let cumulativeCost: Double
}
