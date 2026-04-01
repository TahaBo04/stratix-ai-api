"""Display-only Python code generation from validated strategy specs."""
from __future__ import annotations

from textwrap import indent

from app.schemas.strategy import StrategySpec


CODEGEN_VERSION = "0.1.0"


def generate_python_strategy(spec: StrategySpec) -> str:
    indicators = "\n".join(_render_indicator(indicator) for indicator in spec.indicators) or "# No indicators configured"
    entry = _rule_to_python(spec.entry_rule) if spec.entry_rule else "False"
    exit_rule = _rule_to_python(spec.exit_rule) if spec.exit_rule else "False"
    return f'''"""Generated from a validated STRATIX AI StrategySpec."""
from dataclasses import dataclass


@dataclass
class StrategyConfig:
    symbol: str = "{spec.asset.symbol}"
    timeframe: str = "{spec.timeframe}"
    direction: str = "{spec.direction}"


class GeneratedStrategy:
    name = {spec.name!r}
    config = StrategyConfig()

    def build_indicators(self):
{indent(indicators, ' ' * 8)}

    def entry_signal(self):
        return {entry}

    def exit_signal(self):
        return {exit_rule}
'''


def _render_indicator(indicator) -> str:
    attrs = indicator.model_dump(exclude_none=True)
    args = ", ".join(f"{key}={value!r}" for key, value in attrs.items())
    return f"self.{indicator.id} = ({args})"


def _rule_to_python(node) -> str:
    if node is None:
        return "False"
    if node.operator == "and":
        return " and ".join(_rule_to_python(child) for child in node.conditions)
    if node.operator == "or":
        return " or ".join(_rule_to_python(child) for child in node.conditions)
    op_map = {
        "lt": "<",
        "lte": "<=",
        "gt": ">",
        "gte": ">=",
        "crosses_above": "crosses_above",
        "crosses_below": "crosses_below",
    }
    left = _operand_to_python(node.left)
    right = _operand_to_python(node.right)
    return f"{left} {op_map.get(node.operator, node.operator)} {right}"


def _operand_to_python(operand) -> str:
    if operand.indicator_ref:
        return f"self.{operand.indicator_ref}"
    return repr(operand.value)
