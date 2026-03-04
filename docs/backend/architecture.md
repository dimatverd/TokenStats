# TokenStats Backend — Детальная архитектура

## 1. Структура проекта

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application, CORS, lifespan events
│   ├── config.py               # Конфигурация через pydantic-settings
│   ├── db.py                   # SQLAlchemy engine, session, Base
│   ├── cache.py                # In-memory TTL cache (cachetools)
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── router.py           # POST /auth/register, /auth/login, /auth/token
│   │   ├── models.py           # SQLAlchemy: User, APIKeyStore
│   │   ├── schemas.py          # Pydantic: RegisterRequest, LoginRequest, TokenResponse
│   │   ├── dependencies.py     # get_current_user — JWT Bearer dependency
│   │   ├── security.py         # JWT encode/decode, password hashing (bcrypt)
│   │   └── encryption.py       # Fernet encrypt/decrypt для API-ключей
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py             # BaseProvider — ABC интерфейс
│   │   ├── anthropic.py        # AnthropicProvider (Admin API, sk-ant-admin-...)
│   │   ├── openai.py           # OpenAIProvider (Admin API)
│   │   ├── google.py           # GoogleVertexProvider (Service Account JSON)
│   │   └── registry.py         # ProviderRegistry — фабрика провайдеров
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py           # Корневой APIRouter /api/v1
│   │   ├── usage.py            # GET /api/v1/usage/{provider}
│   │   ├── limits.py           # GET /api/v1/limits/{provider}
│   │   ├── costs.py            # GET /api/v1/costs/{provider}
│   │   ├── summary.py          # GET /api/v1/summary
│   │   ├── history.py          # GET /api/v1/history/{provider}
│   │   ├── devices.py          # POST /api/v1/devices/register
│   │   └── schemas.py          # Pydantic response-модели для API
│   │
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── service.py          # Push-уведомления (APNs, FCM)
│   │
│   └── tasks/
│       ├── __init__.py
│       └── polling.py          # Background polling провайдеров (asyncio)
│
├── alembic/
│   ├── env.py
│   └── versions/               # Миграции БД
│
├── tests/
│   ├── conftest.py             # Fixtures: test client, test DB, mock providers
│   ├── test_auth.py
│   ├── test_providers.py
│   ├── test_api.py
│   └── test_cache.py
│
├── alembic.ini
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

### Описание модулей

| Модуль | Ответственность |
|---|---|
| `app/main.py` | Точка входа. Создание FastAPI app, подключение роутеров, CORS middleware, lifespan (startup/shutdown для background tasks и DB) |
| `app/config.py` | Загрузка переменных окружения через `pydantic-settings`. Единый объект `Settings` |
| `app/db.py` | Инициализация SQLAlchemy async engine, `AsyncSession`, декларативная `Base` |
| `app/cache.py` | Обёртка над `cachetools.TTLCache` с разными TTL для rate limits и usage |
| `app/auth/` | Регистрация, логин, JWT-токены, шифрование API-ключей |
| `app/providers/` | Абстракция провайдеров. Каждый провайдер — класс, наследующий `BaseProvider` |
| `app/api/` | REST-эндпоинты. Тонкий слой: валидация, вызов провайдера, возврат Pydantic-модели |
| `app/tasks/` | Фоновые задачи: периодический polling провайдеров, проверка порогов для push |
| `alembic/` | Миграции схемы БД |
| `tests/` | Unit и интеграционные тесты |

---

## 2. Модели данных (SQLAlchemy)

### User

```python
class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    email: str = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password: str = Column(String(255), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    api_keys = relationship("APIKeyStore", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
```

### APIKeyStore

```python
class ProviderType(str, enum.Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"

class APIKeyStore(Base):
    __tablename__ = "api_keys"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider: str = Column(SAEnum(ProviderType), nullable=False)
    encrypted_key: str = Column(String(1024), nullable=False)  # Fernet-зашифрованный
    key_hint: str = Column(String(20), nullable=True)          # Последние 4 символа
    label: str = Column(String(100), nullable=True)
    is_valid: bool = Column(Boolean, default=True, nullable=False)
    validated_at: datetime = Column(DateTime, nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
    project_id: str = Column(String(255), nullable=True)       # Только для Google Vertex AI

    user = relationship("User", back_populates="api_keys")
```

