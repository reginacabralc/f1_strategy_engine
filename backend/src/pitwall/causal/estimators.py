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


@dataclass(frozen=True, slots=True)
class RefutationResult:
    treatment: str
    outcome: str
    refuter_name: str
    original_estimate: float
    refuted_estimate: float | None
    delta: float | None
    stability: str


@dataclass(frozen=True, slots=True)
class EffectWithRefutations:
    estimate: EffectEstimate
    refutations: tuple[RefutationResult, ...]


DEFAULT_REFUTERS = (
    "random_common_cause",
    "placebo_treatment_refuter",
    "data_subset_refuter",
)


def load_causal_dataset(path: Path = DEFAULT_DATASET_PATH) -> Any:
    """Load the causal dataset as a pandas DataFrame for DoWhy."""

    if not path.exists():
        raise FileNotFoundError(
            f"causal dataset not found at {path}. Run `make build-causal-dataset` first."
        )
    polars = import_module("polars")
    pandas = import_module("pandas")
    return pandas.DataFrame(polars.read_parquet(path).to_dicts())


def estimate_effect_with_refuters(
    data: Any,
    spec: EffectSpec,
    *,
    graph: str | None = None,
    refuter_names: tuple[str, ...] = DEFAULT_REFUTERS,
    random_seed: int = 7,
) -> EffectWithRefutations:
    """Estimate one effect and run the Phase 7 DoWhy refuters."""

    fitted = _fit_effect(data, spec, graph=graph)
    estimate = _effect_estimate_from_fitted(fitted, spec)
    refutations = tuple(
        _refute_estimate(
            fitted,
            spec,
            estimate,
            refuter_name=refuter_name,
            random_seed=random_seed,
        )
        for refuter_name in refuter_names
    )
    return EffectWithRefutations(estimate=estimate, refutations=refutations)


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

    fitted = _fit_effect(data, spec, graph=graph)
    return _effect_estimate_from_fitted(fitted, spec)


def estimate_default_effects(data: Any) -> list[EffectEstimate]:
    """Run the Phase 6 default effects."""

    return [estimate_effect(data, spec) for spec in default_effect_specs()]


def estimate_default_effects_with_refuters(data: Any) -> list[EffectWithRefutations]:
    """Run the default Phase 6 effects plus Phase 7 refuters."""

    return [estimate_effect_with_refuters(data, spec) for spec in default_effect_specs()]


def default_effect_specs() -> list[EffectSpec]:
    """Return the default DoWhy effect specs used by Phase 6/7."""

    return [
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
        if frame[column].dtype == "bool" or _object_bool_column(frame[column]):
            frame[column] = frame[column].map(
                lambda value: None if value is None else int(bool(value))
            )
        else:
            pandas = import_module("pandas")
            frame[column] = pandas.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna()
    if frame.empty:
        raise ValueError("no rows left after dropping NULL values for DoWhy estimate")
    if frame[spec.outcome].dtype == "bool":
        frame[spec.outcome] = frame[spec.outcome].astype(int)
    return frame


def _object_bool_column(series: Any) -> bool:
    values = [value for value in series.dropna().unique()]
    return bool(values) and all(isinstance(value, bool) for value in values)


def _fit_effect(data: Any, spec: EffectSpec, *, graph: str | None) -> dict[str, Any]:
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
    return {
        "frame": frame,
        "model": model,
        "estimand": estimand,
        "estimate": estimate,
    }


def _effect_estimate_from_fitted(fitted: dict[str, Any], spec: EffectSpec) -> EffectEstimate:
    return EffectEstimate(
        treatment=spec.treatment,
        outcome=spec.outcome,
        method_name=spec.method_name,
        n_rows=len(fitted["frame"]),
        estimand_type=str(fitted["estimand"].estimand_type),
        estimate_value=float(fitted["estimate"].value),
    )


def _refute_estimate(
    fitted: dict[str, Any],
    spec: EffectSpec,
    estimate: EffectEstimate,
    *,
    refuter_name: str,
    random_seed: int,
) -> RefutationResult:
    kwargs: dict[str, object] = {"random_seed": random_seed}
    if refuter_name == "data_subset_refuter":
        kwargs["subset_fraction"] = 0.8
        kwargs["num_simulations"] = 10
    elif refuter_name == "random_common_cause":
        kwargs["num_simulations"] = 10
    elif refuter_name == "placebo_treatment_refuter":
        kwargs["placebo_type"] = "permute"
        kwargs["num_simulations"] = 10

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, module="dowhy")
        warnings.filterwarnings("ignore", category=RuntimeWarning, module="statsmodels")
        refutation = fitted["model"].refute_estimate(
            fitted["estimand"],
            fitted["estimate"],
            method_name=refuter_name,
            **kwargs,
        )
    refuted_estimate = _refuted_value(refutation)
    delta = (
        abs(refuted_estimate - estimate.estimate_value)
        if refuted_estimate is not None
        else None
    )
    return RefutationResult(
        treatment=spec.treatment,
        outcome=spec.outcome,
        refuter_name=refuter_name,
        original_estimate=estimate.estimate_value,
        refuted_estimate=refuted_estimate,
        delta=delta,
        stability=_stability_label(estimate.estimate_value, refuted_estimate),
    )


def _refuted_value(refutation: Any) -> float | None:
    value = getattr(refutation, "new_effect", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stability_label(original: float, refuted: float | None) -> str:
    if refuted is None:
        return "unsupported"
    absolute_delta = abs(refuted - original)
    scale = max(abs(original), 1e-9)
    relative_delta = absolute_delta / scale
    if absolute_delta <= 0.001 or relative_delta <= 0.25:
        return "stable"
    if relative_delta <= 1.0:
        return "sensitive"
    return "unstable"


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
