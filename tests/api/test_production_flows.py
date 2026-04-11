import importlib

from fastapi.testclient import TestClient


def _build_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("BACKTEST_EXECUTION_MODE", "inline")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("VERCEL", raising=False)

    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.main as main_module

    main_module = importlib.reload(main_module)
    return TestClient(main_module.app)


def _register_and_authenticate(client: TestClient) -> dict[str, str]:
    register_response = client.post(
        "/v1/auth/register",
        json={
            "full_name": "Prod Flow User",
            "email": "prod-flow@example.com",
            "password": "strong-password",
        },
    )
    assert register_response.status_code == 200
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_auth_register_and_me_flow(tmp_path, monkeypatch):
    with _build_client(tmp_path, monkeypatch) as client:
        headers = _register_and_authenticate(client)
        me_response = client.get("/v1/me", headers=headers)

        assert me_response.status_code == 200
        assert me_response.json()["email"] == "prod-flow@example.com"
        assert me_response.json()["role"] == "user"


def test_distinct_interpretations_and_backtest_flow(tmp_path, monkeypatch):
    with _build_client(tmp_path, monkeypatch) as client:
        headers = _register_and_authenticate(client)

        prompt_a = "Buy when RSI < 30 and sell when RSI > 70 on BTCUSDT 1H with 1:2 risk reward"
        prompt_b = "Buy when EMA 9 crosses above EMA 21 and exit when EMA 9 crosses below EMA 21 on ETHUSDT 4H"

        interpret_a = client.post("/v1/strategies/interpret", json={"prompt": prompt_a})
        interpret_b = client.post("/v1/strategies/interpret", json={"prompt": prompt_b})

        assert interpret_a.status_code == 200
        assert interpret_b.status_code == 200
        assert interpret_a.json()["prompt_digest"] != interpret_b.json()["prompt_digest"]
        assert interpret_a.json()["spec"]["name"] != interpret_b.json()["spec"]["name"]

        strategy_response = client.post(
            "/v1/strategies",
            headers=headers,
            json={
                "raw_prompt": prompt_a,
                "service_tier": "simple",
                "spec": interpret_a.json()["spec"],
            },
        )
        assert strategy_response.status_code == 200
        strategy_id = strategy_response.json()["id"]

        run_response = client.post(
            f"/v1/strategies/{strategy_id}/backtests",
            headers=headers,
            json={"initial_capital": 10_000, "fees_bps": 10, "slippage_bps": 5},
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["id"]

        result_response = client.get(f"/v1/backtests/{run_id}/results", headers=headers)
        assert result_response.status_code == 200
        assert any(metric["key"] == "sharpe_ratio" for metric in result_response.json()["metrics"])


def test_refinement_workflow_returns_comparison(tmp_path, monkeypatch):
    with _build_client(tmp_path, monkeypatch) as client:
        headers = _register_and_authenticate(client)
        prompt = "Buy when RSI < 30 and sell when RSI > 70 on BTCUSDT 1H with 1:2 risk reward"
        interpret_response = client.post("/v1/strategies/interpret", json={"prompt": prompt})
        assert interpret_response.status_code == 200

        strategy_response = client.post(
            "/v1/strategies",
            headers=headers,
            json={
                "raw_prompt": prompt,
                "service_tier": "simple",
                "spec": interpret_response.json()["spec"],
            },
        )
        assert strategy_response.status_code == 200

        run_response = client.post(
            f"/v1/strategies/{strategy_response.json()['id']}/backtests",
            headers=headers,
            json={"initial_capital": 10_000, "fees_bps": 10, "slippage_bps": 5},
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["id"]

        refinement_response = client.post(
            f"/v1/backtests/{run_id}/refine",
            headers=headers,
            json={"max_evaluations": 20},
        )

        assert refinement_response.status_code == 200
        payload = refinement_response.json()
        assert payload["service_tier"] == "pro"
        assert payload["optimized_run"]["id"] != run_id
        assert any(metric["key"] == "win_rate" for metric in payload["comparison"]["metrics"])
