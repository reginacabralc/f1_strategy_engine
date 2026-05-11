"""Estimate and load pit-loss values from ingested race data."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from statistics import mean, median, pstdev
from typing import Any, Protocol

from pitwall.engine.pit_loss import (
    DEFAULT_PIT_LOSS_MS,
    PitLossTable,
)
from pitwall.engine.pit_loss import (
    GLOBAL_FALLBACK_CIRCUIT_ID as ENGINE_GLOBAL_FALLBACK_CIRCUIT_ID,
)
from pitwall.ingest.normalize import clean_nulls

MIN_REALISTIC_PIT_LOSS_MS = 10_000
MAX_REALISTIC_PIT_LOSS_MS = 40_000
GLOBAL_FALLBACK_CIRCUIT_ID = ENGINE_GLOBAL_FALLBACK_CIRCUIT_ID
MIN_GOOD_SAMPLES = 8
MAX_GOOD_IQR_MS = 2_500
MILD_OUTLIER_DELTA_MS = 4_000
EXTREME_OUTLIER_DELTA_MS = 8_000

EXISTING_PIT_LOSS_SAMPLE_SQL = """
    SELECT
        e.circuit_id,
        d.team_code,
        ps.pit_loss_ms,
        'direct_pit_loss_ms' AS source
    FROM pit_stops ps
    JOIN sessions s ON s.session_id = ps.session_id
    JOIN events e ON e.event_id = s.event_id
    LEFT JOIN drivers d ON d.driver_code = ps.driver_code
    WHERE ps.pit_loss_ms IS NOT NULL
      AND ps.pit_loss_ms BETWEEN :min_ms AND :max_ms
"""

ESTIMATED_PIT_LOSS_SAMPLE_SQL = """
    WITH pit_outs AS (
        SELECT
            ps.session_id,
            ps.driver_code,
            ps.lap_number AS pit_out_lap,
            e.circuit_id,
            d.team_code,
            l_in.lap_time_ms AS in_lap_ms,
            l_out.lap_time_ms AS out_lap_ms
        FROM pit_stops ps
        JOIN sessions s ON s.session_id = ps.session_id
        JOIN events e ON e.event_id = s.event_id
        LEFT JOIN drivers d ON d.driver_code = ps.driver_code
        JOIN laps l_out
          ON l_out.session_id = ps.session_id
         AND l_out.driver_code = ps.driver_code
         AND l_out.lap_number = ps.lap_number
        JOIN laps l_in
          ON l_in.session_id = ps.session_id
         AND l_in.driver_code = ps.driver_code
         AND l_in.lap_number = ps.lap_number - 1
        WHERE ps.pit_loss_ms IS NULL
          AND ps.new_compound IS NOT NULL
          AND l_in.lap_time_ms IS NOT NULL
          AND l_out.lap_time_ms IS NOT NULL
    ),
    estimates AS (
        SELECT
            p.circuit_id,
            p.team_code,
            ROUND(p.in_lap_ms + p.out_lap_ms - 2 * b.baseline_ms)::INT AS pit_loss_ms,
            'estimated_from_laps' AS source
        FROM pit_outs p
        CROSS JOIN LATERAL (
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY l.lap_time_ms) AS baseline_ms
            FROM laps l
            WHERE l.session_id = p.session_id
              AND l.driver_code = p.driver_code
              AND l.lap_time_ms IS NOT NULL
              AND l.is_valid = TRUE
              AND l.is_pit_in = FALSE
              AND l.is_pit_out = FALSE
              AND (l.track_status IS NULL OR l.track_status = 'GREEN')
              AND l.lap_time_ms BETWEEN 60000 AND 180000
              AND l.lap_number BETWEEN GREATEST(1, p.pit_out_lap - 6) AND p.pit_out_lap + 6
        ) b
        WHERE b.baseline_ms IS NOT NULL
    )
    SELECT circuit_id, team_code, pit_loss_ms, source
    FROM estimates
    WHERE pit_loss_ms BETWEEN :min_ms AND :max_ms
