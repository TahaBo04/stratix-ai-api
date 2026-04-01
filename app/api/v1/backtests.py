"""Backtest routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import get_current_user
from app.repositories.backtests import create_run, get_equity_curve, get_run, get_trades, list_history
from app.repositories.strategies import get_latest_version, get_strategy, get_version
from app.schemas.backtests import BacktestCreateRequest, BacktestResultResponse, BacktestRunResponse, HistoryItem
from app.schemas.strategy import StrategySpec
from app.services.results_serializer import (
    build_metric_cards,
    serialize_drawdown_curve,
    serialize_equity_curve,
    serialize_price_series,
    serialize_trade_markers,
    serialize_trades,
)
from app.services.market_data import load_bars
from app.workers.jobs import enqueue_backtest


router = APIRouter(tags=["backtests"])


@router.post("/v1/strategies/{strategy_id}/backtests", response_model=BacktestRunResponse)
def create_backtest(strategy_id: str, payload: BacktestCreateRequest, current_user: dict = Depends(get_current_user)) -> BacktestRunResponse:
    strategy = get_strategy(strategy_id)
    if strategy is None or strategy["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Strategy not found")
    version = get_latest_version(strategy_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Strategy version not found")
    spec = StrategySpec.model_validate(version["spec_json"])
    run = create_run(
        strategy_version_id=version["id"],
        asset_symbol=spec.asset.symbol,
        asset_class=spec.asset.asset_class,
        market=spec.asset.market,
        timeframe=spec.timeframe,
        date_start=spec.date_range.start,
        date_end=spec.date_range.end,
        initial_capital=payload.initial_capital,
        fees_bps=payload.fees_bps,
        slippage_bps=payload.slippage_bps,
    )
    enqueue_backtest(run["id"])
    return _serialize_run(run)


@router.get("/v1/backtests/{run_id}", response_model=BacktestRunResponse)
def get_backtest(run_id: str, current_user: dict = Depends(get_current_user)) -> BacktestRunResponse:
    run = _get_user_run(run_id, current_user["id"])
    return _serialize_run(run)


@router.get("/v1/backtests/{run_id}/results", response_model=BacktestResultResponse)
def get_backtest_results(run_id: str, current_user: dict = Depends(get_current_user)) -> BacktestResultResponse:
    run = _get_user_run(run_id, current_user["id"])
    version = get_version(run["strategy_version_id"])
    if version is None:
        raise HTTPException(status_code=404, detail="Strategy version not found")
    frame = load_bars(run["asset_symbol"], run["timeframe"], run["date_start"], run["date_end"])
    price_rows = [
        {
            "timestamp": row["timestamp"].isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }
        for _, row in frame.iterrows()
    ]
    trades = get_trades(run_id)
    equity = get_equity_curve(run_id)
    summary = run["summary_json"] or {}
    return BacktestResultResponse(
        run=_serialize_run(run),
        metrics=build_metric_cards(summary),
        summary=summary,
        generated_python=version["generated_python"],
        price_series=serialize_price_series(price_rows),
        equity_curve=serialize_equity_curve(equity),
        drawdown_curve=serialize_drawdown_curve(equity),
        trade_markers=serialize_trade_markers(trades),
        trades=serialize_trades(trades),
    )


@router.get("/v1/backtests/{run_id}/trades")
def get_backtest_trades(run_id: str, current_user: dict = Depends(get_current_user)) -> list[dict]:
    _get_user_run(run_id, current_user["id"])
    return get_trades(run_id)


@router.get("/v1/history", response_model=list[HistoryItem])
def history(current_user: dict = Depends(get_current_user)) -> list[HistoryItem]:
    rows = list_history(current_user["id"])
    return [
        HistoryItem(
            strategy_id=row["strategy_id"],
            strategy_name=row["strategy_name"],
            run_id=row["run_id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            timeframe=row["timeframe"],
            asset_symbol=row["asset_symbol"],
            summary=row["summary_json"],
        )
        for row in rows
    ]


def _get_user_run(run_id: str, user_id: str) -> dict:
    strategy_id = get_strategy_id_for_run(run_id, user_id)
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    if get_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return run


def get_strategy_id_for_run(run_id: str, user_id: str) -> str:
    history_items = list_history(user_id)
    for item in history_items:
        if item["run_id"] == run_id:
            return item["strategy_id"]
    raise HTTPException(status_code=404, detail="Backtest run not found")


def _serialize_run(run: dict) -> BacktestRunResponse:
    return BacktestRunResponse(
        id=run["id"],
        strategy_version_id=run["strategy_version_id"],
        status=run["status"],
        asset_symbol=run["asset_symbol"],
        asset_class=run["asset_class"],
        market=run["market"],
        timeframe=run["timeframe"],
        date_start=run["date_start"],
        date_end=run["date_end"],
        initial_capital=run["initial_capital"],
        fees_bps=run["fees_bps"],
        slippage_bps=run["slippage_bps"],
        created_at=datetime.fromisoformat(run["created_at"]),
        started_at=datetime.fromisoformat(run["started_at"]) if run.get("started_at") else None,
        completed_at=datetime.fromisoformat(run["completed_at"]) if run.get("completed_at") else None,
    )
