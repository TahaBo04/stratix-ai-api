"""Strategy specification and route schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


StrategyStatus = Literal["valid", "needs_clarification", "invalid"]
ServiceTier = Literal["simple", "pro"]
Direction = Literal["long", "short"]
AssetClass = Literal["crypto", "forex", "stock", "commodity"]
IndicatorType = Literal["RSI", "SMA", "EMA", "MACD", "BOLLINGER", "ATR"]
Operator = Literal["lt", "lte", "gt", "gte", "crosses_above", "crosses_below", "and", "or"]
StopLossType = Literal["percent", "price", "atr"]
TakeProfitType = Literal["fixed_percent", "price", "derived_from_rr", "opposite_signal"]


class AssetSpec(BaseModel):
    asset_class: AssetClass
    symbol: str
    market: str


class DateRange(BaseModel):
    start: str = "2024-01-01"
    end: str = "2025-12-31"


class IndicatorSpec(BaseModel):
    id: str
    type: IndicatorType
    source: str = "close"
    length: Optional[int] = Field(default=None, ge=1, le=500)
    fast_length: Optional[int] = Field(default=None, ge=1, le=500)
    slow_length: Optional[int] = Field(default=None, ge=1, le=500)
    signal_length: Optional[int] = Field(default=None, ge=1, le=500)
    std_dev: Optional[float] = Field(default=None, ge=0.1, le=10.0)
    output: Optional[str] = None


class Operand(BaseModel):
    indicator_ref: Optional[str] = None
    value: Optional[float] = None

    @model_validator(mode="after")
    def ensure_operand_source(self) -> "Operand":
        if self.indicator_ref is None and self.value is None:
            raise ValueError("Operand must include indicator_ref or value")
        return self


class ConditionNode(BaseModel):
    operator: Operator
    left: Optional[Operand] = None
    right: Optional[Operand] = None
    conditions: list["ConditionNode"] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_shape(self) -> "ConditionNode":
        if self.operator in {"and", "or"}:
            if len(self.conditions) < 2:
                raise ValueError("Boolean operators require at least two nested conditions")
        else:
            if self.left is None or self.right is None:
                raise ValueError("Comparison operators require left and right operands")
        return self


ConditionNode.model_rebuild()


class RiskSpec(BaseModel):
    stop_loss_type: StopLossType = "percent"
    stop_loss_value: float = Field(default=2.0, gt=0)
    risk_reward_ratio: float = Field(default=2.0, gt=0)
    take_profit_type: TakeProfitType = "derived_from_rr"
    take_profit_value: Optional[float] = Field(default=None, gt=0)


class ExecutionSpec(BaseModel):
    entry_timing: str = "next_bar_open"
    one_position_at_a_time: bool = True
    sizing_mode: str = "full_notional"


class CostSpec(BaseModel):
    fees_bps: float = Field(default=10.0, ge=0, le=500)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)


class StrategySpec(BaseModel):
    status: StrategyStatus = "needs_clarification"
    name: str
    asset: AssetSpec
    timeframe: str
    date_range: DateRange = Field(default_factory=DateRange)
    direction: Direction = "long"
    indicators: list[IndicatorSpec] = Field(default_factory=list)
    entry_rule: Optional[ConditionNode] = None
    exit_rule: Optional[ConditionNode] = None
    risk: RiskSpec = Field(default_factory=RiskSpec)
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    costs: CostSpec = Field(default_factory=CostSpec)
    missing_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    explanation: Optional[str] = None


class ValidationIssue(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class StrategyValidationResult(BaseModel):
    is_valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class InterpretStrategyRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=4000)


class InterpretStrategyResponse(BaseModel):
    spec: StrategySpec
    validation: StrategyValidationResult
    source: Literal["openai", "heuristic"]
    prompt_digest: str


class CreateStrategyRequest(BaseModel):
    raw_prompt: str = Field(min_length=5, max_length=4000)
    spec: StrategySpec
    service_tier: ServiceTier = "simple"


class UpdateStrategyRequest(BaseModel):
    raw_prompt: Optional[str] = None
    spec: Optional[StrategySpec] = None
    service_tier: Optional[ServiceTier] = None


class StrategyVersionResponse(BaseModel):
    id: str
    version_no: int
    spec: StrategySpec
    compiler_version: str
    prompt_version: str
    generated_python: str
    assumptions: list[str]
    created_at: datetime


class StrategyResponse(BaseModel):
    id: str
    user_id: str
    name: str
    raw_prompt: str
    service_tier: ServiceTier
    status: StrategyStatus
    created_at: datetime
    latest_version: StrategyVersionResponse
