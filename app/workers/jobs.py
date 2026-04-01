"""In-process job queue used for the MVP."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from app.repositories.backtests import create_job_log
from app.workers.runners import run_backtest_job


_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="stratix-worker")
_FUTURES: dict[str, Future] = {}


def enqueue_backtest(run_id: str) -> None:
    create_job_log(job_type="backtest", entity_id=run_id, status="queued")
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
