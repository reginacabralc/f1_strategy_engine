"""Demo mode flag plumbing through /api/v1/replay/start."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pitwall.api.main import create_app


def test_replay_start_accepts_demo_mode_flag() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/replay/start",
            json={"session_id": "bahrain_2024_R", "speed_factor": 10, "demo_mode": True},
        )
        # In-memory event loader returns empty list -> 404, but we only care
        # that the schema accepts demo_mode (no 422 validation error).
        assert response.status_code != 422, response.text


def test_replay_start_demo_mode_defaults_to_false() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/replay/start",
            json={"session_id": "bahrain_2024_R", "speed_factor": 10},
        )
        assert response.status_code != 422, response.text


def test_replay_start_request_schema_has_demo_mode_field() -> None:
    """Schema introspection so the field is discoverable."""
    from pitwall.api.schemas import ReplayStartRequest

    schema = ReplayStartRequest.model_json_schema()
    assert "demo_mode" in schema["properties"]
    assert schema["properties"]["demo_mode"]["type"] == "boolean"
    # Must default to False
    assert schema["properties"]["demo_mode"].get("default") is False
