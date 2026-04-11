"""Prompt interpretation using OpenAI structured outputs with a heuristic fallback."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.strategy import (
    AssetSpec,
    ConditionNode,
    CostSpec,
    DateRange,
    ExecutionSpec,
    IndicatorSpec,
    InterpretStrategyResponse,
    Operand,
    RiskSpec,
    StrategySpec,
)
from app.services.catalog import ASSETS, SUPPORTED_OPERATORS, SUPPORTED_TIMEFRAMES, find_asset
from app.services.strategy_validator import validate_strategy_spec


PROMPT_VERSION = "0.3.0"
logger = get_logger(__name__)
SYSTEM_PROMPT = """
You are STRATIX AI's deterministic strategy parser.
Convert natural-language trading ideas into the provided StrategySpec schema.
Use only supported indicators, operators, assets, and timeframes.
If the prompt is incomplete or ambiguous, keep unsupported fields null, set status to needs_clarification, and populate missing_fields.
Never invent symbols, indicators, operators, or timeframes outside the supplied catalogs.
Do not produce executable code.
Do not emit freeform text outside the schema.
""".strip()


def interpret_prompt(prompt: str) -> InterpretStrategyResponse:
    settings = get_settings()
    prompt_digest = _build_prompt_digest(prompt)
    if settings.openai_api_key:
        attempted_models: list[str] = []
        for model_name in (settings.openai_model_primary, settings.openai_model_fallback):
            if not model_name or model_name in attempted_models:
                continue
            attempted_models.append(model_name)
            try:
                spec = _finalize_spec(_interpret_with_openai(prompt, model_name))
                validation = validate_strategy_spec(spec)
                spec.status = "valid" if validation.is_valid else "needs_clarification"
                spec.missing_fields = validation.missing_fields
                if model_name != settings.openai_model_primary:
                    logger.warning("strategy_parse_used_fallback_model model=%s", model_name)
                return InterpretStrategyResponse(spec=spec, validation=validation, source="openai", prompt_digest=prompt_digest)
            except Exception as exc:
                logger.warning(
                    "strategy_parse_openai_failed model=%s error=%s",
                    model_name,
                    exc,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )

        logger.warning("strategy_parse_falling_back_to_heuristic attempted_models=%s", attempted_models)

    spec = _finalize_spec(_heuristic_parse(prompt))
    validation = validate_strategy_spec(spec)
    spec.status = "valid" if validation.is_valid else "needs_clarification"
    spec.missing_fields = validation.missing_fields
    return InterpretStrategyResponse(spec=spec, validation=validation, source="heuristic", prompt_digest=prompt_digest)


def _build_prompt_digest(prompt: str) -> str:
    return hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:12]


def _interpret_with_openai(prompt: str, model_name: str) -> StrategySpec:
    settings = get_settings()
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_request_timeout_seconds, max_retries=settings.openai_max_retries)
    response = client.responses.parse(
        model=model_name,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt": prompt,
                        "supported_assets": [asset.model_dump() for asset in ASSETS],
                        "supported_operators": SUPPORTED_OPERATORS,
                        "supported_timeframes": SUPPORTED_TIMEFRAMES,
                        "defaults": {
                            "date_range": {"start": "2024-01-01", "end": "2025-12-31"},
                            "execution": {"entry_timing": "next_bar_open", "one_position_at_a_time": True, "sizing_mode": "full_notional"},
                            "costs": {"fees_bps": 10, "slippage_bps": 5},
                        },
                    }
                ),
            },
        ],
        text_format=StrategySpec,
    )
    return response.output_parsed


def _heuristic_parse(prompt: str) -> StrategySpec:
    text = prompt.strip()
    uppercase = text.upper()

    symbol = _match_symbol(uppercase)
    asset = find_asset(symbol) if symbol else None
    timeframe = _match_timeframe(uppercase)
    direction = "short" if re.search(r"\b(short|sell to open)\b", text, re.I) else "long"

    indicators: list[IndicatorSpec] = []
    entry_rule = None
    exit_rule = None
    assumptions: list[str] = []
    missing_fields: list[str] = []

    rsi_matches = re.findall(r"RSI\s*(?:\(|)?\s*(?:<|>|<=|>=)?\s*(\d+)?", uppercase)
    buy_rsi = re.search(r"buy\s+when\s+rsi\s*(<|<=|>|>=)\s*(\d+(?:\.\d+)?)", text, re.I)
    sell_rsi = re.search(r"sell\s+when\s+rsi\s*(<|<=|>|>=)\s*(\d+(?:\.\d+)?)", text, re.I)
    if buy_rsi or sell_rsi or "RSI" in uppercase:
        indicators.append(IndicatorSpec(id="rsi_14", type="RSI", source="close", length=14))
    if buy_rsi:
        entry_rule = ConditionNode(operator=_op_token_to_name(buy_rsi.group(1)), left=Operand(indicator_ref="rsi_14"), right=Operand(value=float(buy_rsi.group(2))))
    if sell_rsi:
        exit_rule = ConditionNode(operator=_op_token_to_name(sell_rsi.group(1)), left=Operand(indicator_ref="rsi_14"), right=Operand(value=float(sell_rsi.group(2))))

    cross_match = re.search(r"(ema|sma)\s*(\d+)\s*cross(?:es)?\s*above\s*(ema|sma)\s*(\d+)", text, re.I)
    if cross_match:
        fast_type, fast_len, slow_type, slow_len = cross_match.groups()
        fast_id = f"{fast_type.lower()}_{fast_len}"
        slow_id = f"{slow_type.lower()}_{slow_len}"
        indicators.extend(
            [
                IndicatorSpec(id=fast_id, type=fast_type.upper(), source="close", length=int(fast_len)),
                IndicatorSpec(id=slow_id, type=slow_type.upper(), source="close", length=int(slow_len)),
            ]
        )
        entry_rule = ConditionNode(operator="crosses_above", left=Operand(indicator_ref=fast_id), right=Operand(indicator_ref=slow_id))
        assumptions.append("Used the moving-average crossover as the entry trigger.")

    exit_cross = re.search(r"(ema|sma)\s*(\d+)\s*cross(?:es)?\s*below\s*(ema|sma)\s*(\d+)", text, re.I)
    if exit_cross:
        fast_type, fast_len, slow_type, slow_len = exit_cross.groups()
        fast_id = f"{fast_type.lower()}_{fast_len}"
        slow_id = f"{slow_type.lower()}_{slow_len}"
        existing_ids = {indicator.id for indicator in indicators}
        if fast_id not in existing_ids:
            indicators.append(IndicatorSpec(id=fast_id, type=fast_type.upper(), source="close", length=int(fast_len)))
        if slow_id not in existing_ids:
            indicators.append(IndicatorSpec(id=slow_id, type=slow_type.upper(), source="close", length=int(slow_len)))
        exit_rule = ConditionNode(operator="crosses_below", left=Operand(indicator_ref=fast_id), right=Operand(indicator_ref=slow_id))

    rr_match = re.search(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*risk\s*reward|risk\s*reward\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", text, re.I)
    rr_value = 2.0
    if rr_match:
        groups = [value for value in rr_match.groups() if value]
        if len(groups) >= 2 and float(groups[0]) != 0:
            rr_value = float(groups[1]) / float(groups[0])

    stop_match = re.search(r"(?:stop loss|sl)\s*(?:at|=)?\s*(\d+(?:\.\d+)?)%", text, re.I)
    take_match = re.search(r"(?:take profit|tp)\s*(?:at|=)?\s*(\d+(?:\.\d+)?)%", text, re.I)

    risk = RiskSpec(
        stop_loss_type="percent",
        stop_loss_value=float(stop_match.group(1)) if stop_match else 2.0,
        risk_reward_ratio=rr_value,
        take_profit_type="fixed_percent" if take_match else "derived_from_rr",
        take_profit_value=float(take_match.group(1)) if take_match else None,
    )

    if not symbol:
        missing_fields.append("asset.symbol")
        assumptions.append("Defaulted to BTCUSDT until a symbol is confirmed.")
        asset = find_asset("BTCUSDT")
    if not timeframe:
        missing_fields.append("timeframe")
        timeframe = "1h"
        assumptions.append("Defaulted timeframe to 1h until a timeframe is confirmed.")
    if not entry_rule:
        missing_fields.append("entry_rule")
    if not indicators:
        missing_fields.append("indicators")

    assert asset is not None
    name = _build_name(text, asset.symbol, timeframe)
    return StrategySpec(
        status="needs_clarification" if missing_fields else "valid",
        name=name,
        asset=AssetSpec(asset_class=asset.asset_class, symbol=asset.symbol, market=asset.market),
        timeframe=timeframe,
        date_range=DateRange(),
        direction=direction,
        indicators=indicators,
        entry_rule=entry_rule,
        exit_rule=exit_rule,
        risk=risk,
        execution=ExecutionSpec(),
        costs=CostSpec(),
        missing_fields=missing_fields,
        assumptions=assumptions,
        explanation=f"Parsed on {datetime.utcnow().strftime('%Y-%m-%d')} from natural language prompt.",
    )


def _finalize_spec(spec: StrategySpec) -> StrategySpec:
    asset = find_asset(spec.asset.symbol)
    assumptions = list(spec.assumptions)

    if asset is not None:
        if spec.asset.asset_class != asset.asset_class:
            spec.asset.asset_class = asset.asset_class
            assumptions.append(f"Normalized asset class to {asset.asset_class} for {asset.symbol}.")
        if spec.asset.market != asset.market:
            spec.asset.market = asset.market
            assumptions.append(f"Normalized market to {asset.market} for {asset.symbol}.")

    normalized_missing_fields: list[str] = []
    for field in spec.missing_fields:
        if _field_is_covered_by_defaults(field, spec):
            default_note = _default_assumption_for_field(field, spec)
            if default_note and default_note not in assumptions:
                assumptions.append(default_note)
            continue
        normalized_missing_fields.append(field)

    spec.assumptions = assumptions
    spec.missing_fields = sorted(set(normalized_missing_fields))
    return spec


def _field_is_covered_by_defaults(field: str, spec: StrategySpec) -> bool:
    normalized = field.replace("risk.", "").replace("costs.", "").replace("execution.", "").replace("date_range.", "")
    if normalized in {"stop_loss_type", "take_profit_type"}:
        return True
    if normalized == "stop_loss_value":
        return spec.risk.stop_loss_value > 0
    if normalized == "risk_reward_ratio":
        return spec.risk.risk_reward_ratio > 0
    if normalized == "take_profit_value":
        return spec.risk.take_profit_type != "fixed_percent" or (spec.risk.take_profit_value is not None and spec.risk.take_profit_value > 0)
    if normalized == "fees_bps":
        return spec.costs.fees_bps >= 0
    if normalized == "slippage_bps":
        return spec.costs.slippage_bps >= 0
    if normalized in {"start", "end"}:
        return bool(spec.date_range.start and spec.date_range.end)
    if normalized in {"entry_timing", "one_position_at_a_time", "sizing_mode"}:
        return True
    if normalized == "market":
        return bool(spec.asset.market)
    if normalized == "direction":
        return bool(spec.direction)
    return False


def _default_assumption_for_field(field: str, spec: StrategySpec) -> str | None:
    normalized = field.replace("risk.", "").replace("costs.", "").replace("execution.", "").replace("date_range.", "")
    if normalized == "stop_loss_value":
        return f"Defaulted stop loss to {spec.risk.stop_loss_value}% for the MVP risk model."
    if normalized == "risk_reward_ratio":
        return f"Defaulted risk/reward ratio to {spec.risk.risk_reward_ratio}:1."
    if normalized == "fees_bps":
        return f"Defaulted fees to {spec.costs.fees_bps} bps."
    if normalized == "slippage_bps":
        return f"Defaulted slippage to {spec.costs.slippage_bps} bps."
    if normalized in {"start", "end"}:
        return f"Defaulted date range to {spec.date_range.start} through {spec.date_range.end}."
    if normalized == "market":
        return f"Defaulted market to {spec.asset.market} for {spec.asset.symbol}."
    if normalized == "direction":
        return f"Defaulted direction to {spec.direction}."
    return None


def _match_symbol(text: str) -> str | None:
    for asset in ASSETS:
        if asset.symbol in text or asset.provider_symbol.replace("/", "") in text:
            return asset.symbol
    return None


def _match_timeframe(text: str) -> str | None:
    match = re.search(r"\b(5M|15M|1H|4H|1D)\b", text)
    return match.group(1).lower() if match else None


def _op_token_to_name(token: str) -> str:
    return {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}[token]


def _build_name(prompt: str, symbol: str, timeframe: str) -> str:
    if "RSI" in prompt.upper():
        return f"RSI Mean Reversion {symbol} {timeframe.upper()}"
    if re.search(r"ema|sma", prompt, re.I):
        return f"Trend Crossover {symbol} {timeframe.upper()}"
    return f"Structured Strategy {symbol} {timeframe.upper()}"
