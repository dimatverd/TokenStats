# TokenStats — Приложение для мониторинга лимитов LLM-токенов на умных часах

## Context

Разработчики и команды, активно использующие LLM API (Claude, OpenAI, Vertex AI), нуждаются в быстром способе отслеживать текущее потребление токенов, оставшиеся лимиты и расходы — без необходимости открывать дашборды в браузере. Приложение для умных часов позволяет в любой момент глянуть на запястье и увидеть ключевые метрики.

## Аутентификация и безопасность ключей

Все провайдеры подключаются через **read-only ключи** — пользователь никогда не отдаёт боевые ключи:

| Провайдер | Тип ключа | Что может | Чего НЕ может |
|---|---|---|---|
| Anthropic | Admin API key (`sk-ant-admin-...`) с read-only scopes (`organization_read`, `usage_read`) | Читать usage, costs, rate limits | Делать inference, менять настройки |
| OpenAI | Admin API key с read permissions | Читать usage, costs, rate limits | Делать completions, менять billing |
| Google Vertex AI | Service Account JSON с viewer-ролями (`monitoring.viewer`, `billing.viewer`, `serviceusage.serviceUsageViewer`) | Читать метрики, расходы, квоты | Делать inference, менять проект |

При добавлении ключа бэкенд **валидирует**, что ключ действительно read-only (тестовый запрос к usage endpoint + проверка, что inference-запрос отклоняется).

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│                   LLM Providers                     │
│  Anthropic API       OpenAI API       Vertex AI     │
│  (Admin read-only)   (Admin read-only) (SA viewer)  │
└───────┬───────────────────┬───────────────┬─────────┘
        │                   │               │
        ▼                   ▼               ▼
┌─────────────────────────────────────────────────────┐
│              Backend (Python FastAPI)                │
│  - Агрегация данных от всех провайдеров             │
│  - Кэширование (in-memory TTL)                      │
│  - Единый REST API для клиентов                     │
│  - Push-уведомления (APNs, FCM)                     │
│  - Аутентификация пользователей (JWT)               │
│  - Хранение ключей (Fernet-шифрование)              │
└───────┬───────────────┬───────────────┬─────────────┘
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌─────────────┐ ┌────────────────┐
│ Apple Watch  │ │   Garmin    │ │   Wear OS      │
│ SwiftUI      │ │ Connect IQ  │ │ Kotlin/Compose │
│ watchOS 10+  │ │ Monkey C    │ │ Wear OS 4+     │
└──────────────┘ └─────────────┘ └────────────────┘
```

## Фаза 1 — Backend (Python FastAPI)

### 1.1 Структура проекта

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, CORS, lifespan
│   ├── config.py               # Settings (pydantic-settings)
│   ├── auth/
│   │   ├── router.py           # /auth/register, /auth/login, /auth/token
│   │   ├── models.py           # User, APIKeyStore
│   │   └── dependencies.py     # JWT bearer dependency
│   ├── providers/
│   │   ├── base.py             # AbstractProvider interface
│   │   ├── anthropic.py        # Anthropic Admin API
│   │   ├── openai.py           # OpenAI Admin API
│   │   └── google.py           # Google Vertex AI (Service Account)
│   ├── api/
│   │   ├── router.py           # /api/v1/...
│   │   ├── usage.py            # GET /usage/{provider}
│   │   ├── limits.py           # GET /limits/{provider}
│   │   ├── costs.py            # GET /costs/{provider}
│   │   └── summary.py          # GET /summary
│   ├── notifications/
│   │   └── service.py          # Push при приближении к лимитам
│   ├── cache.py                # In-memory cache (TTL-based)
│   └── db.py                   # SQLite/PostgreSQL через SQLAlchemy
├── tests/
│   ├── test_providers.py
│   └── test_api.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

### 1.2 Провайдеры — источники данных

**Anthropic (Claude):**
- Ключ: Admin API key (`sk-ant-admin-...`) с read-only scopes
- Rate limits: **workaround** — read-only admin key не имеет доступа к Messages API заголовкам (`anthropic-ratelimit-*`). Решение:
  - `used`: расчёт RPM/TPM из usage report (`bucket_width=1m`) за последнюю минуту (задержка ~5 мин)
  - `limit`: пользователь указывает свой tier при настройке → подставляются лимиты из документации Anthropic
  - При онбординге: селектор "Выберите ваш тарифный план" (Tier 1 / 2 / 3 / 4 / Build / Scale)
- Usage: `GET /v1/organizations/usage_report/messages` (Admin API)
- Costs: `GET /v1/organizations/cost_report` (Admin API)
- Обновление: раз в 1-5 минут (usage данные с задержкой ~5 мин)

**OpenAI:**
- Ключ: Admin API key с read permissions
- Rate limits: `GET /v1/organization/projects/{id}/rate_limits` (Admin API)
- Usage: `GET /v1/organization/usage/completions` (Admin API, bucket_width=1m/1h/1d)
- Costs: `GET /v1/organization/costs` (Admin API)
- Обновление: раз в 1-5 минут

**Google Vertex AI:**
- Ключ: Service Account JSON с viewer-ролями
- Rate limits: Service Usage API (`serviceusage.googleapis.com`) — квоты
- Usage: Cloud Monitoring API — метрики потребления
- Costs: Cloud Billing API — расходы (**задержка до 24ч**, не "раз в час"; для near-realtime — estimated costs на основе usage × price)
- Обновление: раз в 5 минут (monitoring), раз в 24 часа (billing)
- **Примечание:** нет нативных токен-метрик в Cloud Monitoring для GenAI — показываем request count или estimated tokens. Сложная интеграция → рекомендуется для пост-MVP (V1.2+)

### 1.3 API бэкенда

```
POST /auth/register              — регистрация
POST /auth/login                 — получение JWT
POST /auth/providers             — сохранение read-only ключей (с валидацией)

