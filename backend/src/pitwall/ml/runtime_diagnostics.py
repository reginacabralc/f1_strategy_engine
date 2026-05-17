"""Runtime feature parity diagnostics for XGBoost pace prediction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pitwall.engine.projection import PaceContext
from pitwall.ml.predictor import XGBoostPredictor


@dataclass(frozen=True, slots=True)
class XGBoostRuntimeFeatureDiagnostic:
    """Feature support report for one runtime :class:`PaceContext`."""

    feature_names: tuple[str, ...]
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    missing_numeric_features: tuple[str, ...]
    unknown_categorical_features: dict[str, str]
    predicts_delta: bool
    requires_reference_for_prediction: bool
    reference_lap_time_available: bool
    reference_lap_time_feature_present: bool
    driver_pace_offset_missing: bool


def diagnose_xgboost_runtime_features(
    predictor: XGBoostPredictor,
    ctx: PaceContext,
) -> XGBoostRuntimeFeatureDiagnostic:
    """Report how a runtime context maps onto the trained XGBoost schema."""

    schema = _feature_schema(predictor)
    feature_names = tuple(str(name) for name in schema.get("feature_names") or [])
    numeric_features = tuple(str(name) for name in schema.get("numeric_features") or [])
    categorical_features = tuple(str(name) for name in schema.get("categorical_features") or [])
    categorical_values = _categorical_values(schema)
    numeric_values = predictor._numeric_values(ctx)
    category_values = predictor._categorical_values(ctx)

    missing_numeric = tuple(
        feature
        for feature in numeric_features
        if _is_missing_numeric(numeric_values.get(feature))
    )
    unknown_categoricals: dict[str, str] = {}
    for feature in categorical_features:
        allowed = categorical_values.get(feature, set())
        actual = category_values.get(feature, "UNKNOWN")
        if actual not in allowed:
            unknown_categoricals[feature] = actual

    target_column = str(predictor.metadata.get("target_column") or "")
    target_strategy = str(predictor.metadata.get("target_strategy") or "")
    predicts_delta = target_column == "lap_time_delta_ms" or target_strategy.endswith("delta")
    return XGBoostRuntimeFeatureDiagnostic(
        feature_names=feature_names,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        missing_numeric_features=missing_numeric,
        unknown_categorical_features=unknown_categoricals,
        predicts_delta=predicts_delta,
        requires_reference_for_prediction=predicts_delta,
        reference_lap_time_available=ctx.reference_lap_time_ms is not None,
        reference_lap_time_feature_present="reference_lap_time_ms" in feature_names,
        driver_pace_offset_missing=bool(
            numeric_values.get("driver_pace_offset_missing")
        ),
    )


def _feature_schema(predictor: XGBoostPredictor) -> dict[str, Any]:
    schema = predictor._feature_schema()
    return schema if isinstance(schema, dict) else {}


def _categorical_values(schema: dict[str, Any]) -> dict[str, set[str]]:
    raw = schema.get("categorical_values") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(feature): {str(value) for value in values}
        for feature, values in raw.items()
        if isinstance(values, list)
    }


def _is_missing_numeric(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return not math.isfinite(value)
    return False
