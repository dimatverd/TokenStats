# Архитектура клиентских приложений TokenStats

## Содержание

1. [Apple Watch + iOS — MVVM](#1-apple-watch--ios--mvvm)
2. [Навигация](#2-навигация)
3. [Обновление данных](#3-обновление-данных)
4. [Garmin Connect IQ](#4-garmin-connect-iq)
5. [Wear OS](#5-wear-os)
6. [Общие паттерны](#6-общие-паттерны)

---

## 1. Apple Watch + iOS — MVVM

### Обзор архитектуры

Приложение для Apple Watch и iOS построено на паттерне **MVVM (Model-View-ViewModel)** с использованием SwiftUI. Код разделен на три target-а: Shared (общие модели и сервисы), iOS companion app и watchOS app.

```
TokenStats/
├── Shared/
│   ├── Models/           # Swift structs, Codable
│   ├── Services/         # APIClient, KeychainService, WatchConnectivity
│   └── Extensions/       # Расширения стандартных типов
├── TokenStatsApp/        # iOS companion app
│   ├── Views/            # SwiftUI views
│   └── ViewModels/       # ObservableObject классы
├── TokenStatsWatch/      # watchOS app
│   ├── Views/            # SwiftUI views для часов
│   ├── Complications/    # WidgetKit complications
│   └── ViewModels/       # ObservableObject классы
└── TokenStatsWidgets/    # iOS виджеты (WidgetKit)
```

### Models (Swift structs / Codable)

Модели расположены в `Shared/Models/` и используются обоими target-ами. Все модели — value types (`struct`), conforming to `Codable` для автоматической сериализации/десериализации JSON.

```swift
// Shared/Models/Provider.swift

import Foundation

/// Статус провайдера на основе процента использования лимитов
enum ProviderStatus: String, Codable {
    case ok       // < 80%
    case warning  // 80-95%
    case critical // > 95%
    case error    // нет связи / ошибка API
}

/// Метрика с текущим значением, лимитом и процентом использования
struct UsageMetric: Codable, Hashable {
    let used: Int
    let limit: Int
    let pct: Double

    /// Статус на основе процента
    var status: ProviderStatus {
        switch pct {
        case ..<80: return .ok
        case 80..<95: return .warning
        default: return .critical
        }
    }
}

/// Сводка по одному провайдеру — маппится на JSON от бэкенда
struct ProviderSummary: Codable, Identifiable {
    let id: String           // "anthropic", "openai", "vertex"
    let name: String         // "Claude", "OpenAI", "Vertex AI"
    let status: ProviderStatus
    let rpm: UsageMetric     // requests per minute
    let tpm: UsageMetric     // tokens per minute
    let costToday: Double
    let costMonth: Double
    let budgetMonth: Double?
    let budgetPct: Double?

    enum CodingKeys: String, CodingKey {
        case id, name, status, rpm, tpm
        case costToday = "cost_today"
        case costMonth = "cost_month"
        case budgetMonth = "budget_month"
        case budgetPct = "budget_pct"
    }
}
```

```swift
// Shared/Models/TokenUsage.swift

import Foundation

/// Ответ endpoint /api/v1/summary
struct SummaryResponse: Codable {
    let providers: [ProviderSummary]
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case providers
        case updatedAt = "updated_at"
    }
}

/// Точка данных для графика истории потребления
struct UsageHistoryPoint: Codable, Identifiable {
    var id: Date { timestamp }
    let timestamp: Date
    let tokensUsed: Int
    let requestsCount: Int
    let cost: Double

    enum CodingKeys: String, CodingKey {
        case timestamp
        case tokensUsed = "tokens_used"
        case requestsCount = "requests_count"
        case cost
    }
}

/// Настройки подключения к провайдеру (хранится на клиенте для UI)
struct ProviderConfig: Codable, Identifiable {
    let id: String
    let providerType: String
    var isEnabled: Bool
    var displayName: String

    enum CodingKeys: String, CodingKey {
        case id
        case providerType = "provider_type"
        case isEnabled = "is_enabled"
        case displayName = "display_name"
    }
}
```

### ViewModels

ViewModel-ы реализуют протокол `ObservableObject` и содержат `@Published` свойства, за которыми наблюдают View через `@StateObject` или `@ObservedObject`.

```swift
// TokenStatsWatch/ViewModels/WatchViewModel.swift

import Foundation
import Combine

@MainActor
final class WatchViewModel: ObservableObject {

    // MARK: - Published State

    @Published var providers: [ProviderSummary] = []
    @Published var isLoading = false
    @Published var lastUpdated: Date?
    @Published var error: AppError?

    // MARK: - Dependencies

    private let apiClient: APIClientProtocol
    private let connectivityService: WatchConnectivityService
    private var cancellables = Set<AnyCancellable>()

    // MARK: - Init

    init(
        apiClient: APIClientProtocol = APIClient.shared,
        connectivityService: WatchConnectivityService = .shared
    ) {
        self.apiClient = apiClient
        self.connectivityService = connectivityService
        subscribeToConnectivityUpdates()
    }

    // MARK: - Data Loading

    /// Загрузка сводки — вызывается при появлении экрана и pull-to-refresh
    func loadSummary() async {
        guard !isLoading else { return }
        isLoading = true
        error = nil

        do {
            let response: SummaryResponse = try await apiClient.request(.summary)
            providers = response.providers
            lastUpdated = response.updatedAt
        } catch let appError as AppError {
            error = appError
        } catch {
            self.error = .network(error)
        }

        isLoading = false
    }

    /// Возвращает провайдера по id
    func provider(byId id: String) -> ProviderSummary? {
        providers.first { $0.id == id }
    }

    /// Худший статус среди всех провайдеров (для complication)
    var worstStatus: ProviderStatus {
        let statuses = providers.map(\.status)
        if statuses.contains(.critical) { return .critical }
        if statuses.contains(.warning) { return .warning }
        if statuses.contains(.error) { return .error }
        return .ok
    }

    // MARK: - WatchConnectivity

    private func subscribeToConnectivityUpdates() {
        connectivityService.receivedDataPublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] data in
                self?.handleConnectivityData(data)
            }
            .store(in: &cancellables)
    }

    private func handleConnectivityData(_ data: [String: Any]) {
        // Обновление настроек, полученных от iPhone
        if let providersData = data["providers"] as? Data,
           let decoded = try? JSONDecoder().decode([ProviderSummary].self, from: providersData) {
            providers = decoded
            lastUpdated = Date()
        }
    }
}
```

```swift
// TokenStatsApp/ViewModels/DashboardViewModel.swift

import Foundation
import Combine

@MainActor
final class DashboardViewModel: ObservableObject {

    @Published var providers: [ProviderSummary] = []
    @Published var isLoading = false
    @Published var error: AppError?
    @Published var selectedProvider: ProviderSummary?

    private let apiClient: APIClientProtocol
    private let keychainService: KeychainServiceProtocol

    init(
        apiClient: APIClientProtocol = APIClient.shared,
        keychainService: KeychainServiceProtocol = KeychainService.shared
    ) {
        self.apiClient = apiClient
        self.keychainService = keychainService
    }

    func loadSummary() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let response: SummaryResponse = try await apiClient.request(.summary)
            providers = response.providers
        } catch let appError as AppError {
            error = appError
        } catch {
            self.error = .network(error)
        }
    }

    /// Проверяет наличие сохраненного JWT токена
    var isAuthenticated: Bool {
        keychainService.retrieveToken() != nil
    }
}
```

### Views

SwiftUI View отображают данные из ViewModel и отправляют пользовательские действия обратно.

```swift
// TokenStatsWatch/Views/SummaryView.swift

import SwiftUI

struct SummaryView: View {
    @StateObject private var viewModel = WatchViewModel()

    var body: some View {
        NavigationStack {
            List {
                if viewModel.isLoading && viewModel.providers.isEmpty {
                    ProgressView("Загрузка...")
                } else if let error = viewModel.error, viewModel.providers.isEmpty {
                    ErrorRowView(error: error) {
                        Task { await viewModel.loadSummary() }
                    }
                } else {
                    ForEach(viewModel.providers) { provider in
                        NavigationLink(value: provider.id) {
                            ProviderRowView(provider: provider)
                        }
                    }

                    if let updated = viewModel.lastUpdated {
                        Text("Обновлено: \(updated, style: .relative)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("TokenStats")
            .navigationDestination(for: String.self) { providerId in
                ProviderDetailView(
                    providerId: providerId,
                    viewModel: viewModel
                )
            }
            .refreshable {
                await viewModel.loadSummary()
            }
            .task {
                await viewModel.loadSummary()
            }
        }
    }
}
```

### Services

#### APIClient

Центральный сервис для сетевых запросов. Абстрагирует URLSession, обработку ошибок, аутентификацию (JWT).

```swift
// Shared/Services/APIClient.swift

import Foundation

/// Описание API endpoint-ов
enum APIEndpoint {
    case summary
    case summaryCompact
    case limits(provider: String)
    case usage(provider: String)
    case costs(provider: String)
    case history(provider: String)
    case login(email: String, password: String)
    case registerDevice(token: String, platform: String)

    var path: String {
        switch self {
        case .summary:                return "/api/v1/summary"
        case .summaryCompact:         return "/api/v1/summary?format=compact"
        case .limits(let p):          return "/api/v1/limits/\(p)"
        case .usage(let p):           return "/api/v1/usage/\(p)"
        case .costs(let p):           return "/api/v1/costs/\(p)"
        case .history(let p):         return "/api/v1/history/\(p)"
        case .login:                  return "/auth/login"
        case .registerDevice:         return "/api/v1/devices/register"
        }
    }

    var method: String {
        switch self {
        case .login, .registerDevice: return "POST"
        default:                      return "GET"
        }
    }
}

/// Протокол для мокирования в тестах
protocol APIClientProtocol {
    func request<T: Decodable>(_ endpoint: APIEndpoint) async throws -> T
}

final class APIClient: APIClientProtocol {

    static let shared = APIClient()

    private let session: URLSession
    private let baseURL: URL
    private let keychainService: KeychainServiceProtocol
    private let decoder: JSONDecoder

    init(
        baseURL: URL = URL(string: "https://api.tokenstats.app")!,
        keychainService: KeychainServiceProtocol = KeychainService.shared
    ) {
        self.baseURL = baseURL
        self.keychainService = keychainService

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        self.session = URLSession(configuration: config)

        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601
    }

    func request<T: Decodable>(_ endpoint: APIEndpoint) async throws -> T {
        let url = baseURL.appendingPathComponent(endpoint.path)
        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Добавляем JWT из Keychain
        if let token = keychainService.retrieveToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AppError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200..<300:
            return try decoder.decode(T.self, from: data)
        case 401:
            throw AppError.unauthorized
        case 429:
            throw AppError.rateLimited
        case 500..<600:
            throw AppError.serverError(httpResponse.statusCode)
        default:
            throw AppError.httpError(httpResponse.statusCode)
        }
    }
}
```

#### KeychainService

Безопасное хранение JWT токенов и чувствительных данных в iOS/watchOS Keychain.

```swift
// Shared/Services/KeychainService.swift

import Foundation
import Security

protocol KeychainServiceProtocol {
    func saveToken(_ token: String)
    func retrieveToken() -> String?
    func deleteToken()
}

final class KeychainService: KeychainServiceProtocol {

    static let shared = KeychainService()

    private let serviceName = "com.tokenstats.app"
    private let tokenKey = "jwt_access_token"

    func saveToken(_ token: String) {
        let data = Data(token.utf8)

        // Удаляем старый, если есть
        deleteToken()

        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: tokenKey,
            kSecValueData as String:   data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]

        SecItemAdd(query as CFDictionary, nil)
    }

    func retrieveToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: tokenKey,
            kSecReturnData as String:  true,
            kSecMatchLimit as String:  kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess, let data = result as? Data else {
            return nil
        }

        return String(data: data, encoding: .utf8)
    }

    func deleteToken() {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: tokenKey
        ]

        SecItemDelete(query as CFDictionary)
    }
}
```

#### WatchConnectivityService

Двусторонняя коммуникация между iPhone и Apple Watch для передачи настроек и данных.

```swift
// Shared/Services/WatchConnectivityService.swift

import Foundation
import WatchConnectivity
import Combine

final class WatchConnectivityService: NSObject, ObservableObject {

    static let shared = WatchConnectivityService()

    /// Publisher для данных, полученных от парного устройства
    let receivedDataPublisher = PassthroughSubject<[String: Any], Never>()

    private override init() {
        super.init()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    /// Отправка настроек с iPhone на Apple Watch
    func sendProvidersToWatch(_ providers: [ProviderSummary]) {
        guard WCSession.default.isReachable else { return }

        if let data = try? JSONEncoder().encode(providers) {
            WCSession.default.sendMessage(
                ["providers": data],
                replyHandler: nil,
                errorHandler: { error in
                    print("WC send error: \(error.localizedDescription)")
                }
            )
        }
    }

    /// Передача JWT токена на часы через applicationContext (гарантированная доставка)
    func transferAuthToken(_ token: String) {
        try? WCSession.default.updateApplicationContext(["jwt": token])
    }
}

extension WatchConnectivityService: WCSessionDelegate {

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        // Логирование
    }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        receivedDataPublisher.send(message)
    }

    func session(
        _ session: WCSession,
        didReceiveApplicationContext applicationContext: [String: Any]
    ) {
        // Получение JWT на часах
        if let jwt = applicationContext["jwt"] as? String {
            KeychainService.shared.saveToken(jwt)
        }
    }

    #if os(iOS)
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
    #endif
}
```

---

## 2. Навигация

### watchOS — NavigationStack

watchOS 10+ использует `NavigationStack` с value-based навигацией. Каждый экран идентифицируется Hashable-значением.

```
┌───────────────┐
│  SummaryView  │  ← Стартовый экран, список провайдеров
│  (корень)     │
└──────┬────────┘
       │ NavigationLink(value: providerId)
       ▼
┌──────────────────┐
│ ProviderDetail   │  ← Круговые прогресс-бары RPM/TPM/Budget
│ View             │
└──────┬───────────┘
       │ NavigationLink(value: .history)
       ▼
┌──────────────────┐
│ HistoryChart     │  ← График потребления за 24ч/7д (Swift Charts)
│ View             │
└──────────────────┘
```

```swift
// TokenStatsWatch/TokenStatsWatchApp.swift

import SwiftUI

@main
struct TokenStatsWatchApp: App {
    var body: some Scene {
        WindowGroup {
            SummaryView()
        }
    }
}
```

Navigation destination определяется через enum:

```swift
enum WatchDestination: Hashable {
    case providerDetail(id: String)
    case history(providerId: String)
}
```

### iOS — NavigationStack + TabView

iOS companion app использует `TabView` с тремя вкладками и `NavigationStack` внутри каждой.

```
┌─────────────────────────────────────────────┐
│                  TabView                     │
├───────────┬──────────────┬──────────────────┤
│ Dashboard │   History    │    Settings      │
│   Tab     │    Tab       │      Tab         │
├───────────┼──────────────┼──────────────────┤
│           │              │                  │
│ Dashboard │ HistoryList  │ SettingsView     │
│ View      │ View         │                  │
│   │       │   │          │ ├─ Account       │
│   ▼       │   ▼          │ ├─ Providers     │
│ Provider  │ HistoryChart │ │  ├─ Anthropic  │
│ Detail    │ View         │ │  ├─ OpenAI     │
│           │              │ │  └─ Vertex AI  │
│           │              │ └─ Notifications │
└───────────┴──────────────┴──────────────────┘
```

```swift
// TokenStatsApp/Views/MainTabView.swift

import SwiftUI

struct MainTabView: View {
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                DashboardView()
            }
            .tabItem {
                Label("Dashboard", systemImage: "chart.bar.fill")
            }
            .tag(0)

            NavigationStack {
                HistoryListView()
            }
            .tabItem {
                Label("History", systemImage: "clock.fill")
            }
            .tag(1)

            NavigationStack {
                SettingsView()
            }
            .tabItem {
                Label("Settings", systemImage: "gearshape.fill")
            }
            .tag(2)
        }
    }
}
```

---

## 3. Обновление данных

Приложение использует несколько стратегий обновления для обеспечения актуальности данных.

### 3.1 Background App Refresh

watchOS и iOS выполняют фоновое обновление данных каждые 15 минут. Система планирует обновления с учетом батареи и времени использования.

```swift
// TokenStatsWatch/BackgroundTasks.swift

import WatchKit
import Foundation

final class ExtensionDelegate: NSObject, WKApplicationDelegate {

    func applicationDidFinishLaunching() {
        scheduleBackgroundRefresh()
    }

    func handle(_ backgroundTasks: Set<WKRefreshBackgroundTask>) {
        for task in backgroundTasks {
            switch task {
            case let refreshTask as WKApplicationRefreshBackgroundTask:
                Task {
                    await performBackgroundFetch()
                    scheduleBackgroundRefresh()
                    refreshTask.setTaskCompletedWithSnapshot(true)
                }
            default:
                task.setTaskCompletedWithSnapshot(false)
            }
        }
    }

    private func scheduleBackgroundRefresh() {
        let targetDate = Date().addingTimeInterval(15 * 60) // 15 минут
        WKApplication.shared().scheduleBackgroundRefresh(
            withPreferredDate: targetDate,
            userInfo: nil
        ) { error in
            if let error {
                print("BG schedule error: \(error.localizedDescription)")
            }
        }
    }

    private func performBackgroundFetch() async {
        let apiClient = APIClient.shared
        do {
            let response: SummaryResponse = try await apiClient.request(.summary)
            // Сохраняем в UserDefaults для complications
            if let data = try? JSONEncoder().encode(response) {
                UserDefaults.standard.set(data, forKey: "cached_summary")
            }
        } catch {
            // Данные не обновились, используем кэш
        }
    }
}
```

### 3.2 WidgetKit Timeline

Complications на циферблате обновляются через WidgetKit timeline provider. Timeline возвращает набор entries с таймстампами, система отображает актуальный entry.

```swift
// TokenStatsWatch/Complications/ComplicationViews.swift

import WidgetKit
import SwiftUI

struct ProviderEntry: TimelineEntry {
    let date: Date
    let providerName: String
    let status: ProviderStatus
    let tpmPercent: Double
    let costToday: Double
}

struct TokenStatsTimelineProvider: TimelineProvider {

    func placeholder(in context: Context) -> ProviderEntry {
        ProviderEntry(
            date: .now,
            providerName: "Claude",
            status: .ok,
            tpmPercent: 25.0,
            costToday: 10.00
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (ProviderEntry) -> Void) {
        let entry = loadCachedEntry() ?? placeholder(in: context)
        completion(entry)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ProviderEntry>) -> Void) {
        Task {
            let apiClient = APIClient.shared

            do {
                let response: SummaryResponse = try await apiClient.request(.summary)

                // Берем провайдера с худшим статусом для complication
                let worst = response.providers.max(by: { $0.tpm.pct < $1.tpm.pct })

                let entry = ProviderEntry(
                    date: .now,
                    providerName: worst?.name ?? "N/A",
                    status: worst?.status ?? .ok,
                    tpmPercent: worst?.tpm.pct ?? 0,
                    costToday: worst?.costToday ?? 0
                )

                // Следующее обновление через 15 минут
                let nextUpdate = Date().addingTimeInterval(15 * 60)
                let timeline = Timeline(entries: [entry], policy: .after(nextUpdate))
                completion(timeline)

            } catch {
                // При ошибке повторяем через 5 минут
                let entry = loadCachedEntry() ?? placeholder(in: context)
                let retry = Date().addingTimeInterval(5 * 60)
                let timeline = Timeline(entries: [entry], policy: .after(retry))
                completion(timeline)
            }
        }
    }

    private func loadCachedEntry() -> ProviderEntry? {
        guard let data = UserDefaults.standard.data(forKey: "cached_summary"),
              let response = try? JSONDecoder().decode(SummaryResponse.self, from: data),
              let provider = response.providers.first else {
            return nil
        }

        return ProviderEntry(
            date: response.updatedAt,
            providerName: provider.name,
            status: provider.status,
            tpmPercent: provider.tpm.pct,
            costToday: provider.costToday
        )
    }
}
```

### 3.3 WatchConnectivity

Передача данных между iPhone и Apple Watch работает в трех режимах:

| Метод | Когда используется | Гарантия доставки |
|---|---|---|
| `sendMessage()` | Оба устройства активны, реальное время | Нет (best-effort) |
| `updateApplicationContext()` | Передача настроек (JWT, конфигурация) | Да, последнее значение |
| `transferUserInfo()` | Передача данных, которые не должны потеряться | Да, очередь FIFO |

Поток данных:
```
iPhone                              Apple Watch
  │                                      │
  ├── Логин → JWT ──────────────────────►│ applicationContext
  │                                      │ → сохраняет в Keychain
  │                                      │
  ├── Настройки провайдера ─────────────►│ applicationContext
  │                                      │
  ├── Свежие данные (если reachable) ───►│ sendMessage
  │                                      │
  │◄──────── Запрос обновления ──────────┤ sendMessage
  │                                      │
```

### 3.4 Pull-to-Refresh

Ручное обновление доступно на всех экранах со списками через модификатор `.refreshable`:

```swift
List { /* ... */ }
    .refreshable {
        await viewModel.loadSummary()
    }
```

На watchOS pull-to-refresh поддерживается нативно начиная с watchOS 10.

---

## 4. Garmin Connect IQ

### Архитектура Monkey C: App -> View -> Delegate

Garmin Connect IQ использует строгую архитектуру с разделением на три основных компонента.

```
┌──────────────────┐
│ TokenStatsApp.mc │  ← Application: жизненный цикл, точка входа
│ (AppBase)        │
└──────┬───────────┘
       │ создает
       ▼
┌──────────────────┐     ┌──────────────────────┐
│TokenStatsView.mc │◄───►│TokenStatsDelegate.mc │
│ (WatchUi.View)   │     │ (WatchUi.BehaviorDlg)│
│ Отрисовка UI     │     │ Обработка ввода      │
└──────────────────┘     └──────────────────────┘
       │                          │
       ▼                          ▼
┌──────────────────┐     ┌──────────────────────┐
│ DataModel.mc     │     │ ApiService.mc        │
│ Хранение данных  │     │ HTTP-запросы         │
└──────────────────┘     └──────────────────────┘
```

#### Application (точка входа)

```c
// source/TokenStatsApp.mc

using Toybox.Application;
using Toybox.WatchUi;

class TokenStatsApp extends Application.AppBase {

    private var _model as DataModel?;

    function initialize() {
        AppBase.initialize();
    }

    function onStart(state as Dictionary?) as Void {
        _model = new DataModel();
    }

    function onStop(state as Dictionary?) as Void {
    }

    // Widget: glance view — отображается в быстром списке виджетов
    function getGlanceView() as Array<WatchUi.GlanceView>? {
        return [new TokenStatsGlanceView(_model)] as Array<WatchUi.GlanceView>;
    }

    // Основной экран при открытии виджета
    function getInitialView() as Array<WatchUi.Views or WatchUi.InputDelegates>? {
        var view = new TokenStatsView(_model);
        var delegate = new TokenStatsDelegate(view, _model);
        return [view, delegate] as Array<WatchUi.Views or WatchUi.InputDelegates>;
    }

    function getModel() as DataModel {
        return _model;
    }
}
```

#### View (отрисовка)

```c
// source/TokenStatsView.mc

using Toybox.WatchUi;
using Toybox.Graphics;

class TokenStatsView extends WatchUi.View {

    private var _model as DataModel;
    private var _currentPage as Number = 0;

    function initialize(model as DataModel) {
        View.initialize();
        _model = model;
    }

    function onLayout(dc as Dc) as Void {
        // Загружаем layout из ресурсов (опционально)
    }

    function onShow() as Void {
        // Запускаем загрузку данных при показе экрана
        ApiService.fetchSummary(method(:onDataReceived));
    }

    function onUpdate(dc as Dc) as Void {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        var providers = _model.getProviders();

        if (providers == null || providers.size() == 0) {
            dc.drawText(
                dc.getWidth() / 2,
                dc.getHeight() / 2,
                Graphics.FONT_SMALL,
                "Loading...",
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
            );
            return;
        }

        if (_currentPage < providers.size()) {
            drawProviderPage(dc, providers[_currentPage] as Dictionary);
        }
    }

    private function drawProviderPage(dc as Dc, provider as Dictionary) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        var centerX = w / 2;

        // Имя провайдера
        dc.drawText(
            centerX, 20, Graphics.FONT_SMALL,
            provider["n"] as String,
            Graphics.TEXT_JUSTIFY_CENTER
        );

        // Процент TPM — дуга прогресса
        var tpmPct = provider["t"] as Number;
        var color = tpmPct < 80 ? Graphics.COLOR_GREEN :
                    tpmPct < 95 ? Graphics.COLOR_YELLOW :
                    Graphics.COLOR_RED;

        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(8);
        var arcDegrees = (tpmPct * 360) / 100;
        dc.drawArc(centerX, h / 2, h / 2 - 20, Graphics.ARC_CLOCKWISE, 90, 90 - arcDegrees);

        // Текст процента
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(
            centerX, h / 2 - 10, Graphics.FONT_NUMBER_MEDIUM,
            tpmPct.format("%d") + "%",
            Graphics.TEXT_JUSTIFY_CENTER
        );

        // Стоимость
        dc.drawText(
            centerX, h / 2 + 30, Graphics.FONT_TINY,
            "$" + (provider["c"] as Float).format("%.1f"),
            Graphics.TEXT_JUSTIFY_CENTER
        );
    }

    // Callback от ApiService
    function onDataReceived(data as Dictionary?) as Void {
        if (data != null) {
            _model.updateFromApi(data);
        }
        WatchUi.requestUpdate(); // перерисовка
    }

    function nextPage() as Void {
        var count = _model.getProviderCount();
        if (count > 0) {
            _currentPage = (_currentPage + 1) % count;
            WatchUi.requestUpdate();
        }
    }

    function prevPage() as Void {
        var count = _model.getProviderCount();
        if (count > 0) {
            _currentPage = (_currentPage - 1 + count) % count;
            WatchUi.requestUpdate();
        }
    }
}
```

#### Delegate (обработка ввода)

```c
// source/TokenStatsDelegate.mc

using Toybox.WatchUi;

class TokenStatsDelegate extends WatchUi.BehaviorDelegate {

    private var _view as TokenStatsView;
    private var _model as DataModel;

    function initialize(view as TokenStatsView, model as DataModel) {
        BehaviorDelegate.initialize();
        _view = view;
        _model = model;
    }

    // Свайп вверх / нажатие кнопки Down — следующий провайдер
    function onNextPage() as Boolean {
        _view.nextPage();
        return true;
    }

    // Свайп вниз / нажатие кнопки Up — предыдущий провайдер
    function onPreviousPage() as Boolean {
        _view.prevPage();
        return true;
    }

    // Нажатие Select / Tap — обновить данные
    function onSelect() as Boolean {
        ApiService.fetchSummary(_view.method(:onDataReceived));
        return true;
    }
}
```

### Ограничения памяти

Garmin-устройства имеют строгий лимит памяти: от 64 KB до 128 KB в зависимости от модели. Это накладывает жесткие требования:

| Ограничение | Решение |
|---|---|
| Память 64-128 KB | Не хранить историю, только текущие данные |
| HTTP ответ до ~8 KB | Compact API формат (`?format=compact`) |
| Нет фоновых задач в Widget | Данные загружаются при onShow() |
| Нет persistent storage (Widget) | Application.Storage для кэша (до 32 KB) |
| Нет TLS certificate pinning | Полагаемся на Garmin Connect bridge |

### Compact API

Бэкенд предоставляет минимизированный формат ответа для Garmin:

```json
{"p":[{"n":"CL","s":1,"r":4,"t":26,"c":12.5}]}
```

Расшифровка полей:
- `p` — providers (массив)
- `n` — name (сокращенное: CL/OA/VX)
- `s` — status (0=error, 1=ok, 2=warning, 3=critical)
- `r` — RPM percent
- `t` — TPM percent
- `c` — cost today

```c
// source/ApiService.mc

using Toybox.Communications;
using Toybox.Application;

module ApiService {

    const BASE_URL = "https://api.tokenstats.app";
    const SUMMARY_PATH = "/api/v1/summary?format=compact";

    function fetchSummary(callback as Method) as Void {
        var url = BASE_URL + SUMMARY_PATH;

        var options = {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON,
            :headers => {
                "Authorization" => "Bearer " + getStoredToken()
            }
        };

        Communications.makeWebRequest(url, null, options, callback);
    }

    function getStoredToken() as String {
        var token = Application.Properties.getValue("jwt_token");
        if (token != null) {
            return token as String;
        }
        return "";
    }
}
```

```c
// source/DataModel.mc

using Toybox.Application;

class DataModel {

    private var _providers as Array<Dictionary>?;

    function initialize() {
        // Пробуем загрузить кэш
        var cached = Application.Storage.getValue("providers");
        if (cached != null) {
            _providers = cached as Array<Dictionary>;
        }
    }

    function updateFromApi(data as Dictionary) as Void {
        if (data.hasKey("p")) {
            _providers = data["p"] as Array<Dictionary>;
            // Кэшируем для следующего открытия
            Application.Storage.setValue("providers", _providers);
        }
    }

    function getProviders() as Array<Dictionary>? {
        return _providers;
    }

    function getProviderCount() as Number {
        if (_providers == null) {
            return 0;
        }
        return _providers.size();
    }
}
```

---

## 5. Wear OS

### Jetpack Compose архитектура

Wear OS приложение использует **Jetpack Compose for Wear OS** с MVVM паттерном, Hilt для DI, Retrofit для HTTP.

```
wearos/app/src/main/
├── java/com/tokenstats/
│   ├── MainActivity.kt
│   ├── di/                         # Hilt modules
│   │   ├── AppModule.kt
│   │   └── NetworkModule.kt
│   ├── data/
│   │   ├── api/
│   │   │   ├── TokenStatsApi.kt    # Retrofit interface
│   │   │   └── models/             # DTO
│   │   ├── local/
│   │   │   └── PreferencesManager.kt
│   │   └── repository/
│   │       └── TokenRepository.kt
│   ├── presentation/
│   │   ├── SummaryScreen.kt
│   │   ├── ProviderScreen.kt
│   │   ├── viewmodel/
│   │   │   └── SummaryViewModel.kt
│   │   └── theme/
│   │       └── Theme.kt
│   ├── tiles/
│   │   └── SummaryTile.kt
│   ├── complications/
│   │   └── UsageComplication.kt
│   └── worker/
│       └── RefreshWorker.kt
```

### Retrofit API

```kotlin
// data/api/TokenStatsApi.kt

import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Path

data class UsageMetricDto(
    val used: Int,
    val limit: Int,
    val pct: Double
)

data class ProviderSummaryDto(
    val id: String,
    val name: String,
    val status: String,
    val rpm: UsageMetricDto,
    val tpm: UsageMetricDto,
    val cost_today: Double,
    val cost_month: Double,
    val budget_month: Double?,
    val budget_pct: Double?
)

data class SummaryResponseDto(
    val providers: List<ProviderSummaryDto>,
    val updated_at: String
)

interface TokenStatsApi {

    @GET("api/v1/summary")
    suspend fun getSummary(
        @Header("Authorization") token: String
    ): SummaryResponseDto

    @GET("api/v1/limits/{provider}")
    suspend fun getLimits(
        @Header("Authorization") token: String,
        @Path("provider") provider: String
    ): UsageMetricDto

    @GET("api/v1/history/{provider}")
    suspend fun getHistory(
        @Header("Authorization") token: String,
        @Path("provider") provider: String
    ): List<UsageHistoryPointDto>
}
```

### Repository

```kotlin
// data/repository/TokenRepository.kt

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import javax.inject.Inject
import javax.inject.Singleton

sealed class Resource<out T> {
    data class Success<T>(val data: T) : Resource<T>()
    data class Error(val message: String, val cause: Throwable? = null) : Resource<Nothing>()
    data object Loading : Resource<Nothing>()
}

@Singleton
class TokenRepository @Inject constructor(
    private val api: TokenStatsApi,
    private val preferencesManager: PreferencesManager
) {

    fun getSummary(): Flow<Resource<SummaryResponseDto>> = flow {
        emit(Resource.Loading)

        // Сначала отдаем кэш
        val cached = preferencesManager.getCachedSummary()
        if (cached != null) {
            emit(Resource.Success(cached))
        }

        // Затем загружаем свежие данные
        try {
            val token = preferencesManager.getJwtToken()
                ?: throw IllegalStateException("Not authenticated")
            val response = api.getSummary("Bearer $token")
            preferencesManager.cacheSummary(response)
            emit(Resource.Success(response))
        } catch (e: Exception) {
            if (cached == null) {
                emit(Resource.Error(e.message ?: "Unknown error", e))
            }
            // Если кэш есть — молча глотаем ошибку, данные уже показаны
        }
    }
}
```

### ViewModel

```kotlin
// presentation/viewmodel/SummaryViewModel.kt

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SummaryViewModel @Inject constructor(
    private val repository: TokenRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow<SummaryUiState>(SummaryUiState.Loading)
    val uiState: StateFlow<SummaryUiState> = _uiState.asStateFlow()

    init {
        loadSummary()
    }

    fun loadSummary() {
        viewModelScope.launch {
            repository.getSummary().collect { resource ->
                _uiState.value = when (resource) {
                    is Resource.Loading -> SummaryUiState.Loading
                    is Resource.Success -> SummaryUiState.Success(
                        providers = resource.data.providers
                    )
                    is Resource.Error -> SummaryUiState.Error(resource.message)
                }
            }
        }
    }

    fun refresh() {
        loadSummary()
    }
}

sealed class SummaryUiState {
    data object Loading : SummaryUiState()
    data class Success(val providers: List<ProviderSummaryDto>) : SummaryUiState()
    data class Error(val message: String) : SummaryUiState()
}
```

### Compose UI

```kotlin
// presentation/SummaryScreen.kt

import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.wear.compose.foundation.lazy.ScalingLazyColumn
import androidx.wear.compose.foundation.lazy.items
import androidx.wear.compose.material.*

@Composable
fun SummaryScreen(
    viewModel: SummaryViewModel = hiltViewModel(),
    onProviderClick: (String) -> Unit
) {
    val uiState by viewModel.uiState.collectAsState()

    when (val state = uiState) {
        is SummaryUiState.Loading -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        }

        is SummaryUiState.Error -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = state.message,
                        textAlign = TextAlign.Center,
                        color = Color.Red
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    CompactChip(
                        onClick = { viewModel.refresh() },
                        label = { Text("Retry") }
                    )
                }
            }
        }

        is SummaryUiState.Success -> {
            ScalingLazyColumn(
                modifier = Modifier.fillMaxSize(),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                item {
                    ListHeader { Text("TokenStats") }
                }

                items(state.providers) { provider ->
                    ProviderChip(
                        provider = provider,
                        onClick = { onProviderClick(provider.id) }
                    )
                }
            }
        }
    }
}

@Composable
private fun ProviderChip(
    provider: ProviderSummaryDto,
    onClick: () -> Unit
) {
    val statusColor = when (provider.status) {
        "ok" -> Color.Green
        "warning" -> Color.Yellow
        "critical" -> Color.Red
        else -> Color.Gray
    }

    Chip(
        modifier = Modifier.fillMaxWidth(0.9f),
        onClick = onClick,
        label = { Text(provider.name) },
        secondaryLabel = {
            Text("TPM: ${provider.tpm.pct.toInt()}% | \$${provider.cost_today}")
        },
        icon = {
            Box(
                modifier = Modifier.size(12.dp),
                contentAlignment = Alignment.Center
            ) {
                androidx.compose.foundation.Canvas(
                    modifier = Modifier.size(12.dp)
                ) {
                    drawCircle(color = statusColor)
                }
            }
        }
    )
}
```

### Tiles API

Tiles — быстрый доступ к данным без открытия приложения, аналог complications на Apple Watch.

```kotlin
// tiles/SummaryTile.kt

import androidx.wear.protolayout.*
import androidx.wear.protolayout.LayoutElementBuilders.*
import androidx.wear.protolayout.ResourceBuilders.*
import androidx.wear.tiles.*
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.guava.future

class SummaryTileService : TileService() {

    override fun onTileRequest(requestParams: RequestBuilders.TileRequest):
        ListenableFuture<TileBuilders.Tile> = serviceScope.future {

        val repository = /* inject */ TokenRepository(/* ... */)
        val summary = repository.getCachedSummary()

        TileBuilders.Tile.Builder()
            .setResourcesVersion("1")
            .setFreshnessIntervalMillis(15 * 60 * 1000L) // 15 минут
            .setTileTimeline(
                TimelineBuilders.Timeline.Builder()
                    .addTimelineEntry(
                        TimelineBuilders.TimelineEntry.Builder()
                            .setLayout(
                                LayoutElementBuilders.Layout.Builder()
                                    .setRoot(buildTileLayout(summary))
                                    .build()
                            )
                            .build()
                    )
                    .build()
            )
            .build()
    }

    private fun buildTileLayout(summary: SummaryResponseDto?): LayoutElement {
        if (summary == null) {
            return Text.Builder()
                .setText("No data")
                .build()
        }

        val columns = summary.providers.map { provider ->
            Column.Builder()
                .addContent(
                    Text.Builder()
                        .setText(provider.name)
                        .build()
                )
                .addContent(
                    Text.Builder()
                        .setText("${provider.tpm.pct.toInt()}%")
                        .build()
                )
                .build()
        }

        return Row.Builder().apply {
            columns.forEach { addContent(it) }
        }.build()
    }
}
```

### WorkManager

Фоновое обновление данных через WorkManager. Гарантирует выполнение даже при ограничениях Doze mode.

```kotlin
// worker/RefreshWorker.kt

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.*
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

@HiltWorker
class RefreshWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val repository: TokenRepository
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        return try {
            repository.fetchAndCacheSummary()
            Result.success()
        } catch (e: Exception) {
            if (runAttemptCount < 3) {
                Result.retry()
            } else {
                Result.failure()
            }
        }
    }

    companion object {
        private const val WORK_NAME = "token_stats_refresh"

        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = PeriodicWorkRequestBuilder<RefreshWorker>(
                repeatInterval = 15,
                repeatIntervalTimeUnit = TimeUnit.MINUTES
            )
                .setConstraints(constraints)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    WorkRequest.MIN_BACKOFF_MILLIS,
                    TimeUnit.MILLISECONDS
                )
                .build()

            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(
                    WORK_NAME,
                    ExistingPeriodicWorkPolicy.KEEP,
                    request
                )
        }
    }
}
```

---

## 6. Общие паттерны

### 6.1 Error Handling

Все платформы используют типизированные ошибки с единой классификацией.

**Swift (iOS / watchOS):**

```swift
// Shared/Models/AppError.swift

import Foundation

enum AppError: LocalizedError {
    case network(Error)
    case unauthorized
    case rateLimited
    case serverError(Int)
    case httpError(Int)
    case invalidResponse
    case decodingFailed(Error)
    case noData

    var errorDescription: String? {
        switch self {
        case .network(let error):
            return "Нет соединения: \(error.localizedDescription)"
        case .unauthorized:
            return "Сессия истекла. Войдите заново."
        case .rateLimited:
            return "Слишком много запросов. Подождите."
        case .serverError(let code):
            return "Ошибка сервера (\(code))"
        case .httpError(let code):
            return "HTTP ошибка (\(code))"
        case .invalidResponse:
            return "Неожиданный ответ сервера"
        case .decodingFailed:
            return "Ошибка формата данных"
        case .noData:
            return "Нет данных"
        }
    }

    /// Можно ли повторить запрос
    var isRetryable: Bool {
        switch self {
        case .network, .serverError, .rateLimited:
            return true
        default:
            return false
        }
    }
}
```

**Kotlin (Wear OS):**

```kotlin
// data/error/AppError.kt

sealed class AppError(
    override val message: String,
    override val cause: Throwable? = null
) : Exception(message, cause) {

    class Network(cause: Throwable) :
        AppError("Нет соединения: ${cause.message}", cause)

    class Unauthorized :
        AppError("Сессия истекла. Войдите заново.")

    class RateLimited :
        AppError("Слишком много запросов. Подождите.")

    class Server(code: Int) :
        AppError("Ошибка сервера ($code)")

    class Unknown(cause: Throwable) :
        AppError("Неизвестная ошибка: ${cause.message}", cause)

    val isRetryable: Boolean
        get() = this is Network || this is Server || this is RateLimited
}
```

**Monkey C (Garmin):**

В Monkey C нет исключений. Обработка ошибок через callback-параметры и коды ответов.

```c
// source/ErrorHandler.mc

module ErrorHandler {

    // HTTP response codes от Communications.makeWebRequest
    // responseCode < 0 — ошибка сети Connect IQ
    // responseCode = -104 — BLE_CONNECTION_UNAVAILABLE
    // responseCode = -300 — NETWORK_RESPONSE_OUT_OF_MEMORY

    function handleResponseCode(responseCode as Number) as String {
        if (responseCode == 200) {
            return "";
        } else if (responseCode == 401) {
            return "Auth error";
        } else if (responseCode == 429) {
            return "Too many req";
        } else if (responseCode == -104) {
            return "No BLE";
        } else if (responseCode == -300) {
            return "Out of mem";
        } else if (responseCode < 0) {
            return "No connection";
        } else {
            return "Error " + responseCode;
        }
    }

    function isRetryable(responseCode as Number) as Boolean {
        // Сетевые ошибки и 5xx — можно повторить
        return (responseCode < 0 && responseCode != -300) ||
               (responseCode >= 500 && responseCode < 600);
    }
}
```

### 6.2 Offline Mode

Все клиенты реализуют стратегию **cache-first**: показывают кэшированные данные немедленно, затем обновляют с сервера.

```
┌─────────────────────────────────────────────────┐
│               Запрос данных                     │
├─────────────────────────────────────────────────┤
│                                                 │
│  1. Показать кэш (если есть)                    │
│     └── Пользователь сразу видит данные         │
│                                                 │
│  2. Запрос к серверу                            │
│     ├── Успех → обновить UI + обновить кэш      │
│     └── Ошибка → оставить кэш + показать badge │
│                 "Данные от 10 мин назад"         │
│                                                 │
│  3. Нет кэша + нет сети                         │
│     └── Экран ошибки с кнопкой Retry            │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Хранение кэша по платформам:**

| Платформа | Хранилище | Ограничения |
|---|---|---|
| iOS / watchOS | UserDefaults (сводка), FileManager (история) | Без ограничений (разумных) |
| Garmin | Application.Storage | 32 KB максимум |
| Wear OS | EncryptedSharedPreferences, Room DB | Без ограничений (разумных) |

### 6.3 Retry Strategy

Все платформы используют **exponential backoff** с jitter для повторных запросов.

**Swift (общая реализация):**

```swift
// Shared/Services/RetryPolicy.swift

import Foundation

struct RetryPolicy {
    let maxAttempts: Int
    let baseDelay: TimeInterval     // секунды
    let maxDelay: TimeInterval
    let multiplier: Double

    static let `default` = RetryPolicy(
        maxAttempts: 3,
        baseDelay: 1.0,
        maxDelay: 30.0,
        multiplier: 2.0
    )

    /// Задержка для n-й попытки (с jitter)
    func delay(for attempt: Int) -> TimeInterval {
        let exponential = baseDelay * pow(multiplier, Double(attempt))
        let capped = min(exponential, maxDelay)
        let jitter = Double.random(in: 0...(capped * 0.3))
        return capped + jitter
    }
}

/// Выполнение запроса с retry
func withRetry<T>(
    policy: RetryPolicy = .default,
    operation: @escaping () async throws -> T
) async throws -> T {
    var lastError: Error?

    for attempt in 0..<policy.maxAttempts {
        do {
            return try await operation()
        } catch {
            lastError = error

            // Не повторяем для non-retryable ошибок
            if let appError = error as? AppError, !appError.isRetryable {
                throw error
            }

            // Ждем перед следующей попыткой
            if attempt < policy.maxAttempts - 1 {
                let delay = policy.delay(for: attempt)
                try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            }
        }
    }

    throw lastError!
}
```

**Kotlin (Wear OS):**

```kotlin
// data/util/RetryPolicy.kt

import kotlinx.coroutines.delay
import kotlin.math.min
import kotlin.math.pow
import kotlin.random.Random

data class RetryPolicy(
    val maxAttempts: Int = 3,
    val baseDelayMs: Long = 1000,
    val maxDelayMs: Long = 30_000,
    val multiplier: Double = 2.0
) {
    fun delayForAttempt(attempt: Int): Long {
        val exponential = baseDelayMs * multiplier.pow(attempt.toDouble())
        val capped = min(exponential.toLong(), maxDelayMs)
        val jitter = Random.nextLong(0, (capped * 0.3).toLong())
        return capped + jitter
    }
}

suspend fun <T> withRetry(
    policy: RetryPolicy = RetryPolicy(),
    block: suspend () -> T
): T {
    var lastException: Exception? = null

    repeat(policy.maxAttempts) { attempt ->
        try {
            return block()
        } catch (e: Exception) {
            lastException = e

            if (e is AppError && !e.isRetryable) throw e

            if (attempt < policy.maxAttempts - 1) {
                delay(policy.delayForAttempt(attempt))
            }
        }
    }

    throw lastException!!
}
```

**Monkey C (Garmin) — упрощенный retry:**

На Garmin нет фоновых задач и корутин. Retry реализуется через таймер.

```c
// source/RetryHelper.mc

using Toybox.Timer;

class RetryHelper {

    private var _timer as Timer.Timer?;
    private var _attempt as Number = 0;
    private var _maxAttempts as Number = 3;
    private var _callback as Method?;

    function initialize(callback as Method) {
        _callback = callback;
    }

    function retry() as Boolean {
        if (_attempt >= _maxAttempts) {
            _attempt = 0;
            return false; // превышен лимит
        }

        // Exponential backoff: 2s, 4s, 8s
        var delayMs = 2000 * (1 << _attempt);

        _timer = new Timer.Timer();
        _timer.start(_callback, delayMs, false);

        _attempt++;
        return true;
    }

    function reset() as Void {
        _attempt = 0;
        if (_timer != null) {
            _timer.stop();
            _timer = null;
        }
    }
}
```

### 6.4 Сводная таблица паттернов по платформам

| Паттерн | Apple (Swift) | Wear OS (Kotlin) | Garmin (Monkey C) |
|---|---|---|---|
| Архитектура | MVVM + SwiftUI | MVVM + Compose | App/View/Delegate |
| DI | Manual / протоколы | Hilt | Нет (прямые зависимости) |
| Сеть | URLSession async/await | Retrofit + Coroutines | Communications.makeWebRequest |
| Кэш | UserDefaults / FileManager | SharedPreferences / Room | Application.Storage (32KB) |
| Фоновое обновление | Background App Refresh | WorkManager | Нет (только при onShow) |
| Хранение токена | Keychain | EncryptedSharedPreferences | Application.Properties |
| Push | APNs | FCM | Нет |
| Complications | WidgetKit Timeline | Tiles API + Complications | Glance View |
| Retry | async/await + Task.sleep | Coroutines + delay | Timer callback |
| Формат API | Полный JSON | Полный JSON | Compact JSON (~200 bytes) |