GET  /api/v1/summary             — сводка по всем провайдерам
GET  /api/v1/summary?format=compact — минимизированный формат для Garmin
GET  /api/v1/limits/{provider}   — текущие rate limits (RPM, TPM, remaining)
GET  /api/v1/usage/{provider}    — потребление за период
GET  /api/v1/costs/{provider}    — расходы ($) за период
GET  /api/v1/history/{provider}  — история потребления (для графиков)

POST /api/v1/devices/register    — регистрация устройства для push-уведомлений
```

**Формат ответа `/summary`:**
```json
{
  "providers": [
    {
      "id": "anthropic",
      "name": "Claude",
      "status": "ok",
      "rpm": { "used": 45, "limit": 1000, "pct": 4.5 },
      "tpm": { "used": 120000, "limit": 450000, "pct": 26.7 },
      "cost_today": 12.50,
      "cost_month": 340.00,
      "budget_month": 500.00,
      "budget_pct": 68.0
    }
  ],
  "updated_at": "2026-02-28T12:00:00Z"
}
```

**Compact формат для Garmin (`?format=compact`):**
```json
{"p":[{"n":"CL","s":1,"r":4,"t":26,"c":12.5}]}
```

### 1.4 Кэширование и polling

- Rate limits кэшируются на 60 секунд
- Usage/costs кэшируются на 5 минут
- Background tasks (asyncio) опрашивают провайдеров периодически
- При приближении к лимитам (>80%, >95%) — push-уведомление

### 1.5 Валидация ключей при добавлении

При `POST /auth/providers` бэкенд:
1. Проверяет формат ключа
2. Делает тестовый read-запрос (usage endpoint) — должен вернуть 200
3. Проверяет, что ключ read-only (по возможности)
4. Шифрует ключ (Fernet) и сохраняет в БД

---

## Фаза 2 — Apple Watch (SwiftUI, watchOS 10+)

### 2.1 Структура проекта

```
TokenStats/
├── TokenStats.xcodeproj
├── Shared/
│   ├── Models/
│   │   ├── Provider.swift
│   │   └── TokenUsage.swift
│   ├── Services/
│   │   ├── APIClient.swift
│   │   └── KeychainService.swift
│   └── Extensions/
├── TokenStatsApp/               # iOS companion app
│   ├── TokenStatsApp.swift
│   ├── Views/
│   │   ├── DashboardView.swift
│   │   ├── ProviderDetailView.swift
│   │   ├── SettingsView.swift   # Ввод read-only ключей + инструкция
│   │   └── HistoryChartView.swift
│   └── ViewModels/
├── TokenStatsWatch/             # watchOS app
│   ├── TokenStatsWatchApp.swift
│   ├── Views/
│   │   ├── SummaryView.swift
│   │   ├── ProviderView.swift
│   │   └── CompactView.swift
│   ├── Complications/
│   │   └── ComplicationViews.swift
│   └── ViewModels/
│       └── WatchViewModel.swift
└── TokenStatsWidgets/
    ├── SummaryWidget.swift
    └── ProviderWidget.swift
