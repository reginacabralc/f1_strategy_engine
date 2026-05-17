"""Tests for the demo-mode engine extensions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitwall.engine.projection import Compound, PaceContext, PacePrediction


def test_load_scripted_alerts_returns_per_session_dict(tmp_path: Path) -> None:
    from pitwall.engine.demo_mode import load_scripted_alerts

    data = {
        "version": 1,
        "sessions": {
            "bahrain_2024_R": [
                {"lap_number": 9, "attacker_code": "ZHO", "defender_code": "OCO", "source": "test"}
            ]
        },
    }
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps(data))

    alerts = load_scripted_alerts(path)
    assert "bahrain_2024_R" in alerts
    assert len(alerts["bahrain_2024_R"]) == 1
    assert alerts["bahrain_2024_R"][0].lap_number == 9
    assert alerts["bahrain_2024_R"][0].attacker_code == "ZHO"
    assert alerts["bahrain_2024_R"][0].defender_code == "OCO"
    assert alerts["bahrain_2024_R"][0].source == "test"


def test_load_scripted_alerts_missing_file_returns_empty(tmp_path: Path) -> None:
    from pitwall.engine.demo_mode import load_scripted_alerts
    alerts = load_scripted_alerts(tmp_path / "does_not_exist.json")
    assert alerts == {}


def test_load_scripted_alerts_skips_malformed_entries(tmp_path: Path) -> None:
    from pitwall.engine.demo_mode import load_scripted_alerts
    data = {
        "version": 1,
        "sessions": {
            "bahrain_2024_R": [
                {"lap_number": 9, "attacker_code": "ZHO", "defender_code": "OCO", "source": "ok"},
                {"lap_number": "not-a-number", "attacker_code": "X"},  # malformed
                {"missing_lap_field": True},
            ]
        },
    }
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps(data))

    alerts = load_scripted_alerts(path)
    # Only the well-formed entry survives.
    assert len(alerts["bahrain_2024_R"]) == 1
    assert alerts["bahrain_2024_R"][0].attacker_code == "ZHO"


def test_relaxed_thresholds_are_lower_than_production() -> None:
    from pitwall.engine.demo_mode import (
        RELAXED_CONFIDENCE_THRESHOLD,
        RELAXED_SCORE_THRESHOLD,
    )
    from pitwall.engine.undercut import CONFIDENCE_THRESHOLD, SCORE_THRESHOLD

    assert RELAXED_SCORE_THRESHOLD < SCORE_THRESHOLD
    assert RELAXED_CONFIDENCE_THRESHOLD < CONFIDENCE_THRESHOLD
    # Calibrated to demo-data R² range (max ≈ 0.36, so 0.1 lets things fire)
    assert RELAXED_CONFIDENCE_THRESHOLD <= 0.15
    assert RELAXED_SCORE_THRESHOLD <= 0.25


def test_build_scripted_alert_payload_has_required_fields() -> None:
    from pitwall.engine.demo_mode import ScriptedAlert, build_scripted_alert_payload

    scripted = ScriptedAlert(
        lap_number=9,
        attacker_code="ZHO",
        defender_code="OCO",
        source="auto_derived",
    )
    payload = build_scripted_alert_payload(
        scripted=scripted,
        session_id="bahrain_2024_R",
        predictor_name="scipy",
    )
    assert payload["type"] == "alert"
    assert payload["v"] == 1
    body = payload["payload"]
    assert body["alert_type"] == "UNDERCUT_VIABLE"
    assert body["lap_number"] == 9
    assert body["attacker_code"] == "ZHO"
    assert body["defender_code"] == "OCO"
    assert body["session_id"] == "bahrain_2024_R"
    assert body["predictor_used"] == "scipy"
    assert body["demo_source"] == "auto_derived"
    # Legacy aliases preserved (frontend normalizer reads these)
    assert body["attacker"] == "ZHO"
    assert body["defender"] == "OCO"


def test_default_scripted_alerts_path_points_to_data_demo() -> None:
    """Default path matches the data/demo/scripted_alerts.json we committed."""
    from pitwall.engine.demo_mode import DEFAULT_SCRIPTED_ALERTS_PATH
    assert str(DEFAULT_SCRIPTED_ALERTS_PATH).endswith("scripted_alerts.json")
    assert "data/demo" in str(DEFAULT_SCRIPTED_ALERTS_PATH).replace("\\", "/")


def test_real_demo_alerts_file_loads_successfully() -> None:
    """The committed data/demo/scripted_alerts.json must load without errors."""
    from pitwall.engine.demo_mode import DEFAULT_SCRIPTED_ALERTS_PATH, load_scripted_alerts

    alerts = load_scripted_alerts(DEFAULT_SCRIPTED_ALERTS_PATH)
    assert "bahrain_2024_R" in alerts
    assert "monaco_2024_R" in alerts
    assert "hungary_2024_R" in alerts
    # Each session has at least 2 scripted alerts
    for session_id in ("bahrain_2024_R", "monaco_2024_R", "hungary_2024_R"):
        assert len(alerts[session_id]) >= 2, f"{session_id} has too few scripted alerts"


def test_engine_loop_set_demo_mode_loads_scripted_alerts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """set_demo_mode(True) populates _scripted_alerts; set_demo_mode(False) resets emit cache."""
    import pitwall.engine.demo_mode as demo_mod
    from pitwall.core.topics import Topics
    from pitwall.engine.loop import EngineLoop

    # Point the loader at a temp scripted_alerts file
    fake = tmp_path / "alerts.json"
    fake.write_text(json.dumps({
        "version": 1,
        "sessions": {
            "test_session": [
                {"lap_number": 5, "attacker_code": "AAA", "defender_code": "BBB", "source": "test"}
            ]
        },
    }))
    monkeypatch.setattr(demo_mod, "DEFAULT_SCRIPTED_ALERTS_PATH", fake)

    class _NoopBroadcaster:
        async def broadcast_json(self, data: dict[str, Any]) -> None:
            pass

    class _ConstPredictor:
        def predict(self, ctx: PaceContext) -> PacePrediction:
            return PacePrediction(predicted_lap_time_ms=74_500, confidence=0.8)

        def is_available(self, circuit_id: str, compound: Compound) -> bool:
            return True

    loop = EngineLoop(
        topics=Topics(),
        broadcaster=_NoopBroadcaster(),
        predictor=_ConstPredictor(),
        pit_loss_table={},
        predictor_name="scipy",
    )
    assert loop._demo_mode is False
    assert loop._scripted_alerts == {}

    loop.set_demo_mode(True)
    assert loop._demo_mode is True
    assert "test_session" in loop._scripted_alerts

    loop.set_demo_mode(False)
    assert loop._demo_mode is False
    assert loop._emitted_scripted_keys == set()


def test_build_causal_alert_payload_marks_predictor_as_causal() -> None:
    from pitwall.causal.live_inference import CausalLiveObservation, CausalLiveResult
    from pitwall.engine.demo_mode import build_causal_alert_payload

    obs = CausalLiveObservation(
        session_id="bahrain_2024_R",
        circuit_id="bahrain",
        lap_number=9,
        total_laps=57,
        laps_remaining=48,
        attacker_code="ZHO",
        defender_code="OCO",
        current_position=15,
        rival_position=14,
        gap_to_rival_ms=900,
        attacker_compound="MEDIUM",
        defender_compound="MEDIUM",
        attacker_tyre_age=8,
        defender_tyre_age=8,
        tyre_age_delta=0,
        track_status="GREEN",
        track_temp_c=35.0,
        air_temp_c=28.0,
        rainfall=False,
        pit_loss_estimate_ms=22_000,
    )
    result = CausalLiveResult(
        observation=obs,
        undercut_viable=True,
        support_level="weak",
        confidence=0.20,
        required_gain_ms=22_900,
        projected_gain_ms=23_500,
        projected_gap_after_pit_ms=-600,
        traffic_after_pit="low",
        top_factors=("projected_gap_after_pit_ms", "gap_to_rival_ms"),
        explanations=(
            "Undercut viable: projected fresh-tyre gain is above "
            "pit-loss-adjusted requirement.",
        ),
        counterfactuals=(),
    )
    payload = build_causal_alert_payload(result)
    assert payload["v"] == 1
    assert payload["type"] == "alert"
    body = payload["payload"]
    assert body["alert_type"] == "UNDERCUT_VIABLE"
    assert body["predictor_used"] == "causal"
    assert body["attacker_code"] == "ZHO"
    assert body["defender_code"] == "OCO"
    assert body["lap_number"] == 9
    assert body["session_id"] == "bahrain_2024_R"
    # Causal-specific fields the frontend can use for tooltips
    assert body["causal_support_level"] == "weak"
    assert "projected_gap_after_pit_ms" in body["causal_top_factors"]
    assert len(body["causal_explanations"]) >= 1
    # Legacy aliases preserved
    assert body["attacker"] == "ZHO"
    assert body["defender"] == "OCO"


def test_build_causal_alert_payload_uses_observation_gap_and_pit_loss() -> None:
    """Causal alerts must carry observation gap and pit_loss for predictor parity."""
    from pitwall.causal.live_inference import CausalLiveObservation, CausalLiveResult
    from pitwall.engine.demo_mode import build_causal_alert_payload

    obs = CausalLiveObservation(
        session_id="monaco_2024_R",
        circuit_id="monaco",
        lap_number=15,
        total_laps=78,
        laps_remaining=63,
        attacker_code="BOT",
        defender_code="ZHO",
        current_position=18,
        rival_position=17,
        gap_to_rival_ms=2_400,
        attacker_compound="HARD",
        defender_compound="HARD",
        attacker_tyre_age=15,
        defender_tyre_age=15,
        tyre_age_delta=0,
        track_status="GREEN",
        track_temp_c=40.0,
        air_temp_c=24.0,
        rainfall=False,
        pit_loss_estimate_ms=24_000,
    )
    result = CausalLiveResult(
        observation=obs,
        undercut_viable=True,
        support_level="strong",
        confidence=0.42,
        required_gain_ms=26_900,
        projected_gain_ms=27_100,
        projected_gap_after_pit_ms=-200,
        traffic_after_pit="medium",
        top_factors=("projected_gap_after_pit_ms",),
        explanations=("ok",),
        counterfactuals=(),
    )
    body = build_causal_alert_payload(result)["payload"]
    assert body["gap_actual_ms"] == 2_400
    assert body["pit_loss_ms"] == 24_000
    assert body["estimated_gain_ms"] == 27_100  # projected_gain_ms


@pytest.mark.asyncio
async def test_engine_loop_emits_causal_alert_in_demo_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When demo_mode is on and a pair is causally viable, a separate
    predictor_used='causal' alert is broadcast in addition to scipy/XGBoost."""
    import pitwall.engine.loop as loop_mod
    from pitwall.causal.live_inference import CausalLiveObservation, CausalLiveResult
    from pitwall.core.topics import Topics
    from pitwall.degradation.predictor import ScipyPredictor
    from pitwall.engine.loop import EngineLoop
    from pitwall.engine.state import DriverState, RaceState

    captured: list[dict[str, Any]] = []

    class _Capture:
        async def broadcast_json(self, data: dict[str, Any]) -> None:
            captured.append(data)

    def _fake_causal(
        state: Any,
        atk: Any,
        def_: Any,
        predictor: Any,
        *,
        pit_loss_ms: int,
    ) -> CausalLiveResult:
        obs = CausalLiveObservation(
            session_id=state.session_id or "test",
            circuit_id=state.circuit_id or "bahrain",
            lap_number=state.current_lap,
            total_laps=state.total_laps,
            laps_remaining=10,
            attacker_code=atk.driver_code,
            defender_code=def_.driver_code,
            current_position=atk.position,
            rival_position=def_.position,
            gap_to_rival_ms=1_000,
            attacker_compound=atk.compound,
            defender_compound=def_.compound,
            attacker_tyre_age=atk.tyre_age,
            defender_tyre_age=def_.tyre_age,
            tyre_age_delta=def_.tyre_age - atk.tyre_age,
            track_status=state.track_status or "GREEN",
            track_temp_c=35.0,
            air_temp_c=28.0,
            rainfall=False,
            pit_loss_estimate_ms=pit_loss_ms,
        )
        return CausalLiveResult(
            observation=obs,
            undercut_viable=True,
            support_level="weak",
            confidence=0.22,
            required_gain_ms=23_500,
            projected_gain_ms=24_000,
            projected_gap_after_pit_ms=-500,
            traffic_after_pit="low",
            top_factors=("projected_gap_after_pit_ms",),
            explanations=("causal demo test alert",),
            counterfactuals=(),
        )

    monkeypatch.setattr(loop_mod, "evaluate_causal_live", _fake_causal)

    loop = EngineLoop(
        topics=Topics(),
        broadcaster=_Capture(),
        predictor=ScipyPredictor([]),
        pit_loss_table={},
        predictor_name="scipy",
    )
    # Seed state with two consecutive drivers (so compute_relevant_pairs yields them)
    loop._state = RaceState()
    loop._state.session_id = "bahrain_2024_R"
    loop._state.circuit_id = "bahrain"
    loop._state.current_lap = 9
    loop._state.total_laps = 57
    loop._state.track_status = "GREEN"
    loop._state.drivers = {
        "OCO": DriverState(driver_code="OCO", position=1, gap_to_ahead_ms=None,
                           compound="MEDIUM", tyre_age=8, laps_in_stint=8, last_lap_ms=95_000),
        "ZHO": DriverState(driver_code="ZHO", position=2, gap_to_ahead_ms=1_000,
                           compound="MEDIUM", tyre_age=8, laps_in_stint=8, last_lap_ms=95_500),
    }

    loop.set_demo_mode(True)
    await loop._on_lap_complete()

    causal_alerts = [
        m for m in captured
        if m.get("type") == "alert"
        and m["payload"].get("predictor_used") == "causal"
    ]
    assert len(causal_alerts) >= 1
    assert causal_alerts[0]["payload"]["alert_type"] == "UNDERCUT_VIABLE"
    assert causal_alerts[0]["payload"]["attacker_code"] == "ZHO"
    assert causal_alerts[0]["payload"]["defender_code"] == "OCO"
    assert causal_alerts[0]["payload"]["causal_support_level"] == "weak"


