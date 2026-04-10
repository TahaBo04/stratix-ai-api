import pandas as pd

from app.models import CompiledOperand, CompiledRule, CompiledStrategy
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


def test_short_position_realizes_positive_pnl_when_price_falls():
    frame = pd.DataFrame(
        [
            {"timestamp": pd.Timestamp("2024-01-01T00:00:00Z"), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            {"timestamp": pd.Timestamp("2024-01-01T01:00:00Z"), "open": 100.0, "high": 100.0, "low": 99.0, "close": 100.0},
            {"timestamp": pd.Timestamp("2024-01-01T02:00:00Z"), "open": 100.0, "high": 100.0, "low": 90.0, "close": 90.0},
        ]
    )
    strategy = CompiledStrategy(
        name="Short PnL Regression",
        asset_symbol="BTCUSDT",
        asset_class="crypto",
        market="binance",
        timeframe="1h",
        direction="short",
        indicators=[],
        entry_rule=CompiledRule(
            operator="gt",
            left=CompiledOperand(kind="value", value=1.0),
            right=CompiledOperand(kind="value", value=0.0),
        ),
        exit_rule=None,
        risk={
            "stop_loss_type": "percent",
            "stop_loss_value": 50.0,
            "risk_reward_ratio": 2.0,
            "take_profit_type": "fixed_percent",
            "take_profit_value": 10.0,
        },
        execution={"entry_timing": "next_bar_open", "one_position_at_a_time": True, "sizing_mode": "full_notional"},
        costs={"fees_bps": 0.0, "slippage_bps": 0.0},
        date_range={"start": "2024-01-01", "end": "2024-01-02"},
    )

    result = run_backtest(strategy, frame, 10_000)

    assert result["trades"][0]["exit_reason"] == "take_profit"
    assert result["trades"][0]["pnl"] == 1_000.0
    assert result["summary"]["total_pnl"] == 1_000.0
