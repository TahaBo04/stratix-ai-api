from app.schemas.strategy import AssetSpec, ConditionNode, CostSpec, DateRange, ExecutionSpec, IndicatorSpec, Operand, RiskSpec, StrategySpec
from app.services.ai_parser import _finalize_spec, interpret_prompt


def test_rsi_prompt_parses_into_strategy_spec():
    response = interpret_prompt("Buy when RSI < 30 and sell when RSI > 70 on BTCUSDT 1H with 1:2 risk reward")
    assert response.spec.asset.symbol == "BTCUSDT"
    assert response.spec.timeframe == "1h"
    assert response.spec.entry_rule is not None
    assert response.spec.exit_rule is not None


def test_finalize_spec_clears_defaultable_missing_fields():
    spec = StrategySpec(
        status="needs_clarification",
        name="RSI Oversold Overbought BTCUSDT 1H",
        asset=AssetSpec(asset_class="crypto", symbol="BTCUSDT", market="binance"),
        timeframe="1h",
        date_range=DateRange(),
        direction="long",
        indicators=[IndicatorSpec(id="rsi_14", type="RSI", source="close", length=14)],
        entry_rule=ConditionNode(operator="lt", left=Operand(indicator_ref="rsi_14"), right=Operand(value=30)),
        exit_rule=ConditionNode(operator="gt", left=Operand(indicator_ref="rsi_14"), right=Operand(value=70)),
        risk=RiskSpec(stop_loss_value=2.0, risk_reward_ratio=2.0),
        execution=ExecutionSpec(),
        costs=CostSpec(),
        missing_fields=["stop_loss_value"],
        assumptions=[],
    )

    finalized = _finalize_spec(spec)
    assert finalized.missing_fields == []
    assert any("Defaulted stop loss" in assumption for assumption in finalized.assumptions)
