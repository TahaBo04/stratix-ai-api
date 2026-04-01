from app.schemas.strategy import (
    AssetSpec,
    ConditionNode,
    CostSpec,
    DateRange,
    ExecutionSpec,
    IndicatorSpec,
    Operand,
    RiskSpec,
    StrategySpec,
)
from app.services.market_data import load_bars
from app.services.strategy_compiler import compile_strategy
from app.services.backtest_engine import run_backtest


def test_backtest_engine_returns_summary():
    spec = StrategySpec(
        status="valid",
        name="RSI demo",
        asset=AssetSpec(asset_class="crypto", symbol="BTCUSDT", market="binance"),
        timeframe="1h",
        date_range=DateRange(start="2024-01-01", end="2024-01-15"),
        direction="long",
        indicators=[IndicatorSpec(id="rsi_14", type="RSI", length=14)],
        entry_rule=ConditionNode(operator="lt", left=Operand(indicator_ref="rsi_14"), right=Operand(value=30)),
        exit_rule=ConditionNode(operator="gt", left=Operand(indicator_ref="rsi_14"), right=Operand(value=70)),
        risk=RiskSpec(stop_loss_value=2.0, risk_reward_ratio=2.0),
        execution=ExecutionSpec(),
        costs=CostSpec(),
        missing_fields=[],
        assumptions=[],
    )
    compiled = compile_strategy(spec)
    frame = load_bars("BTCUSDT", "1h", "2024-01-01", "2024-01-15")
    result = run_backtest(compiled, frame, 10_000)
    assert "summary" in result
    assert "price_series" in result
