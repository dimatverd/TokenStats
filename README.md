# TokenStats

Monitor AI provider rate limits & costs on Apple Watch, iPhone and wearables.

## What is this

TokenStats is a unified dashboard for tracking usage limits and spending across Anthropic, OpenAI, and Google Vertex AI. The backend collects provider data via background polling and serves it through a REST API optimized for mobile and wearable clients.

## Stack

- **Runtime:** Python 3.13
- **Framework:** FastAPI + Uvicorn
- **Database:** SQLAlchemy async + aiosqlite
- **Auth:** JWT (python-jose) + Fernet encryption for API keys
- **Testing:** pytest + pytest-asyncio (44 tests)
- **Linting:** ruff

## Features

- **Authentication** — JWT-based registration/login with bcrypt password hashing
- **Provider key management** — encrypted storage of API keys (Fernet), CRUD per user
- **Background polling** — periodic fetching of usage/limits from provider APIs
- **TTL cache** — cachetools-based caching to reduce API calls
- **Rate limiting** — slowapi-based request throttling
- **Provider adapters** — pluggable architecture for Anthropic, OpenAI, Google Vertex AI

## Project structure

```
TokenStats/
├── backend/
│   ├── app/
│   │   ├── auth/          # JWT auth, encryption, user models
│   │   ├── providers/     # Anthropic, OpenAI, Google adapters
│   │   ├── tasks/         # Background polling
│   │   ├── cache.py       # TTL cache
│   │   ├── config.py      # Settings (pydantic-settings)
│   │   ├── db.py          # Async SQLAlchemy engine
│   │   └── main.py        # FastAPI app
│   ├── tests/             # 44 tests
│   ├── requirements.txt
│   └── pyproject.toml     # ruff config
├── docs/                  # Architecture, UI spec, test strategy
└── tools/                 # Linear integration scripts
```

## Quick start

```bash
cd backend
pip install -r requirements.txt

# Required environment variables
export FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Tests

```bash
cd backend
pytest -v
```

## Roadmap

- **Sprint 2** — REST API endpoints for providers/usage, iOS SwiftUI client
- **Sprint 3** — watchOS complications, Push notifications
