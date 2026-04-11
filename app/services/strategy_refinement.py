"""Safe STRATIX Pro refinement planning and optimization."""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.refinement import ComparisonMetric, OptimizationVariable, OptimizationWeights, RefinementPlan, StrategyComparison
from app.schemas.strategy import StrategySpec
from app.services.backtest_engine import run_backtest
from app.services.market_data import load_bars
from app.services.strategy_compiler import compile_strategy
from app.services.strategy_validator import validate_strategy_spec


logger = get_logger(__name__)


@dataclass(slots=True)
class CandidateEvaluation:
    params: dict[str, float]
    spec: StrategySpec
    summary: dict
    score: float
    changed: bool


class _AIPlanVariable(BaseModel):
    key: str
    min_value: float
    max_value: float
    step: float = Field(default=1.0, gt=0)


class _AIPlanResponse(BaseModel):
    objective: str = "Improve risk-adjusted returns while limiting overfit."
    objective_weights: OptimizationWeights = Field(default_factory=OptimizationWeights)
    variables: list[_AIPlanVariable] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


def build_refinement_plan(*, raw_prompt: str, spec: StrategySpec, baseline_summary: dict, max_evaluations: int) -> RefinementPlan:
    variables = _extract_variables(spec)
    if not variables:
        variables = [
            OptimizationVariable(
                key="risk.stop_loss_value",
                label="Stop loss (%)",
                current_value=float(spec.risk.stop_loss_value),
                min_value=0.5,
                max_value=5.0,
                step=0.25,
            ),
            OptimizationVariable(
                key="risk.risk_reward_ratio",
                label="Risk/reward ratio",
                current_value=float(spec.risk.risk_reward_ratio),
                min_value=1.0,
                max_value=4.0,
                step=0.25,
            ),
        ]

    objective_weights = OptimizationWeights(
        net_profit=0.3,
        win_rate=0.3 if baseline_summary.get("win_rate", 0.0) < 50 else 0.2,
        drawdown=0.2,
        sharpe=0.15,
        overfitting_penalty=0.05 if baseline_summary.get("trade_count", 0) >= 12 else 0.15,
    )
    objective = "Raise net profitability and win rate while controlling drawdown, Sharpe decay, and overfitting risk."
    constraints = [
        "Keep all candidate specs inside the validated StrategySpec schema.",
        "Preserve the asset, market, direction, and date range from the baseline strategy.",
        "Reject threshold combinations that invert the intended long/short logic.",
        "Use the baseline run's fees and slippage on every candidate evaluation.",
    ]
    source = "heuristic"

    ai_plan = _guidance_from_openai(raw_prompt, spec, baseline_summary, variables)
    if ai_plan is not None:
        source = "openai"
        objective = ai_plan.objective or objective
        objective_weights = _normalize_weights(ai_plan.objective_weights)
        variables = _merge_ai_variables(ai_plan.variables, variables)
        constraints = list(dict.fromkeys([*constraints, *ai_plan.constraints]))
    else:
        objective_weights = _normalize_weights(objective_weights)

    seed = _seed_from_prompt(raw_prompt)
    return RefinementPlan(
        objective=objective,
        objective_weights=objective_weights,
        variables=variables,
        constraints=constraints,
        algorithm="ga_cuckoo_hybrid",
        seed=seed,
        max_evaluations=max_evaluations,
        source=source,
    )


