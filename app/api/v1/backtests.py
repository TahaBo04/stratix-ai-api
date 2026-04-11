"""Backtest routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import get_current_user
from app.core.config import get_settings
from app.repositories.backtests import create_run, get_equity_curve, get_run, get_trades, list_history
from app.repositories.strategies import create_strategy, create_strategy_version, get_latest_version, get_strategy, get_version
from app.schemas.backtests import BacktestCreateRequest, BacktestResultResponse, BacktestRunResponse, HistoryItem
from app.schemas.refinement import RefineStrategyRequest, RefineStrategyResponse, RunComparisonResponse
from app.schemas.strategy import StrategyResponse, StrategySpec, StrategyVersionResponse
from app.services.results_serializer import (
    build_metric_cards,
    serialize_drawdown_curve,
    serialize_equity_curve,
    serialize_price_series,
    serialize_trade_markers,
    serialize_trades,
)
from app.services.market_data import load_bars
from app.services.strategy_codegen import generate_python_strategy
from app.services.strategy_compiler import COMPILER_VERSION
from app.services.strategy_refinement import build_refinement_plan, build_run_comparison, optimize_strategy
from app.services.strategy_validator import validate_strategy_spec
from app.workers.jobs import enqueue_backtest
from app.workers.runners import run_backtest_job
from app.services.ai_parser import PROMPT_VERSION


router = APIRouter(tags=["backtests"])
settings = get_settings()


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
    if settings.backtest_execution_mode == "inline":
        refreshed_run = get_run(run["id"])
        if refreshed_run is not None:
            run = refreshed_run
    return _serialize_run(run)


@router.get("/v1/backtests/{run_id}", response_model=BacktestRunResponse)
def get_backtest(run_id: str, current_user: dict = Depends(get_current_user)) -> BacktestRunResponse:
    run = _get_user_run(run_id, current_user["id"])
    return _serialize_run(run)


@router.get("/v1/backtests/{run_id}/results", response_model=BacktestResultResponse)
def get_backtest_results(run_id: str, current_user: dict = Depends(get_current_user)) -> BacktestResultResponse:
    run = _get_user_run(run_id, current_user["id"])
    if run["status"] == "failed":
        raise HTTPException(status_code=409, detail=run.get("error_message") or "Backtest failed before results were available")
    if run["status"] != "completed":
        raise HTTPException(status_code=409, detail="Backtest results are not available until the run completes")
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
            raw_prompt=row["raw_prompt"],
            service_tier=row.get("service_tier", "simple"),
            run_id=row["run_id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            timeframe=row["timeframe"],
            asset_symbol=row["asset_symbol"],
            summary=row["summary_json"],
        )
        for row in rows
    ]


@router.post("/v1/backtests/{run_id}/refine", response_model=RefineStrategyResponse)
def refine_backtest(run_id: str, payload: RefineStrategyRequest, current_user: dict = Depends(get_current_user)) -> RefineStrategyResponse:
    base_run = _get_user_run(run_id, current_user["id"])
    if base_run["status"] != "completed" or not base_run["summary_json"]:
        raise HTTPException(status_code=409, detail="Complete the baseline backtest before running STRATIX Pro refinement.")

    version = get_version(base_run["strategy_version_id"])
    if version is None:
        raise HTTPException(status_code=404, detail="Strategy version not found")
    strategy = get_strategy(version["strategy_id"])
    if strategy is None or strategy["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Strategy not found")

    baseline_spec = StrategySpec.model_validate(version["spec_json"])
    plan = build_refinement_plan(
        raw_prompt=strategy["raw_prompt"],
        spec=baseline_spec,
        baseline_summary=base_run["summary_json"],
        max_evaluations=payload.max_evaluations,
    )
    optimized_spec, optimization = optimize_strategy(spec=baseline_spec, run_config=base_run, plan=plan)
    validation = validate_strategy_spec(optimized_spec)
    optimized_spec.status = "valid" if validation.is_valid else "needs_clarification"
    optimized_spec.missing_fields = validation.missing_fields
    if not validation.is_valid:
        raise HTTPException(status_code=422, detail="The optimized strategy failed validation and was not persisted.")

    refined_strategy = create_strategy(
        user_id=current_user["id"],
        name=optimized_spec.name,
        raw_prompt=strategy["raw_prompt"],
        service_tier="pro",
        status=optimized_spec.status,
    )
    refined_version = create_strategy_version(
        strategy_id=refined_strategy["id"],
        version_no=1,
        spec=optimized_spec.model_dump(mode="json"),
        compiler_version=COMPILER_VERSION,
        prompt_version=PROMPT_VERSION,
        generated_python=generate_python_strategy(optimized_spec),
        assumptions=optimized_spec.assumptions,
    )
    optimized_run = create_run(
        strategy_version_id=refined_version["id"],
        asset_symbol=optimized_spec.asset.symbol,
        asset_class=optimized_spec.asset.asset_class,
        market=optimized_spec.asset.market,
        timeframe=optimized_spec.timeframe,
        date_start=optimized_spec.date_range.start,
        date_end=optimized_spec.date_range.end,
        initial_capital=base_run["initial_capital"],
        fees_bps=base_run["fees_bps"],
        slippage_bps=base_run["slippage_bps"],
    )
    run_backtest_job(optimized_run["id"])
    refreshed_optimized_run = get_run(optimized_run["id"])
    if refreshed_optimized_run is None or refreshed_optimized_run["status"] != "completed":
        raise HTTPException(status_code=500, detail="Refinement backtest did not complete successfully.")

    return RefineStrategyResponse(
        service_tier="pro",
        triggered_by_win_rate=float(base_run["summary_json"].get("win_rate", 0.0)) < 50,
        recommendation=optimization["recommendation"],
        plan=plan,
        baseline_run=_serialize_run(base_run),
        optimized_run=_serialize_run(refreshed_optimized_run),
        optimized_strategy=_serialize_strategy_response(refined_strategy, refined_version),
        comparison=optimization["comparison"],
    )


@router.get("/v1/runs/compare", response_model=RunComparisonResponse)
def compare_runs(base_run_id: str, candidate_run_id: str, current_user: dict = Depends(get_current_user)) -> RunComparisonResponse:
    baseline_run = _get_user_run(base_run_id, current_user["id"])
    candidate_run = _get_user_run(candidate_run_id, current_user["id"])
    if baseline_run["status"] != "completed" or candidate_run["status"] != "completed":
        raise HTTPException(status_code=409, detail="Both runs must be completed before comparison.")
    return RunComparisonResponse(
        baseline_run=_serialize_run(baseline_run),
        candidate_run=_serialize_run(candidate_run),
        comparison=build_run_comparison(baseline_run["summary_json"], candidate_run["summary_json"]),
    )


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
        error_message=run.get("error_message"),
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


def _serialize_strategy_response(strategy: dict, version: dict) -> StrategyResponse:
    version_response = StrategyVersionResponse(
        id=version["id"],
        version_no=version["version_no"],
        spec=StrategySpec.model_validate(version["spec_json"]),
        compiler_version=version["compiler_version"],
        prompt_version=version["prompt_version"],
        generated_python=version["generated_python"],
        assumptions=version["assumptions_json"],
        created_at=datetime.fromisoformat(version["created_at"]),
    )
    return StrategyResponse(
        id=strategy["id"],
        user_id=strategy["user_id"],
        name=strategy["name"],
        raw_prompt=strategy["raw_prompt"],
        service_tier=strategy.get("service_tier", "simple"),
        status=strategy["status"],
        created_at=datetime.fromisoformat(strategy["created_at"]),
        latest_version=version_response,
    )
