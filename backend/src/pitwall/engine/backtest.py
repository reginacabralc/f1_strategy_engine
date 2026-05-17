"""Replay-based backtest for undercut alerts.

This module compares the normal undercut engine against labels derived from
actual replay pit/position events. It intentionally does not depend on the
causal package; causal analysis remains an informative side path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean, median
from typing import Any, Literal, cast

from pitwall.engine.pit_loss import PitLossTable, lookup_pit_loss
from pitwall.engine.projection import Compound, PaceContext, PacePredictor, UnsupportedContextError
from pitwall.engine.state import RaceState, compute_relevant_pairs
from pitwall.engine.undercut import K_MAX, evaluate_undercut
from pitwall.feeds.base import Event

PredictorName = Literal["scipy", "xgboost", "causal"]
_DRY_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}


@dataclass(frozen=True)
class BacktestMatch:
    attacker: str
    defender: str
    lap_alerted: int | None = None
    lap_actual: int | None = None
    was_successful: bool | None = None


@dataclass(frozen=True)
class BacktestResultData:
    session_id: str
    predictor: PredictorName
    precision: float
    recall: float
    f1: float
    mean_lead_time_laps: float | None = None
    mae_k1_ms: int | None = None
    mae_k3_ms: int | None = None
    mae_k5_ms: int | None = None
    true_positives: list[BacktestMatch] = field(default_factory=list)
    false_positives: list[BacktestMatch] = field(default_factory=list)
    false_negatives: list[BacktestMatch] = field(default_factory=list)
    threshold_sweep: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class _Label:
    attacker: str
    defender: str
    lap_actual: int
    was_successful: bool


@dataclass(frozen=True)
class _Alert:
    attacker: str
    defender: str
    lap_alerted: int


@dataclass(frozen=True)
class _DecisionObservation:
    attacker: str
    defender: str
    lap_number: int
    score: float
    confidence: float


def run_backtest(
    session_id: str,
    events: list[Event],
    predictor: PacePredictor,
    *,
    predictor_name: PredictorName,
    pit_loss_table: PitLossTable,
) -> BacktestResultData:
    """Evaluate one predictor against one replay session."""
    ordered_events = sorted(events, key=_event_sort_key)
    labels = _derive_labels(ordered_events)
    decisions = _collect_decisions(ordered_events, predictor, pit_loss_table)
    alerts = _alerts_from_decisions(decisions, score_threshold=0.4, confidence_threshold=0.5)
    true_pos, false_pos, false_neg = _score_alerts(labels, alerts)
    mae_by_k = _pace_mae_by_horizon(ordered_events, predictor)

    precision = len(true_pos) / (len(true_pos) + len(false_pos)) if true_pos or false_pos else 0.0
    recall = len(true_pos) / (len(true_pos) + len(false_neg)) if true_pos or false_neg else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    lead_times = [
        match.lap_actual - match.lap_alerted
        for match in true_pos
        if match.lap_actual is not None and match.lap_alerted is not None
    ]
    return BacktestResultData(
        session_id=session_id,
        predictor=predictor_name,
        precision=precision,
        recall=recall,
        f1=f1,
        mean_lead_time_laps=float(mean(lead_times)) if lead_times else None,
        mae_k1_ms=mae_by_k.get(1),
        mae_k3_ms=mae_by_k.get(3),
        mae_k5_ms=mae_by_k.get(5),
        true_positives=true_pos,
        false_positives=false_pos,
        false_negatives=false_neg,
        threshold_sweep=_threshold_sweep(labels, decisions),
    )


def _collect_decisions(
    events: list[Event],
    predictor: PacePredictor,
    pit_loss_table: PitLossTable,
) -> list[_DecisionObservation]:
    state = RaceState()
    decisions: list[_DecisionObservation] = []
    for event in events:
        state.apply(event)
        if event["type"] != "lap_complete":
            continue
        if state.track_status in {"SC", "VSC"}:
            continue
        for attacker, defender in compute_relevant_pairs(state):
            pit_loss = lookup_pit_loss(state.circuit_id, attacker.team_code, pit_loss_table)
            decision = evaluate_undercut(state, attacker, defender, predictor, pit_loss)
            if decision.alert_type != "UNDERCUT_VIABLE":
                continue
            decisions.append(
                _DecisionObservation(
                    attacker=decision.attacker_code,
                    defender=decision.defender_code,
                    lap_number=state.current_lap,
                    score=decision.score,
                    confidence=decision.confidence,
                ),
            )
    return decisions


def _alerts_from_decisions(
    decisions: list[_DecisionObservation],
    *,
    score_threshold: float,
    confidence_threshold: float,
) -> list[_Alert]:
    first_alert_by_pair: dict[tuple[str, str], _Alert] = {}
    for decision in decisions:
        if decision.score <= score_threshold or decision.confidence <= confidence_threshold:
            continue
        key = (decision.attacker, decision.defender)
        first_alert_by_pair.setdefault(
            key,
            _Alert(
                attacker=decision.attacker,
                defender=decision.defender,
                lap_alerted=decision.lap_number,
            ),
        )
    return list(first_alert_by_pair.values())


def _derive_labels(events: list[Event]) -> list[_Label]:
    latest_position_by_driver: dict[str, int] = {}
    latest_driver_by_position: dict[int, str] = {}
    pitted_pairs: list[tuple[str, str, int]] = []

    for event in events:
        if event["type"] != "lap_complete":
            continue
        payload = event.get("payload") or {}
        driver = str(payload.get("driver_code") or "")
        position = _int_or_none(payload.get("position"))
        lap_number = _int_or_none(payload.get("lap_number"))
        if not driver or position is None or lap_number is None:
            continue

        if bool(payload.get("is_pit_in", False)) and position > 1:
            defender = latest_driver_by_position.get(position - 1)
            if defender:
                pitted_pairs.append((driver, defender, lap_number))

        latest_position_by_driver[driver] = position
        latest_driver_by_position[position] = driver

    labels: list[_Label] = []
    for attacker, defender, lap_actual in pitted_pairs:
        attacker_pos = latest_position_by_driver.get(attacker)
        defender_pos = latest_position_by_driver.get(defender)
        successful = (
            attacker_pos is not None
            and defender_pos is not None
            and attacker_pos < defender_pos
        )
        if lap_actual <= 1 or not successful:
            continue
        labels.append(
            _Label(
                attacker=attacker,
                defender=defender,
                lap_actual=lap_actual,
                was_successful=successful,
            )
        )
    return labels


def _score_alerts(
    labels: list[_Label],
    alerts: list[_Alert],
) -> tuple[list[BacktestMatch], list[BacktestMatch], list[BacktestMatch]]:
    alert_by_pair = {(alert.attacker, alert.defender): alert for alert in alerts}
    matched_alerts: set[tuple[str, str]] = set()
    true_pos: list[BacktestMatch] = []
    false_neg: list[BacktestMatch] = []

    for label in labels:
        key = (label.attacker, label.defender)
        alert = alert_by_pair.get(key)
        if alert and 0 <= label.lap_actual - alert.lap_alerted <= K_MAX:
            matched_alerts.add(key)
            true_pos.append(
                BacktestMatch(
                    attacker=label.attacker,
                    defender=label.defender,
                    lap_alerted=alert.lap_alerted,
                    lap_actual=label.lap_actual,
                    was_successful=label.was_successful,
                )
            )
        else:
            false_neg.append(
                BacktestMatch(
                    attacker=label.attacker,
                    defender=label.defender,
                    lap_actual=label.lap_actual,
                    was_successful=label.was_successful,
                )
            )

    false_pos = [
        BacktestMatch(
            attacker=alert.attacker,
            defender=alert.defender,
            lap_alerted=alert.lap_alerted,
        )
        for alert in alerts
        if (alert.attacker, alert.defender) not in matched_alerts
    ]
    return true_pos, false_pos, false_neg


def _threshold_sweep(
    labels: list[_Label],
    decisions: list[_DecisionObservation],
    *,
    score_thresholds: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6),
    confidence_thresholds: tuple[float, ...] = (0.0, 0.15, 0.35, 0.5, 0.7),
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for score_threshold in score_thresholds:
        for confidence_threshold in confidence_thresholds:
            alerts = _alerts_from_decisions(
                decisions,
                score_threshold=score_threshold,
                confidence_threshold=confidence_threshold,
            )
            true_pos, false_pos, false_neg = _score_alerts(labels, alerts)
            precision = (
                len(true_pos) / (len(true_pos) + len(false_pos))
                if true_pos or false_pos
                else 0.0
            )
            recall = (
                len(true_pos) / (len(true_pos) + len(false_neg))
                if true_pos or false_neg
                else 0.0
            )
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            rows.append(
                {
                    "score_threshold": score_threshold,
                    "confidence_threshold": confidence_threshold,
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                    "true_positives": len(true_pos),
                    "false_positives": len(false_pos),
                    "false_negatives": len(false_neg),
                    "alerts": len(alerts),
                    "suppressed_by_confidence": sum(
                        1
                        for decision in decisions
                        if decision.score > score_threshold
                        and decision.confidence <= confidence_threshold
                    ),
                }
            )
    return rows


def _pace_mae_by_horizon(events: list[Event], predictor: PacePredictor) -> dict[int, int | None]:
    lap_events = [event for event in events if event["type"] == "lap_complete"]
    session_info = _session_info(events)
    future_by_driver_lap: dict[tuple[str, int], Event] = {}
    for event in lap_events:
        payload = event.get("payload") or {}
        driver = str(payload.get("driver_code") or "")
        lap = _int_or_none(payload.get("lap_number"))
        if driver and lap is not None:
            future_by_driver_lap[(driver, lap)] = event

    history_by_compound: dict[str, list[int]] = defaultdict(list)
    errors: dict[int, list[int]] = {1: [], 3: [], 5: []}
    for origin in lap_events:
        origin_payload = origin.get("payload") or {}
        driver = str(origin_payload.get("driver_code") or "")
        origin_lap = _int_or_none(origin_payload.get("lap_number"))
        if not driver or origin_lap is None:
            continue
        references = {
            compound: float(median(values))
            for compound, values in history_by_compound.items()
            if values
        }
        for horizon in (1, 3, 5):
            future = future_by_driver_lap.get((driver, origin_lap + horizon))
            if future is None:
                continue
            future_payload = future.get("payload") or {}
            actual = _int_or_none(future_payload.get("lap_time_ms"))
            compound = str(future_payload.get("compound") or "").upper()
            if actual is None or compound not in _DRY_COMPOUNDS:
                continue
            try:
                prediction = predictor.predict(
                    _pace_context_from_payload(
                        future_payload,
                        session_info=session_info,
                        reference_lap_time_ms=references.get(compound),
                    )
                )
            except UnsupportedContextError:
                continue
            errors[horizon].append(abs(prediction.predicted_lap_time_ms - actual))
        _append_reference_if_clean(origin_payload, history_by_compound)
    return {
        horizon: round(mean(values)) if values else None
        for horizon, values in errors.items()
    }


def _pace_context_from_payload(
    payload: dict[str, Any],
    *,
    session_info: dict[str, Any],
    reference_lap_time_ms: float | None,
) -> PaceContext:
    lap_number = _int_or_none(payload.get("lap_number"))
    total_laps = _int_or_none(session_info.get("total_laps"))
    gaps = _int_or_none(payload.get("gap_to_ahead_ms"))
    return PaceContext(
        driver_code=str(payload.get("driver_code") or ""),
        circuit_id=str(session_info.get("circuit_id") or ""),
        compound=cast(Compound, str(payload.get("compound") or "MEDIUM").upper()),
        tyre_age=_int_or_none(payload.get("tyre_age")) or 0,
        team_code=_str_or_none(payload.get("team_code")),
        track_temp_c=_float_or_none(payload.get("track_temp_c")),
        air_temp_c=_float_or_none(payload.get("air_temp_c")),
        stint_number=_int_or_none(payload.get("stint_number")),
        lap_in_stint=_int_or_none(payload.get("lap_in_stint")),
        total_laps=total_laps,
        lap_number=lap_number,
        position=_int_or_none(payload.get("position")),
        gap_to_ahead_ms=gaps,
        gap_to_leader_ms=_int_or_none(payload.get("gap_to_leader_ms")),
        is_in_traffic=gaps is not None and gaps < 1_500,
        dirty_air_proxy_ms=max(0, 2_000 - gaps) if gaps is not None else 0,
        reference_lap_time_ms=reference_lap_time_ms,
        driver_pace_offset_missing=True,
    )


def _session_info(events: list[Event]) -> dict[str, Any]:
    for event in events:
        if event["type"] == "session_start":
            payload = event.get("payload") or {}
            return {
                "circuit_id": payload.get("circuit_id"),
                "total_laps": payload.get("total_laps"),
            }
    return {}


def _append_reference_if_clean(
    payload: dict[str, Any],
    history_by_compound: dict[str, list[int]],
) -> None:
    compound = str(payload.get("compound") or "").upper()
    lap_time = _int_or_none(payload.get("lap_time_ms"))
    if compound not in _DRY_COMPOUNDS or lap_time is None:
        return
    if payload.get("is_valid", True) is False:
        return
    if bool(payload.get("is_pit_in", False)) or bool(payload.get("is_pit_out", False)):
        return
    if str(payload.get("track_status") or "GREEN").upper() != "GREEN":
        return
    history_by_compound[compound].append(lap_time)


def _event_sort_key(event: Event) -> tuple[Any, int, int, str]:
    payload = event.get("payload") or {}
    return (
        event.get("ts"),
        _int_or_none(payload.get("lap_number")) or 0,
        _int_or_none(payload.get("position")) or 99,
        str(payload.get("driver_code") or ""),
    )


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None
