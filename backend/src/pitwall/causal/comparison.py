"""Compare causal_scipy, scipy_engine, and xgb_engine decisions."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, SupportsFloat, cast

from pitwall.engine.undercut import CONFIDENCE_THRESHOLD, SCORE_THRESHOLD

DEFAULT_COMPARISON_PATH = Path("data/causal/engine_disagreements.csv")


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    row_count: int
    comparable_scipy_rows: int
    comparable_xgb_rows: int
    causal_vs_scipy_disagreements: int
    causal_vs_xgb_disagreements: int | None
    scipy_vs_xgb_disagreements: int | None
    xgb_status: str


def load_dataset_for_comparison(path: Path) -> Any:
    """Load a causal dataset as pandas for comparison reporting."""

    polars = import_module("polars")
    pandas = import_module("pandas")
    return pandas.DataFrame(polars.read_parquet(path).to_dicts())


def build_disagreement_table(data: Any) -> Any:
    """Return row-level engine decisions and disagreement flags."""

    frame = data.copy()
    required = {
        "session_id",
        "lap_number",
        "attacker_code",
        "defender_code",
        "undercut_viable",
        "projected_gain_if_pit_now_ms",
        "pit_loss_estimate_ms",
        "gap_to_rival_ms",
        "pace_confidence",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"comparison dataset missing column(s): {missing}")

    frame["causal_scipy_decision"] = frame["undercut_viable"].map(_bool_or_none)
    frame["scipy_engine_decision"] = frame.apply(_scipy_engine_decision, axis=1)
    if "xgb_engine_decision" not in frame.columns:
        frame["xgb_engine_decision"] = None
        frame["xgb_status"] = "unavailable_feature_pipeline"
    else:
        frame["xgb_engine_decision"] = frame["xgb_engine_decision"].map(_bool_or_none)
        frame["xgb_status"] = "available"

    frame["causal_vs_scipy_disagreement"] = frame.apply(
        lambda row: _disagree(row["causal_scipy_decision"], row["scipy_engine_decision"]),
        axis=1,
    )
    frame["causal_vs_xgb_disagreement"] = frame.apply(
        lambda row: _disagree(row["causal_scipy_decision"], row["xgb_engine_decision"]),
        axis=1,
    )
    frame["scipy_vs_xgb_disagreement"] = frame.apply(
        lambda row: _disagree(row["scipy_engine_decision"], row["xgb_engine_decision"]),
        axis=1,
    )
    return frame.loc[
        :,
        [
            "session_id",
            "lap_number",
            "attacker_code",
            "defender_code",
            "causal_scipy_decision",
            "scipy_engine_decision",
            "xgb_engine_decision",
            "xgb_status",
            "causal_vs_scipy_disagreement",
            "causal_vs_xgb_disagreement",
            "scipy_vs_xgb_disagreement",
        ],
    ]


def summarize_disagreements(table: Any) -> ComparisonSummary:
    """Summarize engine disagreement counts."""

    comparable_scipy = table.dropna(subset=["causal_scipy_decision", "scipy_engine_decision"])
    comparable_xgb = table.dropna(subset=["causal_scipy_decision", "xgb_engine_decision"])
    xgb_statuses = set(table["xgb_status"].dropna().unique())
    xgb_available = "available" in xgb_statuses
    return ComparisonSummary(
        row_count=len(table),
        comparable_scipy_rows=len(comparable_scipy),
        comparable_xgb_rows=len(comparable_xgb),
        causal_vs_scipy_disagreements=int(
            comparable_scipy["causal_vs_scipy_disagreement"].sum()
        ),
        causal_vs_xgb_disagreements=(
            int(comparable_xgb["causal_vs_xgb_disagreement"].sum())
            if xgb_available
            else None
        ),
        scipy_vs_xgb_disagreements=(
            int(
                table.dropna(subset=["scipy_engine_decision", "xgb_engine_decision"])[
                    "scipy_vs_xgb_disagreement"
                ].sum()
            )
            if xgb_available
            else None
        ),
        xgb_status="available" if xgb_available else "unavailable_feature_pipeline",
    )


def write_disagreement_table(table: Any, path: Path = DEFAULT_COMPARISON_PATH) -> None:
    """Write the row-level disagreement table to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)


def _scipy_engine_decision(row: Any) -> bool | None:
    projected_gain = _number_or_none(row["projected_gain_if_pit_now_ms"])
    pit_loss = _number_or_none(row["pit_loss_estimate_ms"])
    gap = _number_or_none(row["gap_to_rival_ms"])
    confidence = _number_or_none(row["pace_confidence"])
    if projected_gain is None or pit_loss is None or gap is None or confidence is None:
        return None
    score = (projected_gain - pit_loss - gap - 500) / max(1.0, pit_loss)
    score = max(0.0, min(1.0, score))
    return score > SCORE_THRESHOLD and confidence > CONFIDENCE_THRESHOLD


def _disagree(left: bool | None, right: bool | None) -> bool | None:
    if left is None or right is None:
        return None
    return left != right


def _bool_or_none(value: object) -> bool | None:
    if value is None:
        return None
    try:
        if import_module("pandas").isna(value):
            return None
    except TypeError:
        pass
    return bool(value)


def _number_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        if import_module("pandas").isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, str | int | float):
        return float(value)
    if hasattr(value, "__float__"):
        return float(cast(SupportsFloat, value))
    return None
