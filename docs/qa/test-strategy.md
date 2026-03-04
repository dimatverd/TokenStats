# TokenStats — Тест-стратегия

## 1. Обзор тест-стратегии

### 1.1 Пирамида тестирования

```
            ┌─────────┐
            │   E2E   │   ~10% — сквозные сценарии
           ─┴─────────┴─
          ┌───────────────┐
          │  Integration  │   ~30% — API, БД, провайдеры (mock)
         ─┴───────────────┴─
        ┌───────────────────┐
        │      Unit         │   ~60% — провайдеры, кэш, JWT, шифрование
        └───────────────────┘
```

### 1.2 Подход

- **Shift-left**: тесты пишутся параллельно с разработкой
- **Mock-first для провайдеров**: все обращения к Anthropic, OpenAI, Vertex AI мокаются через `respx`; реальные вызовы только в smoke-тестах
- **Контрактное тестирование**: формат ответов API фиксируется Pydantic-схемами
- **Автоматизация**: CI запускает `pytest` (backend), Xcode Test Plans (watchOS/iOS), Connect IQ Simulator (Garmin), Gradle test (Wear OS)

### 1.3 Инструменты

| Область | Инструмент | Назначение |
|---|---|---|
| Backend unit/integration | pytest + pytest-asyncio | Тесты FastAPI, async-кода |
| HTTP mocking | respx / httpx mock | Мок ответов от LLM-провайдеров |
| Покрытие кода | coverage.py + pytest-cov | Минимум 80% покрытия backend |
| API-тесты | httpx.AsyncClient (TestClient) | Тестирование эндпоинтов FastAPI |
| БД-тесты | SQLAlchemy + SQLite in-memory | Изолированные тесты хранилища |
| Нагрузочные | Locust | Симуляция нагрузки на backend API |
| Безопасность | bandit, safety | Статический анализ, проверка зависимостей |
| Apple Watch | XCTest + Xcode Previews | Unit- и UI-тесты watchOS/iOS |
| Garmin | Connect IQ Simulator + Unit Tests | Тесты Monkey C кода |
| Wear OS | JUnit 5 + Espresso + Robolectric | Unit- и UI-тесты Kotlin/Compose |
| Линтинг | ruff, mypy | Статический анализ Python |

---

## 2. Backend-тесты

### 2.1 Unit-тесты провайдеров

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| UP-01 | Anthropic: парсинг usage report | Замокать GET usage с валидным JSON → вызвать `get_usage()` | Корректный `UsageData` с `tokens_used`, `period` |
| UP-02 | Anthropic: парсинг rate limit заголовков | Замокать ответ с `anthropic-ratelimit-*` заголовками → `get_limits()` | `LimitsData` с `rpm.limit=1000`, `rpm.remaining=955` |
| UP-03 | Anthropic: парсинг cost report | Замокать GET cost_report → `get_costs()` | Корректные `cost_today`, `cost_month` |
| UP-04 | Anthropic: невалидный ключ (401) | Замокать 401 → `get_usage()` | `ProviderAuthError` |
| UP-05 | Anthropic: rate limit exceeded (429) | Замокать 429 с `retry-after: 30` → `get_usage()` | `ProviderRateLimitError` с `retry_after=30` |
| UP-06 | Anthropic: таймаут | Замокать `httpx.ReadTimeout` → `get_usage()` | `ProviderTimeoutError` |
| UP-07 | OpenAI: парсинг usage completions | Замокать GET usage/completions → `get_usage()` | Корректный `UsageData` |
| UP-08 | OpenAI: парсинг rate limits | Замокать GET rate_limits → `get_limits()` | Корректные `rpm`, `tpm` |
| UP-09 | OpenAI: парсинг costs | Замокать GET costs → `get_costs()` | Корректные расходы |
| UP-10 | OpenAI: невалидный ключ (401) | Замокать 401 → `get_usage()` | `ProviderAuthError` |
| UP-11 | Vertex AI: парсинг Monitoring API | Замокать Cloud Monitoring → `get_usage()` | Корректный `UsageData` |
| UP-12 | Vertex AI: парсинг квот | Замокать Service Usage → `get_limits()` | Корректные квоты |
| UP-13 | Vertex AI: парсинг Billing | Замокать Billing API → `get_costs()` | Корректные расходы |
| UP-14 | Vertex AI: невалидный SA | Замокать 403 → `get_usage()` | `ProviderAuthError` |
| UP-15 | Пустой ответ (200, {}) | Замокать 200 с `{}` → `get_usage()` | Нулевые значения, не исключение |
| UP-16 | Неожиданная структура JSON | Замокать 200 с другой структурой → `get_usage()` | `ProviderParseError` |

