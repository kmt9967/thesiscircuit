from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_discloses_disabled_orders() -> None:
    assert client.get("/health").json() == {"status": "ok", "mode": "paper", "orders": "disabled"}


def test_no_order_route_exists() -> None:
    paths = set(app.openapi()["paths"])
    assert not any("order" in path.lower() or "trade" in path.lower() for path in paths)


def test_safe_thesis_is_research_only() -> None:
    response = client.post(
        "/evaluate",
        json={
            "symbol": "SPY",
            "strategy": "defined-risk-put-spread",
            "max_loss_usd": 250,
            "days_to_expiry": 21,
            "confidence": 0.8,
            "data_age_seconds": 15,
        },
    )
    assert response.status_code == 200
    assert response.json()["approved_for_research"] is True
    assert response.json()["order_submission_enabled"] is False

