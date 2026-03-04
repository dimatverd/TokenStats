# TokenStats — Исследование API провайдеров

> Дата исследования: 2 марта 2026

---

## 1. Anthropic Admin API

**Документация:** https://docs.anthropic.com/en/api/admin-api

### 1.1 Аутентификация

- **Тип ключа:** Admin API key (формат `sk-ant-admin-...`)
- **Создание:** Console → Settings → Admin API Keys → Create
- **Требования:** Только пользователи с ролью `admin` в организации
- **Read-only scopes:** `organization_read`, `usage_read`
- **Обязательный заголовок:** `anthropic-version: 2023-06-01`
- **Важно:** Admin API недоступен для индивидуальных аккаунтов (нужна организация)

### 1.2 Endpoints

**GET /v1/organizations/usage_report/messages** — Usage Report

Параметры: `starting_at` (обязат., RFC 3339), `ending_at`, `bucket_width` (1m/1h/1d), `group_by[]` (api_key_id, workspace_id, model, service_tier, context_window, inference_geo, speed), `models[]`, `api_key_ids[]`, `workspace_ids[]`, `service_tiers[]`, `limit`, `page`.

Лимиты гранулярности: 1m — до 1440 бакетов, 1h — до 168, 1d — до 31.

Ответ содержит: `uncached_input_tokens`, `cache_read_input_tokens`, `cache_creation` (ephemeral_5m/1h), `output_tokens`, `server_tool_use.web_search_requests`.

**GET /v1/organizations/cost_report** — Cost Report

Параметры: `starting_at` (обязат.), `ending_at`, `bucket_width` (только 1d), `group_by[]` (workspace_id, description), `limit`, `page`.

Ответ: `amount` (строка в центах, "12345.67" USD = $123.46), `currency`, `cost_type` (tokens/web_search/code_execution), `model`, `service_tier`, `token_type`.

**Rate limits** — отдельного endpoint нет. Данные доступны только через заголовки ответа Messages API (`anthropic-ratelimit-requests-limit/remaining/reset`, `anthropic-ratelimit-tokens-limit/remaining/reset`). Read-only Admin key не может делать inference-запросы.

Задержка данных: ~5 минут. Рекомендуемый polling: 1 раз/мин.

---

## 2. OpenAI Admin API

**Документация:** https://platform.openai.com/docs/api-reference/usage

### 2.1 Аутентификация

- **Тип ключа:** Admin API key
- **Создание:** Settings → Organization → Admin Keys
- **Доступ:** Только Organization Owners
- **Авторизация:** `Authorization: Bearer $OPENAI_ADMIN_KEY`

### 2.2 Endpoints

**GET /v1/organization/usage/completions** — Usage

Параметры: `start_time` (обязат., Unix seconds), `end_time`, `bucket_width` (1m/1h/1d), `group_by[]` (project_id, user_id, api_key_id, model, batch, service_tier), `project_ids[]`, `models[]`, `limit`, `page`.

Ответ: `input_tokens`, `output_tokens`, `input_cached_tokens`, `input_audio_tokens`, `output_audio_tokens`, `num_model_requests`, `model`, `project_id`.

Дополнительные endpoints: `/usage/embeddings`, `/usage/images`, `/usage/audio_speeches`, `/usage/audio_transcriptions`, `/usage/moderations`.

**GET /v1/organization/costs** — Costs

Параметры: `start_time` (обязат.), `bucket_width` (только 1d), `project_ids[]`, `group_by[]` (project_id, line_item), `limit`, `page`.

Ответ: `amount.value` (число, доллары), `amount.currency` ("usd"), `line_item`, `project_id`.

**GET /v1/organization/projects/{project_id}/rate_limits** — Rate Limits

Ответ: `model`, `max_requests_per_1_minute`, `max_tokens_per_1_minute`, `max_images_per_1_minute`, `max_audio_megabytes_per_1_minute`, `batch_1_day_max_input_tokens`.

**Ключевое преимущество:** Единственный провайдер с отдельным endpoint для rate limits через Admin key.

---

## 3. Google Vertex AI

### 3.1 Аутентификация

- **Тип ключа:** Service Account JSON
- **OAuth2:** получение access token через google-auth
- **Авторизация:** `Authorization: Bearer <oauth2_token>`

### 3.2 Необходимые роли Service Account