def optimize_strategy(*, spec: StrategySpec, run_config: dict, plan: RefinementPlan) -> tuple[StrategySpec, dict]:
    working_frame = load_bars(run_config["asset_symbol"], run_config["timeframe"], run_config["date_start"], run_config["date_end"])
    rng = random.Random(plan.seed)
    evaluation_cache: dict[str, CandidateEvaluation] = {}
    baseline_params = {variable.key: float(variable.current_value) for variable in plan.variables}
    baseline = _evaluate_candidate(spec, baseline_params, plan, run_config, working_frame, evaluation_cache)

    population_size = min(max(8, len(plan.variables) * 3), 12)
    population = [baseline_params]
    while len(population) < population_size:
        population.append({variable.key: _sample_value(variable, rng) for variable in plan.variables})

    generations = max(2, plan.max_evaluations // max(population_size, 1) // 2)
    for _ in range(generations):
        scored = sorted(
            (_evaluate_candidate(spec, params, plan, run_config, working_frame, evaluation_cache) for params in population),
            key=lambda item: item.score,
            reverse=True,
        )
        elites = scored[: max(2, population_size // 3)]
        population = [elite.params for elite in elites]
        while len(population) < population_size:
            left, right = rng.sample(elites, 2)
            child = {}
            for variable in plan.variables:
                current = left.params[variable.key] if rng.random() < 0.5 else right.params[variable.key]
                if rng.random() < 0.35:
                    current += rng.uniform(-1, 1) * (variable.max_value - variable.min_value) * 0.2
                child[variable.key] = _quantize_value(current, variable)
            population.append(child)

    ranked = sorted(evaluation_cache.values(), key=lambda item: item.score, reverse=True)
    nests = ranked[: min(3, len(ranked))]
    for _ in range(max(plan.max_evaluations - len(evaluation_cache), 0)):
        base = rng.choice(nests)
        candidate = {}
        for variable in plan.variables:
            span = variable.max_value - variable.min_value
            jump = min((rng.paretovariate(1.5) - 1.0) * 0.08, 0.5)
            direction = -1 if rng.random() < 0.5 else 1
            candidate[variable.key] = _quantize_value(base.params[variable.key] + direction * span * jump, variable)
        evaluation = _evaluate_candidate(spec, candidate, plan, run_config, working_frame, evaluation_cache)
        if evaluation.score > nests[-1].score:
            nests = sorted([*nests, evaluation], key=lambda item: item.score, reverse=True)[: len(nests)]

    best = _choose_best_candidate(sorted(evaluation_cache.values(), key=lambda item: item.score, reverse=True), baseline)
    optimized_spec = best.spec.model_copy(deep=True)
    optimized_spec.name = f"{spec.name} Refined"
    optimized_spec.assumptions = list(
        dict.fromkeys(
            [
                *optimized_spec.assumptions,
                f"Refined with STRATIX Pro using a bounded {plan.algorithm} search.",
                f"Evaluated {len(evaluation_cache)} candidate parameter sets with seed {plan.seed}.",
                *_format_change_notes(plan.variables, baseline.params, best.params),
            ]
        )
    )
    recommendation = (
        "Win rate is below 50%, so STRATIX Pro generated a bounded refinement candidate and compared it to the baseline."
        if baseline.summary.get("win_rate", 0.0) < 50
        else "STRATIX Pro refinement completed on request using the same validated strategy constraints."
    )
    if best.score <= baseline.score:
        recommendation = "STRATIX Pro did not find a materially stronger candidate inside the safe search budget. Review the comparison before promoting it."

    comparison = build_run_comparison(baseline.summary, best.summary)
    return optimized_spec, {
        "baseline_summary": baseline.summary,
        "optimized_summary": best.summary,
        "recommendation": recommendation,
        "comparison": comparison,
        "evaluations": len(evaluation_cache),
    }


def build_run_comparison(baseline_summary: dict, candidate_summary: dict) -> StrategyComparison:
    metrics = [
        ("total_pnl", "Total PnL"),
        ("win_rate", "Win Rate"),
        ("net_return_pct", "Net Return"),
        ("max_drawdown_pct", "Max Drawdown"),
        ("profit_factor", "Profit Factor"),
        ("sharpe_ratio", "Sharpe"),
    ]
    return StrategyComparison(
        metrics=[
            ComparisonMetric(
                key=key,
                label=label,
                baseline_value=float(baseline_summary.get(key, 0.0)),
                candidate_value=float(candidate_summary.get(key, 0.0)),
                delta=round(float(candidate_summary.get(key, 0.0)) - float(baseline_summary.get(key, 0.0)), 2),
            )
            for key, label in metrics
        ],
        baseline_summary=baseline_summary,
        candidate_summary=candidate_summary,
    )


def _guidance_from_openai(raw_prompt: str, spec: StrategySpec, baseline_summary: dict, variables: list[OptimizationVariable]) -> _AIPlanResponse | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_request_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
        response = client.responses.parse(
            model=settings.openai_model_primary,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are STRATIX AI's refinement planner. "
                        "Return only structured JSON. "
                        "Choose from the provided numeric optimization variables only. "
                        "Tighten bounds if helpful, but never widen them. "
                        "Do not generate code."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "prompt": raw_prompt,
                            "baseline_summary": baseline_summary,
                            "strategy_spec": spec.model_dump(mode="json"),
                            "allowed_variables": [variable.model_dump() for variable in variables],
                        }
                    ),
                },
            ],
            text_format=_AIPlanResponse,
        )
        return response.output_parsed
    except Exception as exc:
        logger.warning("refinement_planner_openai_failed error=%s", exc, exc_info=(type(exc), exc, exc.__traceback__))
        return None