"""

PIT_LOSS_ESTIMATE_SQL = """
    SELECT circuit_id, team_code, pit_loss_ms, n_samples
    FROM pit_loss_estimates
    ORDER BY circuit_id, team_code NULLS FIRST
"""

DELETE_ESTIMATES_SQL = """
    DELETE FROM pit_loss_estimates
    WHERE circuit_id = ANY(:circuit_ids)
"""

INSERT_ESTIMATE_SQL = """
    INSERT INTO pit_loss_estimates (
        circuit_id,
        team_code,
        pit_loss_ms,
        n_samples,
        computed_at
    )
    VALUES (
        :circuit_id,
        :team_code,
        :pit_loss_ms,
        :n_samples,
        NOW()
    )
"""


class ConnectionLike(Protocol):
    def execute(self, statement: Any, parameters: Any | None = None) -> Iterable[Any]: ...


@dataclass(frozen=True, slots=True)
class PitLossSample:
    circuit_id: str
    team_code: str | None
    pit_loss_ms: int
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class PitLossSampleClassification:
    sample: PitLossSample
    kind: str


@dataclass(frozen=True, slots=True)
class PitLossEstimate:
    circuit_id: str
    team_code: str | None
    pit_loss_ms: int
    n_samples: int
    iqr_ms: int | None = None
    std_ms: int | None = None
    min_ms: int | None = None
    max_ms: int | None = None
    aggregation_method: str = "median_v1"
    source: str = "unknown"
    quality: str = "weak"
    mild_outliers: int = 0
    quarantined_samples: int = 0
    trimmed_mean_ms: int | None = None
    winsorized_mean_ms: int | None = None


@dataclass(frozen=True, slots=True)
class PitLossSampleStats:
    n_samples: int
    median_ms: int
    iqr_ms: int
    std_ms: int
    min_ms: int
    max_ms: int
    trimmed_mean_ms: int | None = None
    winsorized_mean_ms: int | None = None


def build_pit_loss_estimates(
    samples: Iterable[PitLossSample],
    *,
    include_global: bool = False,
) -> list[PitLossEstimate]:
    """Build median pit-loss estimates by team plus circuit fallback rows."""

    clean_samples = [_normalize_sample(sample) for sample in samples]
    by_circuit: dict[str, list[PitLossSample]] = defaultdict(list)
    by_team: dict[tuple[str, str], list[PitLossSample]] = defaultdict(list)
    for sample in clean_samples:
        by_circuit[sample.circuit_id].append(sample)
        if sample.team_code is not None:
            by_team[(sample.circuit_id, sample.team_code)].append(sample)

    estimates: list[PitLossEstimate] = []
    for circuit_id, group_samples in sorted(by_circuit.items()):
        estimate = _estimate_group(circuit_id, None, group_samples)
        if estimate is not None:
            estimates.append(estimate)
    for (circuit_id, team_code), group_samples in sorted(by_team.items()):
        estimate = _estimate_group(circuit_id, team_code, group_samples)
        if estimate is not None:
            estimates.append(estimate)
    if include_global:
        global_estimate = build_global_pit_loss_estimate(clean_samples)
        if global_estimate is not None:
            estimates.append(global_estimate)
    return estimates


def build_global_pit_loss_estimate(
    samples: Iterable[PitLossSample],
) -> PitLossEstimate | None:
    """Build a conservative global fallback from all usable samples."""

    estimate = _estimate_group(
        GLOBAL_FALLBACK_CIRCUIT_ID,
        None,
        [_normalize_sample(sample) for sample in samples],
    )
    if estimate is None:
        return None
    return PitLossEstimate(
        circuit_id=GLOBAL_FALLBACK_CIRCUIT_ID,
        team_code=None,
        pit_loss_ms=max(estimate.pit_loss_ms, DEFAULT_PIT_LOSS_MS),
        n_samples=estimate.n_samples,
        iqr_ms=estimate.iqr_ms,
        std_ms=estimate.std_ms,
        min_ms=estimate.min_ms,
        max_ms=estimate.max_ms,
        aggregation_method="median_conservative_global_v1",
        source=estimate.source,
        quality="fallback",
        mild_outliers=estimate.mild_outliers,
        quarantined_samples=estimate.quarantined_samples,
        trimmed_mean_ms=estimate.trimmed_mean_ms,
        winsorized_mean_ms=estimate.winsorized_mean_ms,
    )


def classify_pit_loss_samples(
    samples: Iterable[PitLossSample],
) -> list[PitLossSampleClassification]:
    """Classify samples into normal, mild outlier, or quarantined."""

    normalized = [_normalize_sample(sample) for sample in samples]
    values = [sample.pit_loss_ms for sample in normalized if _is_realistic(sample.pit_loss_ms)]
    median_ms = _median_ms(values) if values else None

    classifications: list[PitLossSampleClassification] = []
    for sample in normalized:
        if not _is_realistic(sample.pit_loss_ms) or (
            median_ms is not None
            and abs(sample.pit_loss_ms - median_ms)
            > EXTREME_OUTLIER_DELTA_MS
        ):
            kind = "extreme_outlier_quarantined"
        elif (
            median_ms is not None
            and abs(sample.pit_loss_ms - median_ms) > MILD_OUTLIER_DELTA_MS
        ):
            kind = "mild_outlier"
        else:
            kind = "valid_normal"
        classifications.append(PitLossSampleClassification(sample=sample, kind=kind))
    return classifications


def compute_sample_statistics(values: Iterable[int]) -> PitLossSampleStats:
    """Compute robust diagnostics for already accepted sample values."""

    sorted_values = sorted(values)
    if not sorted_values:
        raise ValueError("cannot compute statistics for empty pit-loss sample set")
    iqr_ms = _iqr_ms(sorted_values)
    return PitLossSampleStats(
        n_samples=len(sorted_values),
        median_ms=_median_ms(sorted_values),
        iqr_ms=iqr_ms,
        std_ms=round(pstdev(sorted_values)) if len(sorted_values) > 1 else 0,
        min_ms=min(sorted_values),
        max_ms=max(sorted_values),
        trimmed_mean_ms=_trimmed_mean_ms(sorted_values),
        winsorized_mean_ms=_winsorized_mean_ms(sorted_values),
    )


def build_pit_loss_report_rows(samples: Iterable[PitLossSample]) -> list[dict[str, Any]]:
    """Return diagnostic rows for validation/reporting without widening the DB schema."""

    rows: list[dict[str, Any]] = []
    for estimate in build_pit_loss_estimates(samples, include_global=True):
        rows.append(_estimate_to_report_row(estimate))
    return rows


def validate_pit_loss_estimates(estimates: Iterable[PitLossEstimate]) -> None:
    """Validate estimates before persisting or using them in the engine."""

    rows = list(estimates)
    if not rows:
        raise ValueError("no pit-loss estimates found")

    fallback_circuits = {
        row.circuit_id
        for row in rows
        if row.team_code is None and row.circuit_id != GLOBAL_FALLBACK_CIRCUIT_ID
    }
    estimate_circuits = {
        row.circuit_id for row in rows if row.circuit_id != GLOBAL_FALLBACK_CIRCUIT_ID
    }
    missing_fallback = sorted(estimate_circuits - fallback_circuits)
    if missing_fallback:
        raise ValueError(f"missing circuit fallback for {', '.join(missing_fallback)}")

    for row in rows:
        if row.pit_loss_ms <= 0:
            raise ValueError(f"non-positive pit loss for {row.circuit_id}/{row.team_code}")
        if not _is_realistic(row.pit_loss_ms):
            raise ValueError(
                f"pit loss outside realistic range for {row.circuit_id}/{row.team_code}: "
                f"{row.pit_loss_ms} ms"
            )
        if row.n_samples <= 0:
            raise ValueError(f"non-positive sample count for {row.circuit_id}/{row.team_code}")


def pit_loss_table_from_estimates(estimates: Iterable[PitLossEstimate]) -> PitLossTable:
    """Convert persisted estimates into Stream B's lookup-table shape."""

    table: PitLossTable = {}
    for row in estimates:
        table.setdefault(row.circuit_id, {})[row.team_code] = row.pit_loss_ms
    return table


