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
- `GET /v1/history`
- `GET /v1/admin/health`
- `GET /v1/admin/jobs`

## Safety model
- The OpenAI layer produces structured JSON only.
- Domain validation rejects unsupported indicators, operators, and unsafe constructs.
- The backtest engine executes compiled internal rules, not raw AI-generated Python.
- Python code generation is derived from the validated spec and is display-only.