```

### 2.2 Ключевые экраны

1. **Summary** — список провайдеров с цветовыми индикаторами (зелёный/жёлтый/красный)
2. **Provider Detail** — круговые прогресс-бары: RPM%, TPM%, бюджет%, стоимость сегодня
3. **Complications** — на циферблате: оставшийся % лимита или $ за сегодня

### 2.3 Настройка ключей (iOS companion)

В SettingsView — пошаговая инструкция для каждого провайдера:
- Anthropic: "Console → Admin API Keys → Create → выберите только Read scopes"
- OpenAI: "Settings → API Keys → Create → выберите Read permissions"
- Vertex AI: "GCP Console → IAM → Service Accounts → Create → добавьте Viewer роли → скачайте JSON"

### 2.4 Обновление данных

- WatchConnectivity для передачи настроек с iPhone
- URLSession для прямых запросов к бэкенду с часов
- Background App Refresh каждые 15 минут
- Complications обновляются через WidgetKit timeline

---

## Фаза 3 — Garmin (Connect IQ, Monkey C)

### 3.1 Структура проекта

```
garmin/
├── manifest.xml
├── source/
│   ├── TokenStatsApp.mc
│   ├── TokenStatsView.mc
│   ├── TokenStatsDelegate.mc
│   ├── ApiService.mc
│   └── DataModel.mc
├── resources/
│   ├── layouts/layout.xml
│   ├── drawables/
│   └── strings/strings.xml
└── barrel.jungle
```

### 3.2 Ограничения

- Память: 64-128 KB
- HTTP: `Communications.makeWebRequest()`, макс ~8 KB ответа
- Тип: Widget (glance + detail)
- Использует compact формат API (`?format=compact`)

---

## Фаза 4 — Wear OS (Kotlin, Jetpack Compose)

### 4.1 Структура проекта

```
wearos/
├── app/src/main/
│   ├── java/com/tokenstats/
│   │   ├── MainActivity.kt
│   │   ├── presentation/
│   │   │   ├── SummaryScreen.kt
│   │   │   ├── ProviderScreen.kt
│   │   │   └── theme/Theme.kt
│   │   ├── data/
│   │   │   ├── ApiClient.kt
│   │   │   └── TokenRepository.kt
│   │   ├── tiles/
│   │   │   └── SummaryTile.kt
│   │   └── complications/
│   │       └── UsageComplication.kt
│   └── AndroidManifest.xml
├── build.gradle.kts
└── settings.gradle.kts
```

### 4.2 Возможности

- Tiles API для быстрого доступа
- Complications для циферблата
- WorkManager для фонового обновления
- Push через FCM

---

## Порядок реализации

### MVP (Фаза 1-2): ~3-4 недели
1. Backend — FastAPI + Anthropic + OpenAI + SQLite + JWT auth + key validation
2. Apple Watch — SwiftUI watchOS + iOS companion для настроек ключей
3. Vertex AI провайдер

### V1.1: +2 недели
4. Complications/Widgets для Apple Watch
5. Push-уведомления при приближении к лимитам
6. Графики истории (Swift Charts)

### V1.2: +2-3 недели
7. Garmin Connect IQ widget
8. Wear OS Kotlin app + Tile

### V2.0: будущее
9. Дополнительные провайдеры (Mistral, xAI)
10. Командные фичи (общий дашборд для организации)
11. Прогнозирование расходов

---

## Стек технологий

| Компонент | Технология |
|---|---|
| Backend | Python 3.12+, FastAPI 0.115+, Pydantic, SQLAlchemy |
| DB | SQLite (dev) → PostgreSQL (prod) |
| Cache | In-memory (cachetools) → Redis (prod) |
| iOS app | Swift 5.9+, SwiftUI, Swift Charts, iOS 17+ |
| watchOS app | SwiftUI, WidgetKit, watchOS 10+ |
| Garmin | Monkey C, Connect IQ SDK 7+ |
| Wear OS | Kotlin, Jetpack Compose for Wear OS, Wear OS 4+ |
| Deploy | Docker, Fly.io / Railway |

## Безопасность

- **Только read-only ключи** — пользователь не отдаёт боевые ключи
- API-ключи хранятся в БД зашифрованными (Fernet/AES-256)
- Валидация read-only при добавлении ключа
- JWT аутентификация (access + refresh tokens)
- На клиентах JWT в Keychain (iOS) / EncryptedSharedPreferences (Android)
- HTTPS обязателен
- Rate limiting на бэкенде (slowapi)
- Пошаговые инструкции для создания read-only ключей в UI

## Верификация

1. Backend: `pytest` — unit-тесты провайдеров (mock API), интеграционные тесты
2. Apple Watch: Xcode Previews + watchOS симулятор
3. Garmin: Connect IQ Simulator
4. Wear OS: Android Studio Wear OS emulator
5. E2E: read-only ключи → проверка корректности данных на каждой платформе
