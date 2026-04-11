"""Schemas for STRATIX Pro refinement and run comparison."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.backtests import BacktestRunResponse
from app.schemas.strategy import ServiceTier, StrategyResponse


class OptimizationVariable(BaseModel):
    key: str
    label: str
    current_value: float
    min_value: float
    max_value: float
    step: float = Field(gt=0)


class OptimizationWeights(BaseModel):
    net_profit: float = Field(default=0.35, ge=0, le=1)
    win_rate: float = Field(default=0.2, ge=0, le=1)
    drawdown: float = Field(default=0.2, ge=0, le=1)
    sharpe: float = Field(default=0.15, ge=0, le=1)
    overfitting_penalty: float = Field(default=0.1, ge=0, le=1)


class RefinementPlan(BaseModel):
    objective: str
    objective_weights: OptimizationWeights
    variables: list[OptimizationVariable]
    constraints: list[str]
    algorithm: Literal["ga_cuckoo_hybrid"]
    seed: int
    max_evaluations: int = Field(ge=10, le=120)
    source: Literal["openai", "heuristic"]


class ComparisonMetric(BaseModel):
    key: str
    label: str
    baseline_value: float
    candidate_value: float
    delta: float


class StrategyComparison(BaseModel):
    metrics: list[ComparisonMetric]
    baseline_summary: dict[str, Any]
    candidate_summary: dict[str, Any]


class RefineStrategyRequest(BaseModel):
    max_evaluations: int = Field(default=36, ge=10, le=120)


class RefineStrategyResponse(BaseModel):
    service_tier: ServiceTier = "pro"
    triggered_by_win_rate: bool
    recommendation: str
    plan: RefinementPlan
    baseline_run: BacktestRunResponse
    optimized_run: BacktestRunResponse
    optimized_strategy: StrategyResponse
    comparison: StrategyComparison


class RunComparisonResponse(BaseModel):
    baseline_run: BacktestRunResponse
    candidate_run: BacktestRunResponse
    comparison: StrategyComparison