def load_pit_loss_samples(connection: ConnectionLike) -> list[PitLossSample]:
    """Load direct pit-loss rows and conservative nearby-lap estimates."""

    params = {"min_ms": MIN_REALISTIC_PIT_LOSS_MS, "max_ms": MAX_REALISTIC_PIT_LOSS_MS}
    rows = list(connection.execute(_sql_text(EXISTING_PIT_LOSS_SAMPLE_SQL), params))
    rows.extend(connection.execute(_sql_text(ESTIMATED_PIT_LOSS_SAMPLE_SQL), params))
    return [
        _sample_from_row(dict(row._mapping) if hasattr(row, "_mapping") else dict(row))
        for row in rows
    ]


def load_pit_loss_estimates(connection: ConnectionLike) -> list[PitLossEstimate]:
    rows = connection.execute(_sql_text(PIT_LOSS_ESTIMATE_SQL))
    return [
        _estimate_from_row(dict(row._mapping) if hasattr(row, "_mapping") else dict(row))
        for row in rows
    ]


def load_pit_loss_table(connection: ConnectionLike) -> PitLossTable:
    estimates = load_pit_loss_estimates(connection)
    global_estimate = build_global_pit_loss_estimate(load_pit_loss_samples(connection))
    if global_estimate is not None:
        estimates.append(global_estimate)
    validate_pit_loss_estimates(estimates)
    return pit_loss_table_from_estimates(estimates)