def _extract_variables(spec: StrategySpec) -> list[OptimizationVariable]:
    variables: list[OptimizationVariable] = [
        OptimizationVariable(
            key="risk.stop_loss_value",
            label="Stop loss (%)",
            current_value=float(spec.risk.stop_loss_value),
            min_value=max(0.5, round(spec.risk.stop_loss_value * 0.5, 2)),
            max_value=min(10.0, round(spec.risk.stop_loss_value * 1.75, 2)),
            step=0.25,
        ),
        OptimizationVariable(
            key="risk.risk_reward_ratio",
            label="Risk/reward ratio",
            current_value=float(spec.risk.risk_reward_ratio),
            min_value=1.0,
            max_value=min(5.0, max(2.0, round(spec.risk.risk_reward_ratio * 1.75, 2))),
            step=0.25,
        ),
    ]

    if spec.entry_rule and spec.entry_rule.right and spec.entry_rule.right.value is not None:
        variables.append(
            OptimizationVariable(
                key="entry_rule.right.value",
                label="Entry threshold",
                current_value=float(spec.entry_rule.right.value),
                min_value=_threshold_min(spec, spec.entry_rule.left.indicator_ref if spec.entry_rule.left else None, float(spec.entry_rule.right.value)),
                max_value=_threshold_max(spec, spec.entry_rule.left.indicator_ref if spec.entry_rule.left else None, float(spec.entry_rule.right.value)),
                step=1.0,
            )
        )
    if spec.exit_rule and spec.exit_rule.right and spec.exit_rule.right.value is not None:
        variables.append(
            OptimizationVariable(
                key="exit_rule.right.value",
                label="Exit threshold",
                current_value=float(spec.exit_rule.right.value),
                min_value=_threshold_min(spec, spec.exit_rule.left.indicator_ref if spec.exit_rule.left else None, float(spec.exit_rule.right.value)),
                max_value=_threshold_max(spec, spec.exit_rule.left.indicator_ref if spec.exit_rule.left else None, float(spec.exit_rule.right.value)),
                step=1.0,
            )
        )

    for indicator in spec.indicators:
        if indicator.length is not None:
            variables.append(
                OptimizationVariable(
                    key=f"indicators.{indicator.id}.length",
                    label=f"{indicator.type} length",
                    current_value=float(indicator.length),
                    min_value=max(2.0, float(indicator.length - 10)),
                    max_value=min(120.0, float(indicator.length + 20)),
                    step=1.0,
                )
            )

    return variables[:6]


def _threshold_min(spec: StrategySpec, indicator_ref: str | None, current: float) -> float:
    indicator_type = _indicator_type(spec, indicator_ref)
    if indicator_type == "RSI":
        return 5.0
    return round(max(0.0, current * 0.5), 2)