### 2.2 Unit-тесты кэша

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| UC-01 | Хранение и возврат | Записать → прочитать | Данные совпадают |
| UC-02 | TTL истёк | Записать с TTL=1с → ждать 2с → прочитать | `None` |
| UC-03 | Разные TTL | rate_limits (60с) + costs (300с) → промотать 120с | rate_limits=None, costs=валидные |
| UC-04 | Перезапись | Записать A → записать B → прочитать | Данные B |
| UC-05 | Удаление | Записать → invalidate → прочитать | `None` |
| UC-06 | Конкурентный доступ | 10 asyncio-задач параллельно пишут и читают | Нет race condition |

### 2.3 Unit-тесты JWT

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| UJ-01 | Генерация access token | `create_access_token(user_id=1)` → декодировать | `sub=1`, `exp` через 30 мин, `type=access` |
| UJ-02 | Генерация refresh token | `create_refresh_token(user_id=1)` → декодировать | `type=refresh`, `exp` через 30 дней |
| UJ-03 | Валидация корректного токена | Создать → `verify_token()` | Возвращается `user_id` |
| UJ-04 | Истёкший токен | Создать с `exp` в прошлом → `verify_token()` | `TokenExpiredError` |
| UJ-05 | Подделанный токен | Создать → изменить payload → `verify_token()` | `InvalidTokenError` |
| UJ-06 | Refresh вместо access | Refresh token в эндпоинт требующий access | 401 Unauthorized |
| UJ-07 | Мусорный токен | `Authorization: Bearer abc123` | 401 Unauthorized |

### 2.4 Unit-тесты шифрования (Fernet)

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| UE-01 | Шифрование и расшифровка | Зашифровать `sk-ant-admin-xxx` → расшифровать | Совпадает |
| UE-02 | Разные ключи → разные шифротексты | Зашифровать key_A и key_B | Шифротексты отличаются |
| UE-03 | Неверный master key | Зашифровать с key_A → расшифровать с key_B | `InvalidToken` |
| UE-04 | Повреждённый шифротекст | Зашифровать → модифицировать 1 байт → расшифровать | `InvalidToken` |
| UE-05 | Пустая строка | Зашифровать `""` → расшифровать | Корректно: `""` |

### 2.5 Integration-тесты API

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| IA-01 | Регистрация | POST /auth/register | 201, `{user_id, email}` |
| IA-02 | Дубликат email | Зарегистрировать → повторить | 409 Conflict |
| IA-03 | Логин | Зарегистрироваться → POST /auth/login | 200, `{access_token, refresh_token}` |
| IA-04 | Неверный пароль | POST /auth/login с неверным паролем | 401 |
| IA-05 | Добавление read-only ключа | POST /auth/providers (мок провайдера) | 201, ключ зашифрован в БД |
| IA-06 | Невалидный ключ | POST /auth/providers (мок 401) | 400 |
| IA-07 | Summary без авторизации | GET /api/v1/summary без JWT | 401 |
| IA-08 | Summary с авторизацией | JWT + добавить провайдер → GET /summary | 200, массив providers |
| IA-09 | Summary compact | GET /api/v1/summary?format=compact | 200, `{"p":[...]}` |
| IA-10 | Limits | GET /api/v1/limits/anthropic | 200, rpm/tpm данные |
| IA-11 | Usage | GET /api/v1/usage/openai | 200, usage за период |
| IA-12 | Costs | GET /api/v1/costs/anthropic | 200, cost_today/month |
| IA-13 | History | GET /api/v1/history/anthropic | 200, массив точек |
| IA-14 | Несуществующий провайдер | GET /api/v1/limits/nonexistent | 404 |
| IA-15 | Регистрация устройства | POST /api/v1/devices/register | 201 |
| IA-16 | Кэш: повторный запрос в пределах TTL | 2 запроса → проверка что провайдер вызван 1 раз | Второй из кэша |

