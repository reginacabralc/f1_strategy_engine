"""Diagnostic helpers for replay undercut failure analysis.

This module is intentionally separate from :mod:`pitwall.engine.undercut`.
Production alert behavior stays fixed; diagnostics can vary horizons,
margins, pit-loss scaling, and cold-tyre assumptions to explain why a
replay did or did not alert.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Literal, cast

from pitwall.engine.pit_loss import (
    DEFAULT_PIT_LOSS_MS,
    GLOBAL_FALLBACK_CIRCUIT_ID,
    PitLossTable,
)
from pitwall.engine.projection import (
    COLD_TYRE_PENALTIES_MS,
    PacePredictor,
    UnsupportedContextError,
    project_pace,
)
from pitwall.engine.state import DriverState, RaceState, compute_relevant_pairs
from pitwall.engine.undercut import (
    CONFIDENCE_THRESHOLD,
    K_MAX,
    SCORE_THRESHOLD,
    UNDERCUT_MARGIN_MS,
    _base_context_kwargs,
    _context_for_driver,
    _data_quality_factor,
)
from pitwall.feeds.base import Event

ColdTyreMode = Literal["current", "none", "half"]
SnapshotMode = Literal["event_order", "lap_boundary"]

_NEXT_COMPOUND: dict[str, str] = {
    "SOFT": "MEDIUM",
    "MEDIUM": "HARD",
    "HARD": "MEDIUM",
    "INTER": "INTER",
    "WET": "WET",
}
_DEFAULT_NEXT_COMPOUND = "MEDIUM"
_DRY_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}


@dataclass(frozen=True, slots=True)
class UndercutDiagnosticConfig:
    """Knobs for diagnostic scoring; defaults match production behavior."""

    k: int = K_MAX
    margin_ms: int = UNDERCUT_MARGIN_MS
    pit_loss_scale: float = 1.0
    score_threshold: float = SCORE_THRESHOLD
    confidence_threshold: float = CONFIDENCE_THRESHOLD
    cold_tyre_mode: ColdTyreMode = "current"


@dataclass(frozen=True, slots=True)
class PitLossLookupDiagnostic:
    """Pit-loss value plus the fallback source used to find it."""

    pit_loss_ms: int
    source: Literal["exact_team", "circuit_median", "global_fallback", "default"]
    circuit_id: str
    team_code: str | None


@dataclass(frozen=True, slots=True)
class ScoreDecomposition:
    """One evaluated attacker/defender undercut decision with raw terms."""

    session_id: str
    lap_number: int
    attacker: str
    defender: str
    alert_type: str
    insufficient_reason: str | None
    insufficient_detail: str | None
    k: int
    margin_ms: int
    pit_loss_scale: float
    cold_tyre_mode: ColdTyreMode
    score_threshold: float
    confidence_threshold: float
    attacker_compound: str | None
    defender_compound: str | None
    attacker_next_compound: str | None
    attacker_tyre_age: int
    defender_tyre_age: int
    attacker_laps_in_stint: int
    defender_laps_in_stint: int
    original_pit_loss_ms: int
    pit_loss_ms: int
    pit_loss_source: str | None
    gap_actual_ms: int | None
    gap_recuperable_ms: int | None
    estimated_gain_ms: int | None
    raw_score_ms: int | None
    raw_score: float
    score: float
    confidence: float
    data_quality_factor: float
    should_alert: bool
    suppressed_by_score: bool
    suppressed_by_confidence: bool
    defender_projected_laps_ms: tuple[int, ...]
    attacker_projected_laps_ms: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """Minimal decision shape used by threshold and label diagnostics."""

    attacker: str
    defender: str
    lap_number: int
    score: float
    confidence: float
    estimated_gain_ms: int | None


@dataclass(frozen=True, slots=True)
class LabelRecord:
    """Minimal observed undercut label shape."""

    attacker: str
    defender: str
    lap_actual: int
    was_successful: bool = True
    source: str = "backtest"
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class AlertRecord:
    """First alert emitted for one attacker/defender pair."""

    attacker: str
    defender: str
    lap_alerted: int


@dataclass(frozen=True, slots=True)
class ThresholdConfig:
    """One threshold/physics configuration to evaluate offline."""

    score_threshold: float
    confidence_threshold: float
    margin_ms: int
    k: int
    pit_loss_scale: float
    cold_tyre_mode: ColdTyreMode


@dataclass(frozen=True, slots=True)
class ThresholdSweepRow:
    """Metrics for one threshold/physics configuration."""

    score_threshold: float
    confidence_threshold: float
    margin_ms: int
    k: int
    pit_loss_scale: float
    cold_tyre_mode: ColdTyreMode
    alerts: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    suppressed_by_confidence: int
    suppressed_by_score: int
    mean_estimated_gain_ms: float | None
    mean_score: float | None
    mean_confidence: float | None


@dataclass(frozen=True, slots=True)
class LabelAuditRow:
    """Audit result for one observed undercut label."""

    session_id: str | None
    attacker: str
    defender: str
    lap_actual: int
    was_successful: bool
    source: str
    exact_pair_decision_count: int
    relevant_before_pit: bool
    first_relevant_lap: int | None
    min_lead_time_laps: int | None
    label_window_aligned: bool
    likely_unobservable_label: bool


@dataclass(frozen=True, slots=True)
class ProjectionErrorRow:
    """As-raced pair projection error for one evaluated decision window."""

    session_id: str
    lap_number: int
    attacker: str
    defender: str
    k: int
    predicted_gap_recuperable_ms: int
    realized_as_raced_gap_delta_ms: int
    error_ms: int
    abs_error_ms: int


def score_threshold_config() -> UndercutDiagnosticConfig:
    """Return production threshold defaults as a diagnostic config."""

    return UndercutDiagnosticConfig()


def decompose_undercut_decision(
    state: RaceState,
    attacker: DriverState,
    defender: DriverState,
    predictor: PacePredictor,
    *,
    pit_loss_ms: int = DEFAULT_PIT_LOSS_MS,
    pit_loss_source: str | None = None,
    config: UndercutDiagnosticConfig | None = None,
) -> ScoreDecomposition:
    """Compute production-compatible undercut score terms for one pair."""

    cfg = config or UndercutDiagnosticConfig()
    scaled_pit_loss_ms = round(pit_loss_ms * cfg.pit_loss_scale)
    base = _base_decomposition(
        state,
        attacker,
        defender,
        cfg,
        original_pit_loss_ms=pit_loss_ms,
        pit_loss_ms=scaled_pit_loss_ms,
        pit_loss_source=pit_loss_source,
    )

    attacker_compound = (attacker.compound or "").upper()
    defender_compound = (defender.compound or "").upper()
    if attacker_compound in {"INTER", "WET"} or defender_compound in {"INTER", "WET"}:
        return _insufficient_decomposition(base, "UNDERCUT_DISABLED_RAIN", "wet_compound")
    if defender.laps_in_stint < 2 or attacker.laps_in_stint < 3:
        reason = "defender_fresh_tyres" if defender.laps_in_stint < 2 else "attacker_short_stint"
        return _insufficient_decomposition(base, "INSUFFICIENT_DATA", reason)
    gap_actual_ms = attacker.gap_to_ahead_ms
    if gap_actual_ms is None:
        return _insufficient_decomposition(base, "INSUFFICIENT_DATA", "missing_gap_actual")

    def_compound = defender.compound or _DEFAULT_NEXT_COMPOUND
    next_compound = _NEXT_COMPOUND.get(attacker_compound, _DEFAULT_NEXT_COMPOUND)
    circuit_id = state.circuit_id or ""

    try:
        conf_def = predictor.predict(
            _context_for_driver(state, defender, def_compound, max(1, defender.tyre_age))
        ).confidence
        conf_atk = predictor.predict(
            _context_for_driver(
                state,
                attacker,
                next_compound,
                1,
                start_lap_in_stint=1,
                stint_number=attacker.stint_number + 1,
            )
        ).confidence
        data_quality = _data_quality_factor(attacker)
        confidence = min(conf_def, conf_atk) * data_quality
        defender_laps = project_pace(
            defender.driver_code,
            circuit_id,
            def_compound,
            defender.tyre_age,
            cfg.k,
            predictor,
            apply_cold_tyre_penalty=False,
            **_base_context_kwargs(state, defender, def_compound),
        )
        attacker_laps = project_pace(
            attacker.driver_code,
            circuit_id,
            next_compound,
            0,
            cfg.k,
            predictor,
            apply_cold_tyre_penalty=True,
            cold_tyre_penalties=_cold_tyre_penalties(cfg.cold_tyre_mode),
            **_base_context_kwargs(
                state,
                attacker,
                next_compound,
                start_lap_in_stint=0,
                stint_number=attacker.stint_number + 1,
            ),
        )
    except UnsupportedContextError as exc:
        return _insufficient_decomposition(
            base,
            "INSUFFICIENT_DATA",
            "unsupported_predictor_context",
            str(exc),
        )

    gap_recuperable_ms = sum(
        defender_lap - attacker_lap
        for defender_lap, attacker_lap in zip(defender_laps, attacker_laps, strict=True)
    )
    raw_score_ms = gap_recuperable_ms - scaled_pit_loss_ms - gap_actual_ms - cfg.margin_ms
    raw_score = raw_score_ms / max(1, scaled_pit_loss_ms)
    score = max(0.0, min(1.0, raw_score))
    should_alert = score > cfg.score_threshold and confidence > cfg.confidence_threshold
    return ScoreDecomposition(
        **base,
        alert_type="UNDERCUT_VIABLE",
        insufficient_reason=None,
        insufficient_detail=None,
        gap_actual_ms=gap_actual_ms,
        gap_recuperable_ms=gap_recuperable_ms,
        estimated_gain_ms=gap_recuperable_ms - scaled_pit_loss_ms,
        raw_score_ms=raw_score_ms,
        raw_score=raw_score,
        score=score,
        confidence=confidence,
        data_quality_factor=data_quality,
        should_alert=should_alert,
        suppressed_by_score=score <= cfg.score_threshold,
        suppressed_by_confidence=(
            score > cfg.score_threshold and confidence <= cfg.confidence_threshold
        ),
        defender_projected_laps_ms=tuple(defender_laps),
        attacker_projected_laps_ms=tuple(attacker_laps),
    )


def collect_score_decompositions(
    events: list[Event],
    predictor: PacePredictor,
    pit_loss_table: PitLossTable,
    *,
    config: UndercutDiagnosticConfig | None = None,
    snapshot_mode: SnapshotMode = "event_order",
    max_rows: int | None = None,
) -> list[ScoreDecomposition]:
    """Collect score decompositions from a replay event stream."""

    ordered_events = sorted(events, key=_event_sort_key)
    cfg = config or UndercutDiagnosticConfig()
    if snapshot_mode == "lap_boundary":
        return _collect_lap_boundary_decompositions(
            ordered_events,
            predictor,
            pit_loss_table,
            cfg,
            max_rows=max_rows,
        )
    return _collect_event_order_decompositions(
        ordered_events,
        predictor,
        pit_loss_table,
        cfg,
        max_rows=max_rows,
    )


def lookup_pit_loss_diagnostic(
    circuit_id: str,
    team_code: str | None,
    table: PitLossTable,
    *,
    default: int = DEFAULT_PIT_LOSS_MS,
) -> PitLossLookupDiagnostic:
    """Return the selected pit loss and identify the fallback tier."""

    circuit_table = table.get(circuit_id, {})
    if team_code is not None and team_code in circuit_table:
        return PitLossLookupDiagnostic(
            circuit_table[team_code],
            "exact_team",
            circuit_id,
            team_code,
        )
    if None in circuit_table:
        return PitLossLookupDiagnostic(circuit_table[None], "circuit_median", circuit_id, team_code)
    global_table = table.get(GLOBAL_FALLBACK_CIRCUIT_ID, {})
    if None in global_table:
        return PitLossLookupDiagnostic(global_table[None], "global_fallback", circuit_id, team_code)
    return PitLossLookupDiagnostic(default, "default", circuit_id, team_code)


def decision_record_from_decomposition(row: ScoreDecomposition) -> DecisionRecord:
    """Convert full score diagnostics into the minimal sweep shape."""

    return DecisionRecord(
        attacker=row.attacker,
        defender=row.defender,
        lap_number=row.lap_number,
        score=row.score,
        confidence=row.confidence,
        estimated_gain_ms=row.estimated_gain_ms,
    )


def sweep_thresholds(
    labels: list[LabelRecord],
    decisions: list[DecisionRecord],
    *,
    configs: list[ThresholdConfig],
    window_laps: int = K_MAX,
) -> list[ThresholdSweepRow]:
    """Evaluate alert metrics over threshold/physics configurations."""

    rows: list[ThresholdSweepRow] = []
    for cfg in configs:
        alerts = alerts_from_decisions(
            decisions,
            score_threshold=cfg.score_threshold,
            confidence_threshold=cfg.confidence_threshold,
        )
        true_pos, false_pos, false_neg = score_alerts(labels, alerts, window_laps=window_laps)
        precision = _safe_div(len(true_pos), len(true_pos) + len(false_pos))
        recall = _safe_div(len(true_pos), len(true_pos) + len(false_neg))
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        estimated_gains = [
            decision.estimated_gain_ms
            for decision in decisions
            if decision.estimated_gain_ms is not None
        ]
        rows.append(
            ThresholdSweepRow(
                score_threshold=cfg.score_threshold,
                confidence_threshold=cfg.confidence_threshold,
                margin_ms=cfg.margin_ms,
                k=cfg.k,
                pit_loss_scale=cfg.pit_loss_scale,
                cold_tyre_mode=cfg.cold_tyre_mode,
                alerts=len(alerts),
                true_positives=len(true_pos),
                false_positives=len(false_pos),
                false_negatives=len(false_neg),
                precision=precision,
                recall=recall,
                f1=f1,
                suppressed_by_confidence=sum(
                    1
                    for decision in decisions
                    if decision.score > cfg.score_threshold
                    and decision.confidence <= cfg.confidence_threshold
                ),
                suppressed_by_score=sum(
                    1 for decision in decisions if decision.score <= cfg.score_threshold
                ),
                mean_estimated_gain_ms=float(mean(estimated_gains)) if estimated_gains else None,
                mean_score=float(mean(decision.score for decision in decisions))
                if decisions
                else None,
                mean_confidence=float(mean(decision.confidence for decision in decisions))
                if decisions
                else None,
            )
        )
    return rows


def alerts_from_decisions(
    decisions: list[DecisionRecord],
    *,
    score_threshold: float,
    confidence_threshold: float,
) -> list[AlertRecord]:
    """Return first alert per pair under the supplied thresholds."""

    first_alert_by_pair: dict[tuple[str, str], AlertRecord] = {}
    for decision in decisions:
        if decision.score <= score_threshold or decision.confidence <= confidence_threshold:
            continue
        key = (decision.attacker, decision.defender)
        first_alert_by_pair.setdefault(
            key,
            AlertRecord(
                attacker=decision.attacker,
                defender=decision.defender,
                lap_alerted=decision.lap_number,
            ),
        )
    return list(first_alert_by_pair.values())


def score_alerts(
    labels: list[LabelRecord],
    alerts: list[AlertRecord],
    *,
    window_laps: int = K_MAX,
) -> tuple[list[LabelRecord], list[AlertRecord], list[LabelRecord]]:
    """Score alerts against labels using exact pair and K-lap lead window."""

    alert_by_pair = {(alert.attacker, alert.defender): alert for alert in alerts}
    matched_alerts: set[tuple[str, str]] = set()
    true_pos: list[LabelRecord] = []
    false_neg: list[LabelRecord] = []
    for label in labels:
        alert = alert_by_pair.get((label.attacker, label.defender))
        if alert and 0 <= label.lap_actual - alert.lap_alerted <= window_laps:
            matched_alerts.add((label.attacker, label.defender))
            true_pos.append(label)
        else:
            false_neg.append(label)
    false_pos = [
        alert
        for alert in alerts
        if (alert.attacker, alert.defender) not in matched_alerts
    ]
    return true_pos, false_pos, false_neg


def audit_labels_against_decisions(
    labels: list[LabelRecord],
    decisions: list[DecisionRecord],
    *,
    window_laps: int = K_MAX,
) -> list[LabelAuditRow]:
    """Audit whether labels were observable as exact relevant pairs pre-pit."""

    rows: list[LabelAuditRow] = []
    for label in labels:
        exact = [
            decision
            for decision in decisions
            if decision.attacker == label.attacker
            and decision.defender == label.defender
            and 0 <= label.lap_actual - decision.lap_number <= window_laps
        ]
        first_lap = min((decision.lap_number for decision in exact), default=None)
        min_lead_time = (
            min(label.lap_actual - decision.lap_number for decision in exact)
            if exact
            else None
        )
        relevant = bool(exact)
        rows.append(
            LabelAuditRow(
                session_id=label.session_id,
                attacker=label.attacker,
                defender=label.defender,
                lap_actual=label.lap_actual,
                was_successful=label.was_successful,
                source=label.source,
                exact_pair_decision_count=len(exact),
                relevant_before_pit=relevant,
                first_relevant_lap=first_lap,
                min_lead_time_laps=min_lead_time,
                label_window_aligned=relevant,
                likely_unobservable_label=not relevant,
            )
        )
    return rows


def label_records_from_backtest_objects(
    labels: list[Any],
    *,
    session_id: str | None = None,
) -> list[LabelRecord]:
    """Adapt backtest private label objects without making them runtime API."""

    return [
        LabelRecord(
            attacker=str(label.attacker),
            defender=str(label.defender),
            lap_actual=int(label.lap_actual),
            was_successful=bool(label.was_successful),
            source="backtest_final_position",
            session_id=session_id or getattr(label, "session_id", None),
        )
        for label in labels
    ]


def threshold_configs(
    *,
    score_thresholds: tuple[float, ...] = (0.0, 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0),
    confidence_thresholds: tuple[float, ...] = (0.0, 0.15, 0.35, 0.5, 0.7, 1.0),
    margins_ms: tuple[int, ...] = (0, 250, 500, 1_000),
    horizons: tuple[int, ...] = (2, 3, 5, 8),
    pit_loss_scales: tuple[float, ...] = (0.8, 1.0, 1.2),
    cold_tyre_modes: tuple[ColdTyreMode, ...] = ("current", "none", "half"),
) -> list[ThresholdConfig]:
    """Build the default expanded threshold/physics sweep grid."""

    return [
        ThresholdConfig(
            score_threshold=score_threshold,
            confidence_threshold=confidence_threshold,
            margin_ms=margin_ms,
            k=horizon,
            pit_loss_scale=pit_loss_scale,
            cold_tyre_mode=cold_tyre_mode,
        )
        for horizon in horizons
        for margin_ms in margins_ms
        for pit_loss_scale in pit_loss_scales
        for cold_tyre_mode in cold_tyre_modes
        for score_threshold in score_thresholds
        for confidence_threshold in confidence_thresholds
    ]


def projection_errors_from_decompositions(
    decompositions: list[ScoreDecomposition],
    events: list[Event],
) -> list[ProjectionErrorRow]:
    """Compare projected pair gap recovery to as-raced future lap deltas."""

    actual_laps = _actual_lap_times(events)
    rows: list[ProjectionErrorRow] = []
    for row in decompositions:
        if row.gap_recuperable_ms is None:
            continue
        attacker_laps: list[int] = []
        defender_laps: list[int] = []
        for offset in range(1, row.k + 1):
            attacker_lap = actual_laps.get((row.attacker, row.lap_number + offset))
            defender_lap = actual_laps.get((row.defender, row.lap_number + offset))
            if attacker_lap is None or defender_lap is None:
                break
            attacker_laps.append(attacker_lap)
            defender_laps.append(defender_lap)
        if len(attacker_laps) != row.k or len(defender_laps) != row.k:
            continue
        realized = sum(
            defender_lap - attacker_lap
            for defender_lap, attacker_lap in zip(defender_laps, attacker_laps, strict=True)
        )
        error = row.gap_recuperable_ms - realized
        rows.append(
            ProjectionErrorRow(
                session_id=row.session_id,
                lap_number=row.lap_number,
                attacker=row.attacker,
                defender=row.defender,
                k=row.k,
                predicted_gap_recuperable_ms=row.gap_recuperable_ms,
                realized_as_raced_gap_delta_ms=realized,
                error_ms=error,
                abs_error_ms=abs(error),
            )
        )
    return rows


def _base_decomposition(
    state: RaceState,
    attacker: DriverState,
    defender: DriverState,
    cfg: UndercutDiagnosticConfig,
    *,
    original_pit_loss_ms: int,
    pit_loss_ms: int,
    pit_loss_source: str | None,
) -> dict[str, Any]:
    attacker_compound = attacker.compound.upper() if attacker.compound else None
    defender_compound = defender.compound.upper() if defender.compound else None
    next_compound = _NEXT_COMPOUND.get(attacker_compound or "", _DEFAULT_NEXT_COMPOUND)
    return {
        "session_id": state.session_id,
        "lap_number": state.current_lap,
        "attacker": attacker.driver_code,
        "defender": defender.driver_code,
        "k": cfg.k,
        "margin_ms": cfg.margin_ms,
        "pit_loss_scale": cfg.pit_loss_scale,
        "cold_tyre_mode": cfg.cold_tyre_mode,
        "score_threshold": cfg.score_threshold,
        "confidence_threshold": cfg.confidence_threshold,
        "attacker_compound": attacker_compound,
        "defender_compound": defender_compound,
        "attacker_next_compound": next_compound,
        "attacker_tyre_age": attacker.tyre_age,
        "defender_tyre_age": defender.tyre_age,
        "attacker_laps_in_stint": attacker.laps_in_stint,
        "defender_laps_in_stint": defender.laps_in_stint,
        "original_pit_loss_ms": original_pit_loss_ms,
        "pit_loss_ms": pit_loss_ms,
        "pit_loss_source": pit_loss_source,
    }


def _insufficient_decomposition(
    base: dict[str, Any],
    alert_type: str,
    insufficient_reason: str,
    insufficient_detail: str | None = None,
) -> ScoreDecomposition:
    return ScoreDecomposition(
        **base,
        alert_type=alert_type,
        insufficient_reason=insufficient_reason,
        insufficient_detail=insufficient_detail,
        gap_actual_ms=cast(int | None, base.get("gap_actual_ms")),
        gap_recuperable_ms=None,
        estimated_gain_ms=None,
        raw_score_ms=None,
        raw_score=0.0,
        score=0.0,
        confidence=0.0,
        data_quality_factor=0.0,
        should_alert=False,
        suppressed_by_score=True,
        suppressed_by_confidence=False,
        defender_projected_laps_ms=(),
        attacker_projected_laps_ms=(),
    )


def _cold_tyre_penalties(mode: ColdTyreMode) -> tuple[int, ...]:
    if mode == "none":
        return tuple(0 for _ in COLD_TYRE_PENALTIES_MS)
    if mode == "half":
        return tuple(round(value / 2) for value in COLD_TYRE_PENALTIES_MS)
    return COLD_TYRE_PENALTIES_MS


def _collect_event_order_decompositions(
    events: list[Event],
    predictor: PacePredictor,
    pit_loss_table: PitLossTable,
    cfg: UndercutDiagnosticConfig,
    *,
    max_rows: int | None,
) -> list[ScoreDecomposition]:
    state = RaceState()
    rows: list[ScoreDecomposition] = []
    for event in events:
        state.apply(event)
        if event["type"] != "lap_complete" or state.track_status in {"SC", "VSC"}:
            continue
        rows.extend(_decompositions_for_state(state, predictor, pit_loss_table, cfg))
        if max_rows is not None and len(rows) >= max_rows:
            return rows[:max_rows]
    return rows


def _collect_lap_boundary_decompositions(
    events: list[Event],
    predictor: PacePredictor,
    pit_loss_table: PitLossTable,
    cfg: UndercutDiagnosticConfig,
    *,
    max_rows: int | None,
) -> list[ScoreDecomposition]:
    state = RaceState()
    rows: list[ScoreDecomposition] = []
    for index, event in enumerate(events):
        state.apply(event)
        if event["type"] != "lap_complete":
            continue
        lap_number = _lap_number(event)
        next_lap_number = _next_lap_number(events, start=index + 1)
        if lap_number is None or next_lap_number == lap_number:
            continue
        if state.track_status in {"SC", "VSC"}:
            continue
        rows.extend(_decompositions_for_state(state, predictor, pit_loss_table, cfg))
        if max_rows is not None and len(rows) >= max_rows:
            return rows[:max_rows]
    return rows


def _decompositions_for_state(
    state: RaceState,
    predictor: PacePredictor,
    pit_loss_table: PitLossTable,
    cfg: UndercutDiagnosticConfig,
) -> list[ScoreDecomposition]:
    rows: list[ScoreDecomposition] = []
    for attacker, defender in compute_relevant_pairs(state):
        lookup = lookup_pit_loss_diagnostic(state.circuit_id, attacker.team_code, pit_loss_table)
        rows.append(
            decompose_undercut_decision(
                state,
                attacker,
                defender,
                predictor,
                pit_loss_ms=lookup.pit_loss_ms,
                pit_loss_source=lookup.source,
                config=cfg,
            )
        )
    return rows


def _actual_lap_times(events: list[Event]) -> dict[tuple[str, int], int]:
    actual: dict[tuple[str, int], int] = {}
    for event in events:
        if event["type"] != "lap_complete":
            continue
        payload = event.get("payload") or {}
        compound = str(payload.get("compound") or "").upper()
        if compound not in _DRY_COMPOUNDS:
            continue
        if bool(payload.get("is_pit_in", False)) or bool(payload.get("is_pit_out", False)):
            continue
        if payload.get("is_valid", True) is False:
            continue
        driver = str(payload.get("driver_code") or "")
        lap = _int_or_none(payload.get("lap_number"))
        lap_time = _int_or_none(payload.get("lap_time_ms"))
        if driver and lap is not None and lap_time is not None:
            actual[(driver, lap)] = lap_time
    return actual


def _safe_div(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _event_sort_key(event: Event) -> tuple[Any, int, int, str]:
    payload = event.get("payload") or {}
    return (
        event.get("ts"),
        _int_or_none(payload.get("lap_number")) or 0,
        _int_or_none(payload.get("position")) or 99,
        str(payload.get("driver_code") or ""),
    )


def _lap_number(event: Event) -> int | None:
    return _int_or_none((event.get("payload") or {}).get("lap_number"))


def _next_lap_number(events: list[Event], *, start: int) -> int | None:
    for event in events[start:]:
        if event["type"] == "lap_complete":
            return _lap_number(event)
    return None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return None