def write_pit_loss_estimates(
    connection: ConnectionLike,
    estimates: Iterable[PitLossEstimate],
) -> None:
    rows = list(estimates)
    validate_pit_loss_estimates(rows)
    circuit_ids = sorted({row.circuit_id for row in rows})
    connection.execute(_sql_text(DELETE_ESTIMATES_SQL), {"circuit_ids": circuit_ids})
    connection.execute(_sql_text(INSERT_ESTIMATE_SQL), [_estimate_to_row(row) for row in rows])


def _median_ms(values: list[int]) -> int:
    return round(median(values))


def _trimmed_mean_ms(values: list[int]) -> int | None:
    if len(values) < MIN_GOOD_SAMPLES:
        return None
    trim_count = max(1, round(len(values) * 0.1))
    trimmed = values[trim_count:-trim_count]
    if not trimmed:
        return None
    return round(mean(trimmed))


def _winsorized_mean_ms(values: list[int]) -> int | None:
    if len(values) < MIN_GOOD_SAMPLES:
        return None
    trim_count = max(1, round(len(values) * 0.1))
    low = values[trim_count]
    high = values[-trim_count - 1]
    winsorized = [
        low if idx < trim_count else high if idx >= len(values) - trim_count else value
        for idx, value in enumerate(values)
    ]
    return round(mean(winsorized))


def _iqr_ms(values: list[int]) -> int:
    if len(values) == 1:
        return 0
    midpoint = len(values) // 2
    lower = values[:midpoint]
    upper = values[midpoint:] if len(values) % 2 == 0 else values[midpoint + 1 :]
    if not lower or not upper:
        return 0
    return round(median(upper) - median(lower))


def _is_realistic(value: int) -> bool:
    return MIN_REALISTIC_PIT_LOSS_MS <= value <= MAX_REALISTIC_PIT_LOSS_MS