### 2.6 Integration-тесты БД

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| ID-01 | Создание пользователя | `UserRepository.create()` | Сохранён, id автоинкремент |
| ID-02 | Зашифрованный ключ в БД | Сохранить → прочитать raw | Шифротекст, не plaintext |
| ID-03 | Ключи пользователя | Сохранить 2 ключа → `get_by_user()` | 2 записи |
| ID-04 | Удаление ключа | Сохранить → удалить → прочитать | Пустой список |
| ID-05 | Уникальность user+provider | 2 ключа с одним user+provider | Upsert или ошибка |

### 2.7 E2E-тесты

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| E2E-01 | Полный flow | Регистрация → добавление ключа → GET /summary | Реальные данные |
| E2E-02 | Мультипровайдер | Добавить 3 провайдера → GET /summary | 3 элемента, все ok |
| E2E-03 | Инвалидация кэша | Summary → ждать TTL → Summary | `updated_at` изменился |
| E2E-04 | Push при >80% | Аккаунт с >80% RPM → зарегистрировать устройство | Push доставлен |
| E2E-05 | Refresh token flow | Логин → ждать exp access → refresh → новый access | Работает |

---

## 3. Безопасность

### 3.1 Валидация read-only ключей

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| SEC-01 | Anthropic read-only принимается | POST /auth/providers с read-only admin key | 201 |
| SEC-02 | Anthropic full-access отклоняется | Ключ позволяет inference | 400 «Ключ не read-only» |
| SEC-03 | OpenAI read-only принимается | Admin key с read permissions | 201 |
| SEC-04 | OpenAI write отклоняется | Ключ может делать completions | 400 |
| SEC-05 | Vertex AI viewer принимается | SA с viewer-ролями | 201 |
| SEC-06 | Vertex AI editor отклоняется | SA с ролью editor | 400 |

### 3.2 Fernet

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| SEC-07 | Ключи не в plaintext | Прочитать запись из БД | Нет `sk-ant-admin-`, есть Base64 |
| SEC-08 | Master key в env | Проверить код | FERNET_KEY из env, не в коде |
| SEC-09 | Ротация master key | Перешифровать ключи с новым master | Все расшифровываются |

### 3.3 JWT-безопасность

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| SEC-10 | Токен чужого пользователя | JWT user_1 → данные user_2 | 403 |
| SEC-11 | Алгоритм none attack | JWT с `alg: none` | 401 |
| SEC-12 | JWT без exp | JWT без поля exp | 401 |

### 3.4 Rate limiting

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| SEC-13 | Rate limit /auth/login | 20 запросов за 1 минуту | 429 после лимита |
| SEC-14 | Rate limit API | 100 запросов за 1 минуту | 429 после лимита |
| SEC-15 | Rate limit по IP | Запросы с одного IP сверх лимита | 429 с Retry-After |