### UsageRecord

```python
class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider: str = Column(String(20), nullable=False, index=True)
    model: str = Column(String(100), nullable=True)
    input_tokens: int = Column(BigInteger, default=0)
    output_tokens: int = Column(BigInteger, default=0)
    total_tokens: int = Column(BigInteger, default=0)
    request_count: int = Column(Integer, default=0)
    period_start: datetime = Column(DateTime, nullable=False)
    period_end: datetime = Column(DateTime, nullable=False)
    recorded_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### CostRecord

```python
class CostRecord(Base):
    __tablename__ = "cost_records"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider: str = Column(String(20), nullable=False, index=True)
    amount_usd: float = Column(Float, nullable=False)
    currency: str = Column(String(3), default="USD")
    period_date: date = Column(DateTime, nullable=False)
    period_type: str = Column(String(10), default="daily")     # "daily" | "monthly"
    recorded_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### Device

```python
class Device(Base):
    __tablename__ = "devices"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform: str = Column(String(20), nullable=False)         # "apns" | "fcm"
    device_token: str = Column(String(512), nullable=False, unique=True)
    device_name: str = Column(String(100), nullable=True)
    is_active: bool = Column(Boolean, default=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="devices")
```

### ER-диаграмма

```
┌──────────┐       ┌──────────────┐
│  User    │──1:N──│  APIKeyStore │
│          │       └──────────────┘
│          │──1:N──┌──────────────┐
│          │       │ UsageRecord  │
│          │       └──────────────┘
│          │──1:N──┌──────────────┐
│          │       │ CostRecord   │
│          │       └──────────────┘
│          │──1:N──┌──────────────┐
│          │       │ Device       │
└──────────┘       └──────────────┘
```

---

## 3. API контракты

### 3.1 Аутентификация

#### `POST /auth/register` — Регистрация

**Request:** `{ email: EmailStr, password: str (min 8) }`
**Response 201:** `{ id, email, created_at }`
**Ошибки:** `400` невалидный input, `409` email уже существует

#### `POST /auth/login` — Логин

**Request:** `{ email, password }`
**Response 200:** `{ access_token, refresh_token, token_type: "bearer", expires_in }`
**Ошибки:** `401` неверные credentials

#### `POST /auth/token` — Обновление токена

**Request:** `{ refresh_token }`
**Response 200:** `TokenResponse`
**Ошибки:** `401` невалидный refresh token

#### `POST /auth/providers` — Добавление API-ключа

**Request:**
```python
class AddProviderRequest(BaseModel):
    provider: ProviderType    # "anthropic" | "openai" | "google"
    api_key: str              # Plaintext ключ (или JSON для Google)
    label: str | None = None
    project_id: str | None = None  # Только для Google
    tier: str | None = None   # Только для Anthropic: "tier1"|"tier2"|"tier3"|"tier4"|"build"|"scale"
                              # Используется для определения rate limits (workaround: Admin API
                              # не даёт доступа к заголовкам rate limits Messages API)
```

**Response 201:** `{ id, provider, key_hint, label, is_valid, validated_at }`
**Ошибки:** `400` невалидный формат, `403` ключ не read-only, `409` уже добавлен

#### `GET /auth/providers` — Список провайдеров

**Response 200:** `{ providers: [ProviderKeyResponse] }`

#### `DELETE /auth/providers/{provider}` — Удаление ключа

**Response:** `204 No Content`

### 3.2 Данные (все требуют `Authorization: Bearer <token>`)

#### `GET /api/v1/summary`

**Query:** `format=full|compact`

**Response 200 (full):**
```python
class SummaryResponse(BaseModel):
    providers: list[ProviderSummary]  # id, name, status, rpm, tpm, cost_today/month, budget
    updated_at: datetime
```

