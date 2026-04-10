"""Background task runners."""
from __future__ import annotations

from app.core.logging import get_logger
from app.repositories.backtests import create_job_log, get_run, save_run_results, update_run_status
from app.repositories.strategies import get_version
from app.schemas.strategy import StrategySpec
from app.services.backtest_engine import run_backtest
from app.services.market_data import load_bars
from app.services.results_serializer import serialize_trade_markers
from app.services.strategy_compiler import compile_strategy


logger = get_logger(__name__)


def run_backtest_job(run_id: str) -> None:
    run = get_run(run_id)
    if run is None:
        return
    update_run_status(run_id, "running")
    create_job_log(job_type="backtest", entity_id=run_id, status="running")
    try:
        version = get_version(run["strategy_version_id"])
        if version is None:
            raise RuntimeError("Strategy version not found")
        spec = StrategySpec.model_validate(version["spec_json"])
        compiled = compile_strategy(spec)
        frame = load_bars(run["asset_symbol"], run["timeframe"], run["date_start"], run["date_end"])
        result = run_backtest(compiled, frame, run["initial_capital"])
        result["summary"]["trade_markers"] = [marker.model_dump() for marker in serialize_trade_markers(result["trades"])]
        save_run_results(run_id, result["summary"], result["trades"], result["equity_curve"])
        create_job_log(job_type="backtest", entity_id=run_id, status="completed")
    except Exception as exc:
        update_run_status(run_id, "failed", str(exc))
        logger.error("backtest_job_failed run_id=%s error=%s", run_id, exc, exc_info=(type(exc), exc, exc.__traceback__))
        raise