### 3.5 SQL Injection / XSS

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| SEC-16 | SQLi в email | `"'; DROP TABLE users; --"` | 422 или безопасная обработка |
| SEC-17 | SQLi в provider param | `' OR 1=1 --` | 404, таблицы не затронуты |
| SEC-18 | Параметризованные запросы | Ревью кода | Нет raw SQL с конкатенацией |
| SEC-19 | XSS в email | `<script>alert(1)</script>@test.com` | 422 или экранировано |
| SEC-20 | XSS в параметрах | HTML в query params | Content-Type: application/json, экранировано |
| SEC-21 | HTTP-заголовки безопасности | Проверить ответы | X-Content-Type-Options, X-Frame-Options, HSTS |

---

## 4. Apple Watch (watchOS 10+ / iOS 17+)

### 4.1 UI-тесты

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| AW-01 | SummaryView: отображение | Замокать 3 провайдера → открыть | Список с именами и индикаторами |
| AW-02 | Цветовая индикация | 30% / 85% / 97% → проверить цвета | Зелёный / жёлтый / красный |
| AW-03 | ProviderView: прогресс-бары | Открыть детали | RPM%, TPM%, бюджет%, cost |
| AW-04 | Pull-to-refresh | Потянуть вниз | Данные обновлены, новый timestamp |
| AW-05 | Навигация | Summary → Detail → назад | Плавные переходы, состояние сохранено |
| AW-06 | Пустое состояние | Нет ключей | «Добавьте ключи на iPhone» |
| AW-07 | iOS Settings | Выбрать Anthropic | Пошаговая инструкция |
| AW-08 | Ввод ключа | Ввести → сохранить | Успех или ошибка |

### 4.2 WatchConnectivity

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| AW-09 | iPhone → Watch sync | Добавить провайдер на iPhone | Часы получают обновление |
| AW-10 | Watch без iPhone | Авиарежим на iPhone | Кэшированные данные + «Офлайн» |
| AW-11 | Прямой запрос с часов | Wi-Fi без iPhone | Данные через URLSession |

### 4.3 Complications

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| AW-12 | Отображение % | Добавить complication | Текущий % использования |
| AW-13 | Обновление timeline | Ждать 15 мин | Данные обновлены |
| AW-14 | Тап → приложение | Нажать complication | Открывается SummaryView |

### 4.4 Edge cases

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| AW-15 | Нет интернета | Отключить сеть | Кэш + баннер «Нет соединения» |
| AW-16 | Backend 500 | Замокать 500 | Кэш + «Ошибка обновления» |
| AW-17 | Низкий заряд | Режим экономии энергии | Background refresh off, ручное работает |
| AW-18 | Длинное имя | Замокать длинное имя | Обрезка с многоточием |

---

## 5. Garmin (Connect IQ)

### 5.1 Compact API

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| GR-01 | Парсинг compact JSON | Замокать `{"p":[...]}` → `DataModel.parse()` | Корректный объект |
| GR-02 | Размер ответа ≤8 KB | 3 провайдера → проверить размер | < 8 KB |
| GR-03 | HTTP через Communications API | `ApiService.fetchData()` | `makeWebRequest` вызван корректно |
| GR-04 | Ошибка сети | Замокать NETWORK_REQUEST_TIMED_OUT | «No connection», нет краша |
| GR-05 | HTTP 401 | Замокать 401 | «Auth error» |

### 5.2 Ограничения памяти

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| GR-06 | Память < 64 KB | Profiler + 3 провайдера | Peak < 64 KB |
| GR-07 | Утечки памяти | 50 циклов обновления | Память стабильна |
| GR-08 | Минимальное устройство | Forerunner 245 (64 KB) | Нет OOM |

### 5.3 Widget UI

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| GR-09 | Glance view | Открыть widget | Сводка с % лимита |
| GR-10 | Detail view | Раскрыть glance | Все провайдеры с метриками |
| GR-11 | Круглый vs прямоугольный экран | Venu + Forerunner | Layout адаптируется |

---

## 6. Wear OS (Kotlin, Jetpack Compose)

