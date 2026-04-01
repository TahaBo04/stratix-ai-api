"""Internal deterministic strategy domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CompiledOperand:
    kind: str
    value: Any


@dataclass(slots=True)
class CompiledRule:
    operator: str
    left: CompiledOperand | None = None
    right: CompiledOperand | None = None
    conditions: list["CompiledRule"] = field(default_factory=list)


@dataclass(slots=True)
class CompiledIndicator:
    identifier: str
    indicator_type: str
    params: dict[str, Any]


@dataclass(slots=True)
class CompiledStrategy:
    name: str
    asset_symbol: str
    asset_class: str
    market: str
    timeframe: str
    direction: str
    indicators: list[CompiledIndicator]
    entry_rule: CompiledRule
    exit_rule: CompiledRule | None
    risk: dict[str, Any]
    execution: dict[str, Any]
    costs: dict[str, Any]
    date_range: dict[str, str]
