"""Tests for POST /api/v1/config/predictor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from pitwall.api.dependencies import get_engine_loop
from pitwall.api.main import create_app


def _make_client(predictor_name: str = "scipy") -> TestClient:
    app = create_app()
    mock_loop = MagicMock()
    mock_loop.predictor_name = predictor_name
    app.dependency_overrides[get_engine_loop] = lambda: mock_loop
    return TestClient(app)


# ---------------------------------------------------------------------------
# scipy — always succeeds
# ---------------------------------------------------------------------------


def test_set_predictor_scipy_returns_200() -> None:
    client = _make_client()
    r = client.post("/api/v1/config/predictor", json={"predictor": "scipy"})
    assert r.status_code == 200
    assert r.json()["active_predictor"] == "scipy"


def test_set_predictor_scipy_calls_set_predictor_on_engine_loop() -> None:
    app = create_app()
    mock_loop = MagicMock()
    app.dependency_overrides[get_engine_loop] = lambda: mock_loop

    with TestClient(app) as client:
        client.post("/api/v1/config/predictor", json={"predictor": "scipy"})

    mock_loop.set_predictor.assert_called_once()
    args = mock_loop.set_predictor.call_args[0]
    assert args[1] == "scipy"


def test_set_predictor_scipy_response_shape() -> None:
    client = _make_client()
    body = client.post("/api/v1/config/predictor", json={"predictor": "scipy"}).json()
    assert set(body) == {"active_predictor"}


# ---------------------------------------------------------------------------
# xgboost — 409 when model file missing (default state in V1)
# ---------------------------------------------------------------------------


def test_set_predictor_xgboost_409_when_model_missing() -> None:
    client = _make_client()
    # models/xgb_pace_v1.json does not exist in the test environment
    r = client.post("/api/v1/config/predictor", json={"predictor": "xgboost"})
    assert r.status_code == 409
    assert "xgb_pace_v1.json" in r.json()["detail"] or "train-xgb" in r.json()["detail"]


def test_set_predictor_xgboost_409_detail_mentions_make_train_xgb() -> None:
    client = _make_client()
    r = client.post("/api/v1/config/predictor", json={"predictor": "xgboost"})
    assert r.status_code == 409
    assert "train-xgb" in r.json()["detail"]


def test_set_predictor_xgboost_200_when_model_exists_but_class_missing(
    tmp_path: Path,
) -> None:
    """When the model JSON exists but XGBoostPredictor isn't implemented yet → 409."""
    model_file = tmp_path / "xgb_pace_v1.json"
    model_file.write_text("{}")

    app = create_app()
    mock_loop = MagicMock()
    app.dependency_overrides[get_engine_loop] = lambda: mock_loop

    with patch("pitwall.core.config.get_settings") as mock_settings:
        mock_settings.return_value.xgb_model_path = str(model_file)
        mock_settings.return_value.pace_predictor = "scipy"
        with TestClient(app) as client:
            r = client.post("/api/v1/config/predictor", json={"predictor": "xgboost"})

    # XGBoostPredictor doesn't exist yet → 409 from ImportError branch
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Invalid request body
# ---------------------------------------------------------------------------


def test_set_predictor_invalid_name_returns_422() -> None:
    client = _make_client()
    r = client.post("/api/v1/config/predictor", json={"predictor": "lstm"})
    assert r.status_code == 422


def test_set_predictor_missing_body_returns_422() -> None:
    client = _make_client()
    r = client.post("/api/v1/config/predictor", json={})
    assert r.status_code == 422