**Response 200 (compact):** `{"p":[{"n":"CL","s":1,"r":4,"t":26,"c":12.5}]}`

#### `GET /api/v1/usage/{provider}`

**Query:** `period=today|week|month`, `model=...`
**Response 200:** `{ provider, period, usage: [{ model, input/output/total_tokens, request_count }], totals, updated_at }`

#### `GET /api/v1/limits/{provider}`

**Response 200:** `{ provider, limits: [{ model, rpm, tpm, rpd }], updated_at }`

#### `GET /api/v1/costs/{provider}`

**Query:** `period=today|week|month`
**Response 200:** `{ provider, period, costs: [{ date, amount_usd }], total_usd, updated_at }`

#### `GET /api/v1/history/{provider}`

**Query:** `days=7` (max 90), `metric=tokens|requests|cost`
**Response 200:** `{ provider, metric, points: [{ timestamp, value }], updated_at }`

#### `POST /api/v1/devices/register`

**Request:** `{ platform: "apns"|"fcm", device_token, device_name? }`
**Response 201:** `{ id, platform, device_name }`

### Общая обёртка ошибок

```python
class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None  # e.g. "key_not_readonly"
```

---

## 4. Провайдер-интерфейс (BaseProvider ABC)

```python
class BaseProvider(ABC):
    @abstractmethod
    async def validate_key(self, api_key: str) -> KeyValidationResult:
        """1) Проверка формата 2) Тестовый read-запрос 3) Проверка read-only"""

    @abstractmethod
    async def get_rate_limits(self, api_key: str) -> list[RateLimits]:
        """Текущие RPM, TPM limits"""

    @abstractmethod
    async def get_usage(self, api_key: str, period_start, period_end) -> list[UsageData]:
        """Потребление токенов за период"""

    @abstractmethod
    async def get_costs(self, api_key: str, period_start, period_end) -> list[CostData]:
        """Расходы в USD за период"""

    @property
    @abstractmethod
    def provider_type(self) -> str: ...   # "anthropic" | "openai" | "google"

    @property
    @abstractmethod
    def display_name(self) -> str: ...    # "Claude" | "OpenAI" | "Vertex AI"
```

### ProviderRegistry (фабрика)

```python
class ProviderRegistry:
    _providers: dict[str, type[BaseProvider]] = {}

    @classmethod
    def register(cls, provider_cls): ...
    @classmethod
    def get(cls, provider_type: str) -> BaseProvider: ...
```

---

## 5. Конфигурация (pydantic-settings)

| Переменная | Тип | По умолчанию | Описание |
|---|---|---|---|
| `DATABASE_URL` | str | `sqlite+aiosqlite:///./tokenstats.db` | Строка подключения к БД |
| `JWT_SECRET_KEY` | str | **обязат.** | Секрет для JWT |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | int | 30 | TTL access token |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | int | 30 | TTL refresh token |
| `FERNET_KEY` | str | **обязат.** | Ключ Fernet для шифрования API-ключей |
| `CACHE_TTL_RATE_LIMITS` | int | 60 | TTL кэша rate limits (сек) |
| `CACHE_TTL_USAGE` | int | 300 | TTL кэша usage (сек) |
| `CACHE_TTL_COSTS` | int | 300 | TTL кэша costs (сек) |
| `RATE_LIMIT_PER_MINUTE` | int | 60 | Rate limit API на пользователя |
| `CORS_ORIGINS` | list[str] | `["*"]` | Разрешённые origins |

---

## 6. Аутентификация

### JWT Flow

