"""DoWhy prototypes for the causal undercut dataset."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from pitwall.causal.graph import validate_dag

DEFAULT_DATASET_PATH = Path("data/causal/undercut_driver_rival_lap.parquet")

DEFAULT_COMMON_CAUSES = (
    "lap_number",
    "laps_remaining",
    "current_position",
    "rival_position",
    "gap_to_rival_ms",
    "pit_loss_estimate_ms",
    "attacker_tyre_age",
    "defender_tyre_age",
    "tyre_age_delta",
    "track_temp_c",
    "air_temp_c",
    "rainfall",
)


@dataclass(frozen=True, slots=True)
class EffectSpec:
    treatment: str
    outcome: str
    method_name: str = "backdoor.linear_regression"
    common_causes: tuple[str, ...] = DEFAULT_COMMON_CAUSES


@dataclass(frozen=True, slots=True)
class EffectEstimate:
    treatment: str
    outcome: str
    method_name: str
    n_rows: int
    estimand_type: str
    estimate_value: float


def load_causal_dataset(path: Path = DEFAULT_DATASET_PATH) -> Any:
    """Load the causal dataset as a pandas DataFrame for DoWhy."""

    if not path.exists():
        raise FileNotFoundError(
            f"causal dataset not found at {path}. Run `make build-causal-dataset` first."
        )
    polars = import_module("polars")
    pandas = import_module("pandas")
    return pandas.DataFrame(polars.read_parquet(path).to_dicts())


def estimate_effect(
    data: Any,
    spec: EffectSpec,
    *,
    graph: str | None = None,
) -> EffectEstimate:
    """Estimate one simple DoWhy effect over the causal dataset.

    The prototype intentionally starts with linear regression. For binary
    outcomes this is a linear probability estimate, documented as a limitation
    rather than presented as a classifier.
    """

    validate_dag()
    dowhy = _dowhy_module()
    frame = _prepare_frame(data, spec)
    model = dowhy.CausalModel(
        data=frame,
        treatment=spec.treatment,
        outcome=spec.outcome,
        graph=graph or _backdoor_gml_for_frame(frame, spec),
    )
    estimand = model.identify_effect(proceed_when_unidentifiable=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, module="dowhy")
        warnings.filterwarnings("ignore", category=RuntimeWarning, module="statsmodels")
        estimate = model.estimate_effect(
            estimand,
            method_name=spec.method_name,
        )
    return EffectEstimate(
        treatment=spec.treatment,
        outcome=spec.outcome,
        method_name=spec.method_name,
        n_rows=len(frame),
        estimand_type=str(estimand.estimand_type),
        estimate_value=float(estimate.value),
    )


def estimate_default_effects(data: Any) -> list[EffectEstimate]:
    """Run the Phase 6 default effects."""

    specs = [
        EffectSpec(
            treatment="fresh_tyre_advantage_ms",
            outcome="undercut_viable",
            common_causes=(
                "lap_number",
                "laps_remaining",
                "current_position",
                "rival_position",
                "gap_to_rival_ms",
                "pit_loss_estimate_ms",
                "attacker_tyre_age",
                "defender_tyre_age",
                "track_temp_c",
                "air_temp_c",
                "rainfall",
            ),
        ),
        EffectSpec(
            treatment="gap_to_rival_ms",
            outcome="undercut_viable",
            common_causes=(
                "lap_number",
                "laps_remaining",
                "current_position",
                "rival_position",
                "pit_loss_estimate_ms",
                "attacker_tyre_age",
                "defender_tyre_age",
                "tyre_age_delta",
                "track_temp_c",
                "air_temp_c",
                "rainfall",
            ),
        ),
        EffectSpec(
            treatment="tyre_age_delta",
            outcome="undercut_viable",
            common_causes=(
                "lap_number",
                "laps_remaining",
                "current_position",
                "rival_position",
                "gap_to_rival_ms",
                "pit_loss_estimate_ms",
                "track_temp_c",
                "air_temp_c",
                "rainfall",
            ),
        ),
    ]
    return [estimate_effect(data, spec) for spec in specs]


def _prepare_frame(data: Any, spec: EffectSpec) -> Any:
    required_columns = [spec.treatment, spec.outcome]
    missing = [column for column in required_columns if column not in data.columns]
    if missing:
        raise ValueError(f"missing required DoWhy column(s): {missing}")
    common_causes = [
        column
        for column in spec.common_causes
        if column in data.columns and not data[column].isna().all()
    ]
    columns = [spec.treatment, spec.outcome, *common_causes]
    frame = data.loc[:, columns].copy()
    for column in frame.columns:
        if frame[column].dtype == "bool":
            frame[column] = frame[column].astype(int)
    frame = frame.dropna()
    if frame.empty:
        raise ValueError("no rows left after dropping NULL values for DoWhy estimate")
    if frame[spec.outcome].dtype == "bool":
        frame[spec.outcome] = frame[spec.outcome].astype(int)
    return frame


def _backdoor_gml_for_frame(data: Any, spec: EffectSpec) -> str:
    common_causes = [
        column
        for column in data.columns
        if column not in {spec.treatment, spec.outcome}
    ]
    nodes = [spec.treatment, spec.outcome, *common_causes]
    node_ids = {node: index for index, node in enumerate(nodes)}
    lines = ["graph [", "  directed 1"]
    for node, node_id in node_ids.items():
        lines.extend(["  node [", f"    id {node_id}", f'    label "{node}"', "  ]"])
    lines.extend(
        [
            "  edge [",
            f"    source {node_ids[spec.treatment]}",
            f"    target {node_ids[spec.outcome]}",
            "  ]",
        ]
    )
    for cause in common_causes:
        lines.extend(
            [
                "  edge [",
                f"    source {node_ids[cause]}",
                f"    target {node_ids[spec.treatment]}",
                "  ]",
                "  edge [",
                f"    source {node_ids[cause]}",
                f"    target {node_ids[spec.outcome]}",
                "  ]",
            ]
        )
    lines.append("]")
    return "\n".join(lines)


def _dowhy_module() -> Any:
    try:
        return import_module("dowhy")
    except ImportError as exc:  # pragma: no cover - exercised in old envs.
        raise RuntimeError(
            "DoWhy is not installed. Run `make install` after the dowhy dependency "
            "is added to backend/pyproject.toml."
        ) from exc
