import ActivityKit
import Foundation

/// Manages the lifecycle of TokenStats Live Activities.
/// Starts a Live Activity when a provider's usage crosses 80%,
/// updates it as usage changes, and ends it when usage drops below the threshold.
@available(iOS 16.1, *)
@MainActor
final class LiveActivityManager: ObservableObject {

    static let shared = LiveActivityManager()

    /// Threshold percentage at which a Live Activity is started.
    static let activationThreshold: Double = 80.0

    /// Tracks the currently active Live Activity, keyed by "providerName-limitType".
    private var activeActivities: [String: Activity<TokenStatsAttributes>] = [:]

    private init() {}

    // MARK: - Public API

    /// Starts a Live Activity for the given provider and limit type.
    /// If an activity already exists for this provider+limitType, it updates instead.
    func startActivity(
        provider: String,
        limitType: TokenStatsAttributes.LimitType,
        pct: Double,
        used: Int,
        limit: Int
    ) {
        let key = activityKey(provider: provider, limitType: limitType)

        // If already tracking this provider+limitType, just update
        if activeActivities[key] != nil {
            updateActivity(provider: provider, limitType: limitType, pct: pct, used: used, limit: limit)
            return
        }

        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }

        let attributes = TokenStatsAttributes(
            providerName: provider,
            limitType: limitType
        )
        let state = TokenStatsAttributes.ContentState(
            pct: pct,
            used: used,
            limit: limit
        )

        do {
            let activity = try Activity.request(
                attributes: attributes,
                content: .init(state: state, staleDate: Date().addingTimeInterval(120)),
                pushType: nil
            )
            activeActivities[key] = activity
        } catch {
            print("[LiveActivityManager] Failed to start activity for \(key): \(error)")
        }
    }

    /// Updates the Live Activity state for the given provider and limit type.
    func updateActivity(
        provider: String,
        limitType: TokenStatsAttributes.LimitType,
        pct: Double,
        used: Int,
        limit: Int
    ) {
        let key = activityKey(provider: provider, limitType: limitType)
        guard let activity = activeActivities[key] else { return }

        let updatedState = TokenStatsAttributes.ContentState(
            pct: pct,
            used: used,
            limit: limit
        )

        Task {
            await activity.update(
                ActivityContent(state: updatedState, staleDate: Date().addingTimeInterval(120))
            )
        }
    }

    /// Ends the Live Activity for the given provider and limit type.
    func endActivity(
        provider: String,
        limitType: TokenStatsAttributes.LimitType
    ) {
        let key = activityKey(provider: provider, limitType: limitType)
        guard let activity = activeActivities[key] else { return }

        let finalState = activity.content.state

        Task {
            await activity.end(
                ActivityContent(state: finalState, staleDate: nil),
                dismissalPolicy: .immediate
            )
        }
        activeActivities.removeValue(forKey: key)
    }

    /// Ends all active Live Activities.
    func endAllActivities() {
        for (key, activity) in activeActivities {
            let finalState = activity.content.state
            Task {
                await activity.end(
                    ActivityContent(state: finalState, staleDate: nil),
                    dismissalPolicy: .immediate
                )
            }
            activeActivities.removeValue(forKey: key)
        }
    }

    /// Evaluates a provider summary and starts/updates/ends Live Activities as needed.
    /// Call this from DashboardViewModel after each data refresh.
    func evaluateProvider(_ provider: ProviderSummary) {
        // Check RPM
        if let rpm = provider.rpm {
            handleLimitCheck(
                provider: provider.name,
                limitType: .rpm,
                pct: rpm.pct,
                used: rpm.used,
                limit: rpm.limit
            )
        }

        // Check TPM
        if let tpm = provider.tpm {
            handleLimitCheck(
                provider: provider.name,
                limitType: .tpm,
                pct: tpm.pct,
                used: tpm.used,
                limit: tpm.limit
            )
        }
    }

    // MARK: - Private

    private func handleLimitCheck(
        provider: String,
        limitType: TokenStatsAttributes.LimitType,
        pct: Double,
        used: Int,
        limit: Int
    ) {
        let key = activityKey(provider: provider, limitType: limitType)
        let isActive = activeActivities[key] != nil

        if pct >= Self.activationThreshold {
            if isActive {
                updateActivity(provider: provider, limitType: limitType, pct: pct, used: used, limit: limit)
            } else {
                startActivity(provider: provider, limitType: limitType, pct: pct, used: used, limit: limit)
            }
        } else if isActive {
            // Usage dropped below threshold — dismiss the activity
            endActivity(provider: provider, limitType: limitType)
        }
    }

    private func activityKey(provider: String, limitType: TokenStatsAttributes.LimitType) -> String {
        "\(provider)-\(limitType.rawValue)"
    }
}