| Роль | ID | Назначение |
|---|---|---|
| Monitoring Viewer | `roles/monitoring.viewer` | Чтение метрик Cloud Monitoring |
| Billing Account Viewer | `roles/billing.viewer` | Просмотр биллинга |
| Quota Viewer | `roles/servicemanagement.quotaViewer` | Просмотр квот |
| BigQuery Data Viewer | `roles/bigquery.dataViewer` | Чтение billing export |
| BigQuery Job User | `roles/bigquery.jobUser` | Запросы в BigQuery |

### 3.3 API

**Cloud Monitoring API** (`monitoring.googleapis.com/v3/projects/{id}/timeSeries`) — request count, latency, quota usage. Гранулярность от 60s. **Нет нативных токен-метрик** для GenAI моделей.

**Cloud Quotas API** (`cloudquotas.googleapis.com`) — текущие лимиты и usage квот.

**BigQuery Export для Billing** — детальные расходы через SQL-запросы к таблице `gcp_billing_export_resource_v1_{BILLING_ACCOUNT_ID}`. **Задержка до 24 часов.**

### 3.4 Проблемы

1. Нет единого endpoint для usage + costs
2. Нет токен-метрик в Cloud Monitoring для GenAI
3. BigQuery для costs требует предварительной настройки
4. OAuth2 значительно сложнее простого API key

---

## 4. Сравнительная таблица

| | Anthropic | OpenAI | Vertex AI |
|---|---|---|---|
| **Usage endpoint** | `/v1/organizations/usage_report/messages` | `/v1/organization/usage/completions` | Cloud Monitoring timeSeries |
| **Cost endpoint** | `/v1/organizations/cost_report` | `/v1/organization/costs` | BigQuery Export |
| **Rate limits endpoint** | Нет (заголовки ответа) | `/projects/{id}/rate_limits` | Cloud Quotas API |
| **Auth** | Admin key (`x-api-key`) | Admin key (Bearer) | OAuth2 (Service Account) |
| **Гранулярность usage** | 1m, 1h, 1d | 1m, 1h, 1d | От 60s |
| **Гранулярность costs** | 1d | 1d | 1d (BigQuery) |
| **Токен-метрики** | Да (input, cached, output) | Да (input, output, cached, audio) | Нет нативных |
| **Задержка usage** | ~5 мин | ~минуты | ~1-3 мин |
| **Задержка costs** | ~5 мин | ~реальное время | До 24 часов |
| **Сложность интеграции** | Низкая | Низкая | Высокая |

---

## 5. Конкуренты и аналоги

**Прямых конкурентов (мониторинг LLM на часах) не обнаружено.** Ниша полностью свободна.

Косвенные конкуренты — веб-платформы:

| Продукт | Тип | Мобильное приложение |
|---|---|---|
| Langfuse | Open-source, token/cost tracking | Нет |
| Helicone | AI gateway + analytics | Нет |
| LiteLLM | Proxy с мониторингом | Нет |
| Braintrust | AI observability | Нет |
| LangSmith | LangChain observability | Нет |
| Datadog LLM Observability | Enterprise monitoring | Нет watch-app |

Все — веб-дашборды/прокси, без мобильных/watch-приложений.

---

## 6. Выводы и рекомендации

### Что подтвердилось из PLAN.md

- Все endpoints из PLAN.md существуют и работают как описано
- Read-only Admin keys доступны у Anthropic и OpenAI
- Service Account с viewer-ролями работает для Vertex AI
- Ниша мониторинга LLM на часах полностью свободна

### Что нужно скорректировать (критичное)

1. **Anthropic rate limits:** Read-only Admin key **НЕ может** получить заголовки rate limits (нет доступа к Messages API). Нужен workaround — статическая таблица лимитов по tier или оценка на основе usage.

2. **Vertex AI costs задержка:** До 24 часов (не "раз в час" как в плане). Нужно рассчитывать estimated costs на основе usage × price.

3. **Vertex AI без токен-метрик:** Cloud Monitoring даёт request count, но не input/output tokens для GenAI. Показывать request count или estimated tokens.

4. **Vertex AI сложность настройки:** Перенести в пост-MVP фазу. Пошаговый wizard обязателен.

### Рекомендуемый порядок реализации

1. **OpenAI** — самый полный API (usage + costs + rate limits через один Admin key)
2. **Anthropic** — хороший API для usage/costs, workaround для rate limits
3. **Vertex AI** — сложная интеграция, отложить на V1.2+
