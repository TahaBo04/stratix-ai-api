"""Strategy routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import get_current_user
from app.repositories.strategies import (
    create_strategy,
    create_strategy_version,
    get_latest_version,
    get_strategy,
    next_version_number,
    update_strategy,
)
from app.schemas.strategy import (
    CreateStrategyRequest,
    InterpretStrategyRequest,
    InterpretStrategyResponse,
    StrategyResponse,
    StrategySpec,
    StrategyVersionResponse,
    UpdateStrategyRequest,
)
from app.services.ai_parser import PROMPT_VERSION, interpret_prompt
from app.services.strategy_codegen import generate_python_strategy
from app.services.strategy_compiler import COMPILER_VERSION
from app.services.strategy_validator import validate_strategy_spec


router = APIRouter(prefix="/v1/strategies", tags=["strategies"])


@router.post("/interpret", response_model=InterpretStrategyResponse)
def interpret_strategy(payload: InterpretStrategyRequest) -> InterpretStrategyResponse:
    return interpret_prompt(payload.prompt)


@router.post("", response_model=StrategyResponse)
def create_strategy_route(payload: CreateStrategyRequest, current_user: dict = Depends(get_current_user)) -> StrategyResponse:
    validation = validate_strategy_spec(payload.spec)
    payload.spec.status = "valid" if validation.is_valid else "needs_clarification"
    payload.spec.missing_fields = validation.missing_fields
    strategy = create_strategy(
        user_id=current_user["id"],
        name=payload.spec.name,
        raw_prompt=payload.raw_prompt,
        status=payload.spec.status,
        service_tier=payload.service_tier,
    )
    version = create_strategy_version(
        strategy_id=strategy["id"],
        version_no=1,
        spec=payload.spec.model_dump(mode="json"),
        compiler_version=COMPILER_VERSION,
        prompt_version=PROMPT_VERSION,
        generated_python=generate_python_strategy(payload.spec),
        assumptions=payload.spec.assumptions,
    )
    return _serialize_strategy(strategy, version)


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy_route(strategy_id: str, current_user: dict = Depends(get_current_user)) -> StrategyResponse:
    strategy = get_strategy(strategy_id)
    if strategy is None or strategy["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Strategy not found")
    version = get_latest_version(strategy_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Strategy version not found")
    return _serialize_strategy(strategy, version)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
def update_strategy_route(strategy_id: str, payload: UpdateStrategyRequest, current_user: dict = Depends(get_current_user)) -> StrategyResponse:
    strategy = get_strategy(strategy_id)
    if strategy is None or strategy["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Strategy not found")
    raw_prompt = payload.raw_prompt or strategy["raw_prompt"]
    spec = payload.spec
    if spec is None:
        version = get_latest_version(strategy_id)
        if version is None:
            raise HTTPException(status_code=404, detail="Strategy version not found")
        spec = StrategySpec.model_validate(version["spec_json"])
    validation = validate_strategy_spec(spec)
    spec.status = "valid" if validation.is_valid else "needs_clarification"
    spec.missing_fields = validation.missing_fields
    updated = update_strategy(
        strategy_id,
        name=spec.name,
        raw_prompt=raw_prompt,
        service_tier=payload.service_tier or strategy.get("service_tier", "simple"),
        status=spec.status,
    )
    assert updated is not None
    version = create_strategy_version(
        strategy_id=strategy_id,
        version_no=next_version_number(strategy_id),
        spec=spec.model_dump(mode="json"),
        compiler_version=COMPILER_VERSION,
        prompt_version=PROMPT_VERSION,
        generated_python=generate_python_strategy(spec),
        assumptions=spec.assumptions,
    )
    return _serialize_strategy(updated, version)


@router.post("/{strategy_id}/clone", response_model=StrategyResponse)
def clone_strategy(strategy_id: str, current_user: dict = Depends(get_current_user)) -> StrategyResponse:
    strategy = get_strategy(strategy_id)
    if strategy is None or strategy["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Strategy not found")
    version = get_latest_version(strategy_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Strategy version not found")
    cloned_strategy = create_strategy(
        user_id=current_user["id"],
        name=f"{strategy['name']} Copy",
        raw_prompt=strategy["raw_prompt"],
        service_tier=strategy.get("service_tier", "simple"),
        status=strategy["status"],
    )
    cloned_version = create_strategy_version(
        strategy_id=cloned_strategy["id"],
        version_no=1,
        spec=version["spec_json"],
        compiler_version=version["compiler_version"],
        prompt_version=version["prompt_version"],
        generated_python=version["generated_python"],
        assumptions=version["assumptions_json"],
    )
    return _serialize_strategy(cloned_strategy, cloned_version)


def _serialize_strategy(strategy: dict, version: dict) -> StrategyResponse:
    version_response = StrategyVersionResponse(
        id=version["id"],
        version_no=version["version_no"],
        spec=StrategySpec.model_validate(version["spec_json"]),
        compiler_version=version["compiler_version"],
        prompt_version=version["prompt_version"],
        generated_python=version["generated_python"],
        assumptions=version["assumptions_json"],
        created_at=datetime.fromisoformat(version["created_at"]),
    )
    return StrategyResponse(
        id=strategy["id"],
        user_id=strategy["user_id"],
        name=strategy["name"],
        raw_prompt=strategy["raw_prompt"],
        service_tier=strategy.get("service_tier", "simple"),
        status=strategy["status"],
        created_at=datetime.fromisoformat(strategy["created_at"]),
        latest_version=version_response,
    )
