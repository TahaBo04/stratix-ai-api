# STRATIX AI API

FastAPI backend for STRATIX AI. The backend converts natural-language strategy prompts into a validated `StrategySpec`, compiles that spec into deterministic internal logic, and runs historical backtests on local seed datasets.

## Highlights
- JSON-first OpenAI parsing via the Responses API
- Safe `StrategySpec` validation before execution
- Deterministic backtest engine for crypto and forex OHLCV data
- SQLite-backed repositories for local MVP development
- Seed market data and in-process job runner for demo readiness

## Quickstart
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Deploying on Vercel
This repository now includes the Vercel-specific files needed for a first deployment:
- `app/index.py`
- `.python-version`

Vercel's current FastAPI runtime supports zero-configuration entrypoints such as
`app/index.py`, so `vercel.json` is intentionally omitted here.

Use these Vercel project settings:
- Framework Preset: `FastAPI` or auto-detected Python/FastAPI
- Root Directory: leave blank when deploying this repo directly
- Build Command: leave blank
- Install Command: leave blank
- Output Directory: leave blank

Recommended environment variables:
```env
APP_ENV=production
SECRET_KEY=replace_with_a_long_random_secret
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL_PRIMARY=gpt-5.4-mini
OPENAI_MODEL_FALLBACK=gpt-5.4
OPENAI_REQUEST_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2
BACKTEST_EXECUTION_MODE=inline
CORS_ORIGINS=https://your-frontend.vercel.app
DEFAULT_DEMO_USER_EMAIL=demo@stratix.ai
DEFAULT_DEMO_USER_PASSWORD=demo-password
```

Deployment notes:
- On Vercel, the backend will automatically fall back to `/tmp/stratix_ai.db` unless `DATABASE_PATH` is explicitly set.
- On Vercel Hobby, prefer `BACKTEST_EXECUTION_MODE=inline`; in-process thread queues are not durable across serverless invocations.
- The seed datasets under `datasets/` are read-only inputs and can still be bundled for demo usage.
- This is suitable for a demo or small MVP, but not ideal for long-running or high-volume backtests because Vercel Functions have request-time limits and ephemeral storage.
- For a more durable production setup, move the database to Postgres and market data to object storage.

## API overview
- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `GET /v1/me`
- `GET /v1/catalog/indicators`
- `GET /v1/catalog/assets`
- `POST /v1/strategies/interpret`
- `POST /v1/strategies`
- `GET /v1/strategies/{strategy_id}`
- `PATCH /v1/strategies/{strategy_id}`
- `POST /v1/strategies/{strategy_id}/backtests`
- `GET /v1/backtests/{run_id}`
- `GET /v1/backtests/{run_id}/results`
- `GET /v1/backtests/{run_id}/trades`
- `POST /v1/backtests/{run_id}/refine`
- `GET /v1/runs/compare`
- `GET /v1/history`
- `GET /v1/admin/health`
- `GET /v1/admin/jobs`

## Safety model
- The OpenAI layer produces structured JSON only.
- Domain validation rejects unsupported indicators, operators, and unsafe constructs.
- The backtest engine executes compiled internal rules, not raw AI-generated Python.
- Python code generation is derived from the validated spec and is display-only.
