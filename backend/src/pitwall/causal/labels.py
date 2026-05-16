"""Label construction for causal undercut viability datasets."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from pitwall.engine.projection import COLD_TYRE_PENALTIES_MS
from pitwall.ingest.normalize import to_float

VALID_CAUSAL_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})
NEXT_COMPOUND: dict[str, str] = {
    "SOFT": "MEDIUM",
    "MEDIUM": "HARD",
    "HARD": "MEDIUM",
}
DEFAULT_PROJECTION_LAPS = 5
DEFAULT_SAFETY_MARGIN_MS = 500
TRAFFIC_PENALTY_HIGH_MS: int = 3_000
TRAFFIC_PENALTY_MEDIUM_MS: int = 1_500


@dataclass(frozen=True, slots=True)
class DegradationCurve:
    circuit_id: str
    compound: str
    a: float
    b: float
    c: float
    confidence: float

    def predict_ms(self, tyre_age: int) -> int:
        return max(1, round(self.a + self.b * tyre_age + self.c * tyre_age * tyre_age))


@dataclass(frozen=True, slots=True)
class ViabilityInputs:
    circuit_id: str
    attacker_compound: str | None
    defender_compound: str | None
    attacker_tyre_age: int | None
    defender_tyre_age: int | None
    gap_to_rival_ms: int | None
    pit_loss_estimate_ms: int | None
    track_status: str | None
    rainfall: bool | None
    attacker_laps_in_stint: int | None = None
    defender_laps_in_stint: int | None = None
    traffic_after_pit: str | None = None


@dataclass(frozen=True, slots=True)
class ViabilityLabel:
    undercut_viable: bool | None
    undercut_window_open: bool
    projected_gain_if_pit_now_ms: int | None
    fresh_tyre_advantage_ms: int | None
    required_gain_to_clear_rival_ms: int | None
    projected_gap_after_pit_ms: int | None
    next_compound: str | None
    pace_confidence: float | None
    row_usable: bool
    missing_reason: str | None
    label_source: str


def build_degradation_lookup(
    rows: list[dict[str, object]],
) -> dict[tuple[str, str], DegradationCurve]:
    """Build a degradation lookup from DB coefficient rows."""

    lookup: dict[tuple[str, str], DegradationCurve] = {}
    values_by_compound: dict[str, list[DegradationCurve]] = {}
    for row in rows:
        circuit_id = str(row["circuit_id"])
        compound = str(row["compound"]).upper()
        confidence = to_float(row.get("r_squared"))
        curve = DegradationCurve(
            circuit_id=circuit_id,
            compound=compound,
            a=_required_float(row, "a"),
            b=_required_float(row, "b"),
            c=_required_float(row, "c"),
            confidence=(
                max(0.0, min(1.0, confidence))
                if confidence is not None
                else 0.0
            ),
        )
        lookup[(circuit_id, compound)] = curve
        values_by_compound.setdefault(compound, []).append(curve)
    for compound, curves in values_by_compound.items():
        lookup[("__global__", compound)] = DegradationCurve(
            circuit_id="__global__",
            compound=compound,
            a=float(median(curve.a for curve in curves)),
            b=float(median(curve.b for curve in curves)),
            c=float(median(curve.c for curve in curves)),
            confidence=float(median(curve.confidence for curve in curves)),
        )
    return lookup


def compute_undercut_viability_label(
    inputs: ViabilityInputs,
    degradation_lookup: dict[tuple[str, str], DegradationCurve],
    *,
    projection_laps: int = DEFAULT_PROJECTION_LAPS,
    safety_margin_ms: int = DEFAULT_SAFETY_MARGIN_MS,
    cold_tyre_penalties_ms: tuple[int, ...] = COLD_TYRE_PENALTIES_MS,
) -> ViabilityLabel:
    """Compute the proxy-modeled undercut viability label for one pair-lap."""

    missing_reason = _missing_reason(inputs)
    if missing_reason is not None:
        return _unusable(missing_reason)

    attacker_compound = str(inputs.attacker_compound).upper()
    defender_compound = str(inputs.defender_compound).upper()
    next_compound = NEXT_COMPOUND.get(attacker_compound)
    if next_compound is None:
        return _unusable("missing_next_compound")

    defender_curve = _curve_for(degradation_lookup, inputs.circuit_id, defender_compound)
    attacker_curve = _curve_for(degradation_lookup, inputs.circuit_id, next_compound)
    if defender_curve is None:
        return _unusable("missing_defender_degradation_curve")
    if attacker_curve is None:
        return _unusable("missing_attacker_fresh_degradation_curve")

    assert inputs.defender_tyre_age is not None
    assert inputs.gap_to_rival_ms is not None
    assert inputs.pit_loss_estimate_ms is not None

    defender_laps = [
        defender_curve.predict_ms(inputs.defender_tyre_age + lap_offset)
        for lap_offset in range(1, projection_laps + 1)
    ]
    attacker_laps = [
        attacker_curve.predict_ms(lap_offset)
        + _cold_penalty(cold_tyre_penalties_ms, lap_offset)
        for lap_offset in range(1, projection_laps + 1)
    ]
    per_lap_advantages = [
        defender_ms - attacker_ms
        for defender_ms, attacker_ms in zip(defender_laps, attacker_laps, strict=True)
    ]
    projected_gain_ms = sum(per_lap_advantages)
    traffic_penalty = _traffic_penalty_ms(inputs.traffic_after_pit)
    projected_gain_ms = projected_gain_ms - traffic_penalty
    fresh_tyre_advantage_ms = round(projected_gain_ms / projection_laps)
    required_gain_ms = inputs.gap_to_rival_ms + inputs.pit_loss_estimate_ms + safety_margin_ms
    projected_gap_after_pit_ms = required_gain_ms - projected_gain_ms
    undercut_viable = projected_gain_ms >= required_gain_ms

    return ViabilityLabel(
        undercut_viable=undercut_viable,
        undercut_window_open=undercut_viable,
        projected_gain_if_pit_now_ms=projected_gain_ms,
        fresh_tyre_advantage_ms=fresh_tyre_advantage_ms,
        required_gain_to_clear_rival_ms=required_gain_ms,
        projected_gap_after_pit_ms=projected_gap_after_pit_ms,
        next_compound=next_compound,
        pace_confidence=min(defender_curve.confidence, attacker_curve.confidence),
        row_usable=True,
        missing_reason=None,
        label_source="proxy_modeled_causal_scipy_v1",
    )


def _missing_reason(inputs: ViabilityInputs) -> str | None:
    attacker_compound = str(inputs.attacker_compound or "").upper()
    defender_compound = str(inputs.defender_compound or "").upper()
    track_status = str(inputs.track_status or "GREEN").upper()
    if inputs.rainfall is True:
        return "rainfall"
    if attacker_compound not in VALID_CAUSAL_COMPOUNDS:
        return "unsupported_attacker_compound"
    if defender_compound not in VALID_CAUSAL_COMPOUNDS:
        return "unsupported_defender_compound"
    if track_status != "GREEN":
        return "non_green_track_status"
    if inputs.attacker_tyre_age is None:
        return "missing_attacker_tyre_age"
    if inputs.defender_tyre_age is None:
        return "missing_defender_tyre_age"
    if inputs.gap_to_rival_ms is None:
        return "missing_gap_to_rival"
    if inputs.pit_loss_estimate_ms is None:
        return "missing_pit_loss_estimate"
    return None


def _cold_penalty(penalties_ms: tuple[int, ...], lap_offset: int) -> int:
    index = lap_offset - 1
    return penalties_ms[index] if index < len(penalties_ms) else 0


def _curve_for(
    degradation_lookup: dict[tuple[str, str], DegradationCurve],
    circuit_id: str,
    compound: str,
) -> DegradationCurve | None:
    return degradation_lookup.get((circuit_id, compound)) or degradation_lookup.get(
        ("__global__", compound)
    )


def _traffic_penalty_ms(traffic_after_pit: str | None) -> int:
    """Return ms to subtract from projected_gain for the given traffic level.

    Dirty-air following costs ~1 s/lap for ~3 laps of out-lap exposure.
    'high' = ≥2 cars within 3 s of projected pit exit.
    'medium' = 1 car within 3 s.
    'low'/'unknown'/None = no penalty.
    """
    if traffic_after_pit == "high":
        return TRAFFIC_PENALTY_HIGH_MS
    if traffic_after_pit == "medium":
        return TRAFFIC_PENALTY_MEDIUM_MS
    return 0


def _unusable(reason: str) -> ViabilityLabel:
    return ViabilityLabel(
        undercut_viable=None,
        undercut_window_open=False,
        projected_gain_if_pit_now_ms=None,
        fresh_tyre_advantage_ms=None,
        required_gain_to_clear_rival_ms=None,
        projected_gap_after_pit_ms=None,
        next_compound=None,
        pace_confidence=None,
        row_usable=False,
        missing_reason=reason,
        label_source="proxy_modeled_causal_scipy_v1",
    )


def _required_float(row: dict[str, object], key: str) -> float:
    value = to_float(row.get(key))
    if value is None:
        raise ValueError(f"{key} is required for degradation curve")
    return value
