import SwiftUI
import WidgetKit

@main
struct TokenStatsWidgetBundle: WidgetBundle {
    var body: some Widget {
        SummaryWidget()
        ProviderWidget()
        LockScreenCircularWidget()
        LockScreenRectangularWidget()
    }
}
