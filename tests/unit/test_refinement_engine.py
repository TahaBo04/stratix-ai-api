from app.schemas.strategy import AssetSpec, ConditionNode, CostSpec, DateRange, ExecutionSpec, IndicatorSpec, Operand, RiskSpec, StrategySpec
from app.services.strategy_refinement import build_refinement_plan, optimize_strategy


def test_refinement_engine_returns_a_comparison_payload():
    spec = StrategySpec(
        status="valid",
        name="RSI Recovery Candidate",
        asset=AssetSpec(asset_class="crypto", symbol="BTCUSDT", market="binance"),
        timeframe="1h",
        date_range=DateRange(start="2024-01-01", end="2024-01-15"),
        direction="long",
        indicators=[IndicatorSpec(id="rsi_14", type="RSI", source="close", length=14)],
        entry_rule=ConditionNode(operator="lt", left=Operand(indicator_ref="rsi_14"), right=Operand(value=30)),
        exit_rule=ConditionNode(operator="gt", left=Operand(indicator_ref="rsi_14"), right=Operand(value=70)),
        risk=RiskSpec(stop_loss_value=2.0, risk_reward_ratio=2.0),
        execution=ExecutionSpec(),
        costs=CostSpec(),
        missing_fields=[],
        assumptions=[],
    )
    run_config = {
        "asset_symbol": "BTCUSDT",
        "timeframe": "1h",
        "date_start": "2024-01-01",
        "date_end": "2024-01-15",
        "initial_capital": 10_000.0,
        "fees_bps": 10.0,
        "slippage_bps": 5.0,
        "summary_json": {"win_rate": 22.5, "trade_count": 18},
    }

    plan = build_refinement_plan(
        raw_prompt="Buy when RSI < 30 and sell when RSI > 70 on BTCUSDT 1H with 1:2 risk reward",
        spec=spec,
        baseline_summary=run_config["summary_json"],
        max_evaluations=20,
    )
    optimized_spec, optimization = optimize_strategy(spec=spec, run_config=run_config, plan=plan)

    assert plan.variables
    assert optimized_spec.name.endswith("Refined")
    assert optimization["comparison"].metrics
    assert "candidate_summary" in optimization["comparison"].model_dump()