### 6.1 UI-тесты

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| WO-01 | SummaryScreen | Замокать данные → открыть | ScalingLazyColumn, прокрутка |
| WO-02 | ProviderScreen | Нажать на провайдер | RPM, TPM, cost с прогресс-барами |
| WO-03 | Material You тема | Сменить цвет | Приложение адаптируется |

### 6.2 Tiles API

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| WO-04 | Tile: сводка | Добавить Tile | %, cost today |
| WO-05 | Tile: обновление | Ждать WorkManager интервал | Данные обновлены |
| WO-06 | Tile: тап | Нажать Tile | Открыть SummaryScreen |

### 6.3 Edge cases

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| WO-07 | Нет интернета | Отключить сеть | Кэш + баннер |
| WO-08 | Doze mode | Устройство в Doze → WorkManager | Данные обновлены при выходе |
| WO-09 | Малый RAM | 512 MB + другие приложения | Нет крашей |

---

## 7. Нагрузочное тестирование

### 7.1 Целевые метрики

| Метрика | MVP | Production |
|---|---|---|
| RPS | 50 | 500 |
| Latency p50 | < 100 мс | < 50 мс |
| Latency p99 | < 500 мс | < 200 мс |
| Error rate | < 1% | < 0.1% |
| Пользователей | 100 | 1000 |

### 7.2 Сценарии Locust

| ID | Название | Конфигурация |
|---|---|---|
| LT-01 | Steady state | 50 users, 10 мин |
| LT-02 | Spike | 10 → 200 users за 30с |
| LT-03 | Soak | 30 users, 1 час |
| LT-04 | Только /summary | 80% трафика |
| LT-05 | Mix эндпоинтов | 60% summary, 20% limits, 10% usage, 10% costs |

### 7.3 Provider rate limits

| ID | Название | Шаги | Ожидаемый результат |
|---|---|---|---|
| LT-06 | 100 users, 1 провайдер | 100 summary одновременно | Провайдер вызван 1 раз (кэш) |
| LT-07 | Кэш под нагрузкой | 50 RPS на /summary | Всё из кэша |
| LT-08 | Cache stampede | TTL истекает при 50 RPS | 1 запрос к провайдеру (lock) |
| LT-09 | Graceful degradation при 429 | Провайдер → 429 | Кэш + `"stale": true` |

---

## 8. Чеклист релиза MVP (Go / No-Go)

### Функциональность (обязательно)

- [ ] Регистрация и JWT аутентификация
- [ ] Добавление read-only ключей Anthropic, OpenAI, Vertex AI
- [ ] GET /api/v1/summary, /limits, /usage, /costs работают
- [ ] Apple Watch: SummaryView + ProviderView
- [ ] iOS companion: настройка ключей
- [ ] WatchConnectivity: синхронизация

### Безопасность (обязательно)

- [ ] API-ключи зашифрованы Fernet в БД
- [ ] Валидация read-only при добавлении
- [ ] JWT access + refresh работают
- [ ] Rate limiting на auth-эндпоинтах
- [ ] HTTPS обязателен
- [ ] SQL injection: все запросы параметризованы
- [ ] bandit: 0 high-severity, safety: 0 vulnerabilities

### Качество (обязательно)

- [ ] Backend unit-тесты: покрытие >= 80%
- [ ] Integration-тесты: все эндпоинты покрыты
- [ ] E2E с реальными read-only ключами пройден
- [ ] Нагрузка: 50 RPS без ошибок, p99 < 500 мс
- [ ] Нет memory leaks (soak 1 час)
- [ ] mypy: 0 errors, ruff: 0 warnings

### Инфраструктура (обязательно)

- [ ] Docker-образ собирается
- [ ] docker-compose работает локально
- [ ] Деплой на Fly.io / Railway
- [ ] Health check endpoint
- [ ] Structured JSON logs

### Решение

- **Go**: Все обязательные пункты выполнены
- **No-Go**: Любой обязательный пункт не выполнен → блокер
- **Conditional Go**: Обязательные выполнены, желательные в бэклоге