```
Client                              Backend
  │  POST /auth/register               │
  ├───────────────────────────────────►│── hash password (bcrypt)
  │  201 {id, email}                   │── save to DB
  │◄───────────────────────────────────┤
  │                                     │
  │  POST /auth/login                   │
  ├───────────────────────────────────►│── verify bcrypt
  │  200 {access_token, refresh_token} │── generate JWT (HS256)
  │◄───────────────────────────────────┤
  │                                     │
  │  GET /api/v1/summary                │
  │  Authorization: Bearer <access>     │
  ├───────────────────────────────────►│── decode JWT, check exp
  │  200 {providers: [...]}            │
  │◄───────────────────────────────────┤
  │                                     │
  │  POST /auth/token                   │
  │  {refresh_token}                    │
  ├───────────────────────────────────►│── verify refresh, issue new access
  │  200 {access_token, refresh_token} │
  │◄───────────────────────────────────┤
```

### Fernet шифрование API-ключей

- Ключ генерируется: `Fernet.generate_key()`
- Шифрование: `fernet.encrypt(plaintext_key.encode())`
- Расшифровка: `fernet.decrypt(encrypted_key.encode())`
- Ключи в БД **никогда** не хранятся в plaintext

---

## 7. Кэширование (TTL-стратегия)

| Тип данных | TTL | Причина |
|------------|-----|---------|
| Rate limits | 60 сек | Часто меняются |
| Usage | 300 сек | Обновляются реже |
| Costs | 300 сек | Задержка у провайдеров |
| Summary | 60 сек | Наследует TTL rate limits |

Реализация: `cachetools.TTLCache` с ключами `{user_id}:{provider}:{data_type}`.
В production заменяется на Redis без изменения интерфейса.

---

## 8. Background Tasks (asyncio polling)

```
FastAPI Lifespan
  startup:  → asyncio.create_task(poll_rate_limits)  [каждые 60 сек]
            → asyncio.create_task(poll_usage_costs)   [каждые 300 сек]
  shutdown: → cancel all tasks

poll_loop:
  for user in active_users:
    for provider in user.providers:
      ├── fetch rate_limits → cache
      ├── fetch usage → cache + DB
      ├── fetch costs → cache + DB
      └── check thresholds → push? (>80% warning, >95% critical)
```

Error handling: при ошибке одного провайдера — логирование, продолжение работы, данные в кэше помечаются "stale".

---

## 9. Безопасность

### Read-only валидация

При добавлении ключа:
1. Проверка формата ключа
2. Тестовый read-запрос к usage endpoint → должен вернуть 200
3. Тестовый inference-запрос → **должен быть отклонён** (иначе ключ не read-only)

### Rate Limiting (slowapi)

| Эндпоинт | Лимит |
|----------|-------|
| `/auth/register` | 5/minute |
| `/auth/login` | 10/minute |
| `/api/v1/*` | 60/minute |

### Дополнительные меры

- HTTPS обязателен (reverse proxy)
- Fernet (AES-128-CBC) для API-ключей
- Bcrypt (cost 12) для паролей
- Pydantic валидация на всех эндпоинтах
- Минимальная длина пароля — 8 символов

---

## 10. Docker

### Dockerfile

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: "3.9"
services:
  backend:
    build: .
    ports: ["8000:8000"]
    env_file: [.env]
    environment:
      DATABASE_URL: postgresql+asyncpg://tokenstats:secret@db:5432/tokenstats
    depends_on:
      db: { condition: service_healthy }
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: tokenstats
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: tokenstats
    volumes: [postgres_data:/var/lib/postgresql/data]
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tokenstats"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
```

---

## 11. Зависимости (requirements.txt)

```
# Web framework
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1

# Database
sqlalchemy[asyncio]==2.0.36
aiosqlite==0.20.0              # SQLite (dev)
asyncpg==0.30.0                # PostgreSQL (prod)
alembic==1.14.1

# Auth & Security
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
cryptography==44.0.0

# HTTP client
httpx==0.28.1

# Cache
cachetools==5.5.1

# Rate limiting
slowapi==0.1.9

# Google Cloud (Vertex AI)
google-auth==2.37.0
google-cloud-monitoring==2.24.1
google-cloud-billing==1.15.2
google-cloud-service-usage==1.11.1

# Push notifications
aioapns==3.3
firebase-admin==6.6.0

# Testing
pytest==8.3.4
pytest-asyncio==0.24.0

# Dev tools
ruff==0.8.6
```