def _threshold_max(spec: StrategySpec, indicator_ref: str | None, current: float) -> float:
    indicator_type = _indicator_type(spec, indicator_ref)
    if indicator_type == "RSI":
        return 95.0
    return round(max(current + 1, current * 1.5), 2)


def _indicator_type(spec: StrategySpec, indicator_ref: str | None) -> str | None:
    if not indicator_ref:
        return None
    for indicator in spec.indicators:
        if indicator.id == indicator_ref:
            return indicator.type
    return None


def _normalize_weights(weights: OptimizationWeights) -> OptimizationWeights:
    values = {
        "net_profit": max(weights.net_profit, 0.0),
        "win_rate": max(weights.win_rate, 0.0),
        "drawdown": max(weights.drawdown, 0.0),
        "sharpe": max(weights.sharpe, 0.0),
        "overfitting_penalty": max(weights.overfitting_penalty, 0.0),
    }
    total = sum(values.values()) or 1.0
    return OptimizationWeights(**{key: round(value / total, 4) for key, value in values.items()})


def _merge_ai_variables(ai_variables: list[_AIPlanVariable], defaults: list[OptimizationVariable]) -> list[OptimizationVariable]:
    default_map = {variable.key: variable for variable in defaults}
    merged: list[OptimizationVariable] = []
    for ai_variable in ai_variables:
        baseline = default_map.get(ai_variable.key)
        if baseline is None:
            continue
        merged.append(
            OptimizationVariable(
                key=baseline.key,
                label=baseline.label,
                current_value=baseline.current_value,
                min_value=max(baseline.min_value, min(ai_variable.min_value, ai_variable.max_value)),
                max_value=min(baseline.max_value, max(ai_variable.min_value, ai_variable.max_value)),
                step=max(baseline.step, ai_variable.step),
            )
        )
    return merged or defaults


def _seed_from_prompt(raw_prompt: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(raw_prompt[:120])) % 1_000_003


def _sample_value(variable: OptimizationVariable, rng: random.Random) -> float:
    span = variable.max_value - variable.min_value
    raw = variable.min_value + rng.random() * span
    return _quantize_value(raw, variable)


def _quantize_value(raw: float, variable: OptimizationVariable) -> float:
    bounded = min(variable.max_value, max(variable.min_value, raw))
    steps = round((bounded - variable.min_value) / variable.step)
    quantized = variable.min_value + steps * variable.step
    decimals = _step_precision(variable.step)
    return round(min(variable.max_value, max(variable.min_value, quantized)), decimals)


def _step_precision(step: float) -> int:
    text = f"{step:.8f}".rstrip("0")
    return len(text.split(".", 1)[1]) if "." in text else 0


def _evaluate_candidate(
    base_spec: StrategySpec,
    params: dict[str, float],
    plan: RefinementPlan,
    run_config: dict,
    frame,
    cache: dict[str, CandidateEvaluation],
) -> CandidateEvaluation:
    cache_key = json.dumps(params, sort_keys=True)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    candidate_spec = base_spec.model_copy(deep=True)
    for variable in plan.variables:
        _assign_value(candidate_spec, variable.key, params[variable.key])
    candidate_spec.costs.fees_bps = float(run_config["fees_bps"])
    candidate_spec.costs.slippage_bps = float(run_config["slippage_bps"])
    candidate_spec.missing_fields = []
    validation = validate_strategy_spec(candidate_spec)
    if not validation.is_valid or not _passes_strategy_constraints(candidate_spec):
        evaluation = CandidateEvaluation(params=params, spec=candidate_spec, summary={}, score=-1_000_000.0, changed=_params_changed(plan.variables, params))
        cache[cache_key] = evaluation
        return evaluation

    compiled = compile_strategy(candidate_spec)
    compiled.costs["fees_bps"] = float(run_config["fees_bps"])
    compiled.costs["slippage_bps"] = float(run_config["slippage_bps"])
    result = run_backtest(compiled, frame, float(run_config["initial_capital"]))
    summary = result["summary"]
    score = _score_summary(summary, plan.objective_weights)
    evaluation = CandidateEvaluation(params=params, spec=candidate_spec, summary=summary, score=score, changed=_params_changed(plan.variables, params))
    cache[cache_key] = evaluation
    return evaluation


