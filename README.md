# Estatio — Local Development Setup

Estatio is an AI-native property management platform. This guide covers running the full stack locally.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, MongoDB, Celery, Redis |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| AI | Gemini (primary), OpenAI, Anthropic |
| Auth | Google OAuth 2.0 + JWT |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- [Node.js 20+](https://nodejs.org/) and npm (for frontend without Docker)
- [Python 3.11+](https://www.python.org/) and pip (for backend without Docker)
- A [MongoDB Atlas](https://www.mongodb.com/atlas) account **or** use the local MongoDB container
- A [Google Cloud](https://console.cloud.google.com/) project with OAuth credentials
- A [Gemini API key](https://aistudio.google.com/app/apikey)

---

## Option 1 — Docker Compose (Recommended)

The easiest way to run everything together (backend, frontend, MongoDB, Redis, Celery worker).

### 1. Clone the repo

```bash
git clone <repo-url>
cd Estatio
```

### 2. Configure environment variables

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and fill in the required values:

```env
# App
SECRET_KEY=your-secret-key-here          # any long random string
APP_ENV=development

# MongoDB — use the local Docker container
MONGODB_URL=mongodb://mongo:27017
MONGODB_DB=estatio_dev

# Google OAuth (required for login)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# AI (at least one is required)
GEMINI_API_KEY=your-gemini-api-key
AI_PROVIDER=gemini

# Redis — use the local Docker container
REDIS_URL=redis://redis:6379/0

# Frontend
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=["http://localhost:3000"]
```

> Optional: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `STRIPE_SECRET_KEY`, `SENDGRID_API_KEY`, `GCS_BUCKET_NAME`

### 3. Start all services

```bash
docker-compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (Redoc) | http://localhost:8000/redoc |
| Health check | http://localhost:8000/health |

### 4. Stop services

```bash
docker-compose down          # stop containers
docker-compose down -v       # stop and delete MongoDB data volume
```

---

## Option 2 — Run Services Individually

### Backend

```bash
cd backend

# Create and activate a virtual environment
python3.11 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set MONGODB_URL, GOOGLE_CLIENT_ID/SECRET, GEMINI_API_KEY, etc.

# Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Celery worker** (optional, needed for background tasks):

```bash
# In a separate terminal, with venv activated
cd backend
celery -A app.workers.celery_app worker --loglevel=info
```

> Requires Redis running locally. Install via Homebrew: `brew install redis && brew services start redis`

### Frontend

```bash
cd frontend

npm install

npm run dev        # starts Vite dev server on http://localhost:3000
```

The Vite dev server proxies `/api` requests to `http://localhost:8000`.

### MongoDB (local, without Docker)

Install and run MongoDB 7 locally, or use [MongoDB Atlas](https://www.mongodb.com/atlas) (free tier works).

For Atlas, set `MONGODB_URL` in `backend/.env` to your Atlas connection string.

---

## Google OAuth Setup

Login requires a Google OAuth 2.0 application.

1. Go to [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. Create an **OAuth 2.0 Client ID** (Web application type)
3. Add to **Authorized redirect URIs**:
   ```
   http://localhost:8000/api/v1/auth/google/callback
   ```
4. Copy the **Client ID** and **Client Secret** into `backend/.env`

---

## Running Tests

### Backend

```bash
cd backend
source venv/bin/activate
pytest                          # run all tests
pytest --cov=app                # with coverage report
ruff check app/                 # linting
```

### Frontend

```bash
cd frontend
npm run lint                    # ESLint
npx tsc --noEmit                # TypeScript type-check
npm run build                   # full production build check
```

---

## Project Structure

```
Estatio/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI entry point
│   │   ├── core/               # config, database, auth, security
│   │   ├── models/             # MongoDB data models
│   │   ├── routers/            # API endpoints (auth, properties, tenants, ...)
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # business logic
│   │   ├── ai/                 # AI integration (Gemini, OpenAI, Anthropic)
│   │   └── workers/            # Celery background tasks
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/              # route-level components
│   │   ├── components/         # reusable UI components
│   │   ├── services/           # API client
│   │   └── store/              # Zustand state management
│   ├── package.json
│   └── vite.config.ts
├── terraform/                  # GCP infrastructure as code
├── scripts/                    # GCP setup and secrets sync
├── docker-compose.yml
└── .github/workflows/          # CI/CD pipelines
```

---

## Common Issues

**`CORS error` in browser**
Ensure `CORS_ORIGINS` in `backend/.env` includes `http://localhost:3000` (as a JSON array string).

**`Connection refused` to MongoDB**
When running without Docker, make sure MongoDB is running locally or your Atlas `MONGODB_URL` is correct and your IP is whitelisted.

**Google OAuth redirect mismatch**
The redirect URI in Google Cloud Console must exactly match `GOOGLE_REDIRECT_URI` in `backend/.env`.

**Celery tasks not processing**
Ensure Redis is running and `REDIS_URL` points to it. When using Docker Compose, this is handled automatically.
