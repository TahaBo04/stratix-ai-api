"""In-process job queue used for the MVP."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from app.core.config import get_settings
from app.core.logging import get_logger
from app.repositories.backtests import create_job_log
from app.workers.runners import run_backtest_job


_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="stratix-worker")
_FUTURES: dict[str, Future] = {}
logger = get_logger(__name__)


def enqueue_backtest(run_id: str) -> None:
    create_job_log(job_type="backtest", entity_id=run_id, status="queued")
    if get_settings().backtest_execution_mode == "inline":
        logger.info("executing_backtest_inline run_id=%s", run_id)
        try:
            run_backtest_job(run_id)
        except Exception as exc:
            logger.error("inline_backtest_failed run_id=%s error=%s", run_id, exc, exc_info=(type(exc), exc, exc.__traceback__))
        return
    future = _EXECUTOR.submit(run_backtest_job, run_id)
    _FUTURES[run_id] = future


def job_status_snapshot() -> list[dict]:
    snapshot = []
    for run_id, future in list(_FUTURES.items()):
        if future.running():
            status = "running"
        elif future.done():
            status = "completed" if future.exception() is None else "failed"
        else:
            status = "queued"
        snapshot.append({"run_id": run_id, "status": status})
    return snapshot