def _assign_value(spec: StrategySpec, key: str, value: float) -> None:
    if key == "risk.stop_loss_value":
        spec.risk.stop_loss_value = value
        return
    if key == "risk.risk_reward_ratio":
        spec.risk.risk_reward_ratio = value
        return
    if key == "entry_rule.right.value" and spec.entry_rule and spec.entry_rule.right:
        spec.entry_rule.right.value = value
        return
    if key == "exit_rule.right.value" and spec.exit_rule and spec.exit_rule.right:
        spec.exit_rule.right.value = value
        return
    if key.startswith("indicators.") and key.endswith(".length"):
        identifier = key.split(".", 2)[1]
        for indicator in spec.indicators:
            if indicator.id == identifier:
                indicator.length = int(round(value))
                return


def _score_summary(summary: dict, weights: OptimizationWeights) -> float:
    net_profit_score = max(-1.0, min(float(summary.get("net_return_pct", 0.0)) / 100, 2.0))
    win_rate_score = float(summary.get("win_rate", 0.0)) / 100
    drawdown_penalty = float(summary.get("max_drawdown_pct", 0.0)) / 100
    sharpe_score = max(-1.0, min(float(summary.get("sharpe_ratio", 0.0)) / 3, 2.0))
    overfit_penalty = _overfitting_penalty(summary)
    return (
        weights.net_profit * net_profit_score
        + weights.win_rate * win_rate_score
        - weights.drawdown * drawdown_penalty
        + weights.sharpe * sharpe_score
        - weights.overfitting_penalty * overfit_penalty
    )


def _overfitting_penalty(summary: dict) -> float:
    trade_count = float(summary.get("trade_count", 0.0))
    profit_factor = float(summary.get("profit_factor", 0.0))
    low_sample_penalty = max(0.0, (10.0 - trade_count) / 10.0)
    extreme_profit_factor_penalty = max(0.0, (profit_factor - 4.0) / 4.0)
    return low_sample_penalty + extreme_profit_factor_penalty


def _passes_strategy_constraints(spec: StrategySpec) -> bool:
    if spec.entry_rule and spec.exit_rule and spec.entry_rule.right and spec.exit_rule.right:
        if spec.entry_rule.right.value is not None and spec.exit_rule.right.value is not None:
            if spec.direction == "long" and spec.entry_rule.right.value >= spec.exit_rule.right.value:
                return False
            if spec.direction == "short" and spec.entry_rule.right.value <= spec.exit_rule.right.value:
                return False
    return True


def _params_changed(variables: list[OptimizationVariable], params: dict[str, float]) -> bool:
    for variable in variables:
        if abs(params[variable.key] - variable.current_value) > max(variable.step / 2, 1e-9):
            return True
    return False


def _choose_best_candidate(ranked: list[CandidateEvaluation], baseline: CandidateEvaluation) -> CandidateEvaluation:
    for candidate in ranked:
        if candidate.changed and candidate.summary:
            return candidate
    return baseline


def _format_change_notes(variables: list[OptimizationVariable], baseline: dict[str, float], optimized: dict[str, float]) -> list[str]:
    notes: list[str] = []
    for variable in variables:
        previous = baseline[variable.key]
        current = optimized[variable.key]
        if math.isclose(previous, current, abs_tol=max(variable.step / 2, 1e-9)):
            continue
        notes.append(f"{variable.label} moved from {previous} to {current}.")
    return notes