def _estimate_group(
    circuit_id: str,
    team_code: str | None,
    samples: list[PitLossSample],
) -> PitLossEstimate | None:
    classifications = classify_pit_loss_samples(samples)
    usable = [
        row.sample
        for row in classifications
        if row.kind in {"valid_normal", "mild_outlier"}
    ]
    if not usable:
        return None

    stats = compute_sample_statistics([sample.pit_loss_ms for sample in usable])
    mild_outliers = sum(1 for row in classifications if row.kind == "mild_outlier")
    quarantined = sum(
        1 for row in classifications if row.kind == "extreme_outlier_quarantined"
    )
    return PitLossEstimate(
        circuit_id=circuit_id,
        team_code=team_code,
        pit_loss_ms=stats.median_ms,
        n_samples=stats.n_samples,
        iqr_ms=stats.iqr_ms,
        std_ms=stats.std_ms,
        min_ms=stats.min_ms,
        max_ms=stats.max_ms,
        aggregation_method="median_v1",
        source=_source_label(sample.source for sample in usable),
        quality=_quality_label(stats, mild_outliers, quarantined),
        mild_outliers=mild_outliers,
        quarantined_samples=quarantined,
        trimmed_mean_ms=stats.trimmed_mean_ms,
        winsorized_mean_ms=stats.winsorized_mean_ms,
    )


def _quality_label(
    stats: PitLossSampleStats,
    mild_outliers: int,
    quarantined_samples: int,
) -> str:
    if (
        stats.n_samples >= MIN_GOOD_SAMPLES
        and stats.iqr_ms <= MAX_GOOD_IQR_MS
        and mild_outliers == 0
        and quarantined_samples == 0
    ):
        return "good"
    return "weak"


def _source_label(sources: Iterable[str]) -> str:
    clean_sources = {source for source in sources if source}
    if not clean_sources:
        return "unknown"
    if len(clean_sources) == 1:
        return next(iter(clean_sources))
    return "mixed"


def _normalize_sample(sample: PitLossSample) -> PitLossSample:
    return PitLossSample(
        circuit_id=sample.circuit_id.lower(),
        team_code=(sample.team_code.lower() if sample.team_code is not None else None),
        pit_loss_ms=sample.pit_loss_ms,
        source=sample.source,
    )


def _sample_from_row(row: dict[str, Any]) -> PitLossSample:
    cleaned = clean_nulls(row)
    return PitLossSample(
        circuit_id=str(cleaned["circuit_id"]).lower(),
        team_code=(str(cleaned["team_code"]).lower() if cleaned.get("team_code") else None),
        pit_loss_ms=int(cleaned["pit_loss_ms"]),
        source=str(cleaned.get("source") or "unknown"),
    )


def _estimate_from_row(row: dict[str, Any]) -> PitLossEstimate:
    cleaned = clean_nulls(row)
    return PitLossEstimate(
        circuit_id=str(cleaned["circuit_id"]).lower(),
        team_code=(str(cleaned["team_code"]).lower() if cleaned.get("team_code") else None),
        pit_loss_ms=int(cleaned["pit_loss_ms"]),
        n_samples=int(cleaned["n_samples"]),
        source="persisted",
    )


def _estimate_to_row(row: PitLossEstimate) -> dict[str, Any]:
    return {
        "circuit_id": row.circuit_id,
        "team_code": row.team_code,
        "pit_loss_ms": row.pit_loss_ms,
        "n_samples": row.n_samples,
    }


def _estimate_to_report_row(row: PitLossEstimate) -> dict[str, Any]:
    team_code = row.team_code
    if row.circuit_id == GLOBAL_FALLBACK_CIRCUIT_ID:
        team_code = "GLOBAL_FALLBACK"
    elif team_code is None:
        team_code = "CIRCUIT_MEDIAN"
    return {
        "circuit_id": row.circuit_id,
        "team_code": team_code,
        "pit_loss_ms": row.pit_loss_ms,
        "n_samples": row.n_samples,
        "iqr_ms": row.iqr_ms,
        "std_ms": row.std_ms,
        "min_ms": row.min_ms,
        "max_ms": row.max_ms,
        "aggregation_method": row.aggregation_method,
        "source": row.source,
        "quality": row.quality,
        "status": "ok" if row.quality in {"good", "fallback"} else "review",
        "mild_outliers": row.mild_outliers,
        "quarantined_samples": row.quarantined_samples,
        "trimmed_mean_ms": row.trimmed_mean_ms,
        "winsorized_mean_ms": row.winsorized_mean_ms,
    }


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
