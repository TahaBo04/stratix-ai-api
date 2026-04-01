"""Domain validation for strategy specs."""
from __future__ import annotations

from app.schemas.strategy import ConditionNode, StrategySpec, StrategyValidationResult, ValidationIssue
from app.services.catalog import SUPPORTED_OPERATORS, SUPPORTED_TIMEFRAMES, find_asset


MAX_RULE_NESTING = 4
MAX_INDICATORS = 8


def validate_strategy_spec(spec: StrategySpec) -> StrategyValidationResult:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    missing_fields = list(spec.missing_fields)

    asset = find_asset(spec.asset.symbol)
    if asset is None:
        errors.append(ValidationIssue(code="unsupported_asset", field="asset.symbol", message=f"Unsupported asset symbol: {spec.asset.symbol}"))
    elif asset.asset_class != spec.asset.asset_class:
        errors.append(ValidationIssue(code="asset_class_mismatch", field="asset.asset_class", message="Asset class does not match the selected symbol."))

    if spec.timeframe not in SUPPORTED_TIMEFRAMES:
        errors.append(ValidationIssue(code="unsupported_timeframe", field="timeframe", message=f"Unsupported timeframe: {spec.timeframe}"))

    if not spec.entry_rule:
        missing_fields.append("entry_rule")
    if not spec.exit_rule:
        warnings.append(ValidationIssue(code="missing_exit_rule", field="exit_rule", message="No explicit exit rule provided. Stops and take profits will control exits."))
    if not spec.indicators:
        missing_fields.append("indicators")

    indicator_ids = set()
    for indicator in spec.indicators:
        if indicator.id in indicator_ids:
            errors.append(ValidationIssue(code="duplicate_indicator", field="indicators", message=f"Duplicate indicator id: {indicator.id}"))
        indicator_ids.add(indicator.id)
    if len(spec.indicators) > MAX_INDICATORS:
        errors.append(ValidationIssue(code="too_many_indicators", field="indicators", message=f"MVP supports at most {MAX_INDICATORS} indicators."))

    if spec.entry_rule:
        _validate_condition_node(spec.entry_rule, indicator_ids, errors, "entry_rule", 1)
    if spec.exit_rule:
        _validate_condition_node(spec.exit_rule, indicator_ids, errors, "exit_rule", 1)

    if spec.risk.stop_loss_value <= 0:
        errors.append(ValidationIssue(code="invalid_stop", field="risk.stop_loss_value", message="Stop loss must be positive."))
    if spec.risk.risk_reward_ratio <= 0:
        errors.append(ValidationIssue(code="invalid_rr", field="risk.risk_reward_ratio", message="Risk/reward must be positive."))

    if spec.asset.symbol and asset and spec.asset.market != asset.market:
        warnings.append(ValidationIssue(code="market_normalized", field="asset.market", message=f"Asset market normalized to {asset.market}."))

    if missing_fields and not errors:
        warnings.append(ValidationIssue(code="needs_clarification", field=None, message="Strategy is missing fields required for execution."))

    is_valid = not errors and not missing_fields
    return StrategyValidationResult(is_valid=is_valid, errors=errors, warnings=warnings, missing_fields=sorted(set(missing_fields)))


def _validate_condition_node(node: ConditionNode, indicator_ids: set[str], errors: list[ValidationIssue], field_prefix: str, depth: int) -> None:
    if node.operator not in SUPPORTED_OPERATORS:
        errors.append(ValidationIssue(code="unsupported_operator", field=field_prefix, message=f"Unsupported operator: {node.operator}"))
        return
    if depth > MAX_RULE_NESTING:
        errors.append(ValidationIssue(code="rule_too_deep", field=field_prefix, message=f"Maximum rule nesting depth is {MAX_RULE_NESTING}."))
        return
    if node.operator in {"and", "or"}:
        for idx, child in enumerate(node.conditions):
            _validate_condition_node(child, indicator_ids, errors, f"{field_prefix}.conditions[{idx}]", depth + 1)
        return
    for side_name, operand in (("left", node.left), ("right", node.right)):
        if operand and operand.indicator_ref and operand.indicator_ref not in indicator_ids:
            errors.append(ValidationIssue(code="unknown_indicator_ref", field=f"{field_prefix}.{side_name}", message=f"Unknown indicator reference: {operand.indicator_ref}"))