@pytest.mark.asyncio
async def test_engine_loop_does_not_emit_causal_alert_when_demo_mode_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production path (demo_mode=False) must NOT call evaluate_causal_live."""
    import pitwall.engine.loop as loop_mod
    from pitwall.core.topics import Topics
    from pitwall.degradation.predictor import ScipyPredictor
    from pitwall.engine.loop import EngineLoop
    from pitwall.engine.state import DriverState, RaceState

    called = {"count": 0}

    def _spy_causal(*args: Any, **kwargs: Any) -> None:
        called["count"] += 1
        raise RuntimeError("must not be called in production")

    monkeypatch.setattr(loop_mod, "evaluate_causal_live", _spy_causal)

    class _NoopCast:
        async def broadcast_json(self, data: dict[str, Any]) -> None:
            pass

    loop = EngineLoop(
        topics=Topics(),
        broadcaster=_NoopCast(),
        predictor=ScipyPredictor([]),
        pit_loss_table={},
        predictor_name="scipy",
    )
    loop._state = RaceState()
    loop._state.session_id = "bahrain_2024_R"
    loop._state.circuit_id = "bahrain"
    loop._state.current_lap = 9
    loop._state.track_status = "GREEN"
    loop._state.drivers = {
        "OCO": DriverState(driver_code="OCO", position=1, gap_to_ahead_ms=None,
                           compound="MEDIUM", tyre_age=8, laps_in_stint=8, last_lap_ms=95_000),
        "ZHO": DriverState(driver_code="ZHO", position=2, gap_to_ahead_ms=1_000,
                           compound="MEDIUM", tyre_age=8, laps_in_stint=8, last_lap_ms=95_500),
    }
    # demo_mode is False by default; do NOT call set_demo_mode(True)
    await loop._on_lap_complete()
    assert called["count"] == 0
