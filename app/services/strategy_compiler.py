"""Compilation of validated strategy specs into deterministic internal objects."""
from __future__ import annotations

from app.models import CompiledIndicator, CompiledOperand, CompiledRule, CompiledStrategy
from app.schemas.strategy import ConditionNode, Operand, StrategySpec


COMPILER_VERSION = "0.1.0"


def compile_strategy(spec: StrategySpec) -> CompiledStrategy:
    return CompiledStrategy(
        name=spec.name,
        asset_symbol=spec.asset.symbol,
        asset_class=spec.asset.asset_class,
        market=spec.asset.market,
        timeframe=spec.timeframe,
        direction=spec.direction,
        indicators=[
            CompiledIndicator(
                identifier=indicator.id,
                indicator_type=indicator.type,
                params=indicator.model_dump(exclude={"id", "type"}, exclude_none=True),
            )
            for indicator in spec.indicators
        ],
        entry_rule=_compile_condition(spec.entry_rule),
        exit_rule=_compile_condition(spec.exit_rule) if spec.exit_rule else None,
        risk=spec.risk.model_dump(exclude_none=True),
        execution=spec.execution.model_dump(exclude_none=True),
        costs=spec.costs.model_dump(exclude_none=True),
        date_range=spec.date_range.model_dump(),
    )


def _compile_condition(node: ConditionNode) -> CompiledRule:
    if node.operator in {"and", "or"}:
        return CompiledRule(operator=node.operator, conditions=[_compile_condition(child) for child in node.conditions])
    return CompiledRule(operator=node.operator, left=_compile_operand(node.left), right=_compile_operand(node.right))


def _compile_operand(operand: Operand | None) -> CompiledOperand:
    if operand is None:
        raise ValueError("Operand is required")
    if operand.indicator_ref is not None:
        return CompiledOperand(kind="indicator", value=operand.indicator_ref)
    return CompiledOperand(kind="value", value=operand.value)
