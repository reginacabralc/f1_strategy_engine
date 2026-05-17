"""XGBoost-backed PacePredictor.

The class handles the **load-from-file lifecycle** and satisfies the
:class:`~pitwall.engine.projection.PacePredictor` Protocol so it can be
hot-swapped into the engine at runtime via ``POST /api/v1/config/predictor``.

Feature construction is metadata-driven: runtime inputs are mapped into the
exact ``feature_schema.feature_names`` order saved beside the model artifact.
Categorical values unseen at runtime map to ``UNKNOWN`` when the schema exposes
that column, and missing numeric live fields are passed through as XGBoost
native missing values.

Usage (once the model file exists)::

    predictor = XGBoostPredictor.from_file("models/xgb_pace_v1.json")
    engine_loop.set_predictor(predictor, "xgboost")
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from pitwall.engine.projection import PaceContext, PacePrediction, UnsupportedContextError


class XGBoostPredictor:
    """Pace predictor backed by a trained XGBoost regressor.

    The model is expected to be serialised with
    ``XGBRegressor.save_model(path)`` (native JSON format).  An optional
    sidecar file ``<model>.meta.json`` stores training metadata
    (feature list, training date, MAE, confidence calibration) and is loaded
    automatically when present.
    """

    def __init__(self, model: Any, metadata: dict[str, Any]) -> None:
        self._model = model
        self._metadata = metadata

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: Path | str) -> XGBoostPredictor:
        """Load a serialised ``XGBRegressor`` from *path*.

        Args:
            path: Filesystem path to the ``*.json`` model file produced by
                  ``XGBRegressor.save_model()``.

        Raises:
            FileNotFoundError: Model file does not exist.
            ImportError: ``xgboost`` package is not installed.
        """
        import xgboost as xgb  # lazy import — xgboost is heavy

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"XGBoost model not found at '{path}'. "
                "Run 'make train-xgb' to train and serialise the model."
            )

        model = xgb.Booster()
        model.load_model(str(path))

        # Load companion metadata sidecar if present.
        meta_path = path.with_suffix("").with_suffix(".meta.json")
        metadata: dict[str, Any] = {}
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text())

        return cls(model, metadata)

    # ------------------------------------------------------------------
    # PacePredictor Protocol
    # ------------------------------------------------------------------

    def predict(self, ctx: PaceContext) -> PacePrediction:
        """Predict lap time for the given context.

        The trained Stream A model predicts ``lap_time_delta_ms``.  Runtime
        callers must therefore provide a live-safe ``reference_lap_time_ms``;
        the predictor returns ``reference + predicted_delta`` as the absolute
        lap-time projection consumed by the undercut engine.
        """
        feature_names = self._feature_names()
        if not feature_names:
            raise UnsupportedContextError(
                "XGBoostPredictor requires metadata.feature_schema.feature_names "
                "to construct runtime features."
            )

        target_strategy = str(self._metadata.get("target_strategy") or "")
        target_column = str(self._metadata.get("target_column") or "")
        predicts_delta = target_column == "lap_time_delta_ms" or target_strategy.endswith("delta")
        reference_lap_time_ms = ctx.reference_lap_time_ms
        if predicts_delta and reference_lap_time_ms is None:
            raise UnsupportedContextError(
                "XGBoostPredictor requires reference_lap_time_ms for "
                f"{target_strategy or target_column or 'delta'} predictions "
                f"({ctx.circuit_id!r}, {ctx.compound!r})."
            )

        import xgboost as xgb  # lazy import — xgboost is heavy

        values = self._feature_values(ctx, feature_names)
        matrix = xgb.DMatrix(
            np.asarray([values], dtype=float),
            feature_names=feature_names,
            missing=np.nan,
        )
        raw_prediction = float(self._model.predict(matrix)[0])
        if predicts_delta:
            assert reference_lap_time_ms is not None
            lap_time_ms = float(reference_lap_time_ms) + raw_prediction
        else:
            lap_time_ms = raw_prediction
        if not math.isfinite(lap_time_ms) or lap_time_ms <= 0:
            raise UnsupportedContextError(
                f"XGBoostPredictor produced invalid lap time {lap_time_ms!r} "
                f"for ({ctx.circuit_id!r}, {ctx.compound!r})."
            )
        return PacePrediction(
            predicted_lap_time_ms=round(lap_time_ms),
            confidence=self._confidence(ctx),
        )

    def is_available(self, circuit_id: str, compound: str) -> bool:
        """Return whether the predictor has enough metadata to build features.

        Per-context live references are still validated in :meth:`predict`.
        """
        return bool(self._feature_names())

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> dict[str, Any]:
        """Training metadata from the ``.meta.json`` sidecar (may be empty)."""
        return self._metadata

    # ------------------------------------------------------------------
    # Feature construction
    # ------------------------------------------------------------------

    def _feature_schema(self) -> dict[str, Any]:
        raw = self._metadata.get("feature_schema") or {}
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise UnsupportedContextError(
                    "XGBoostPredictor feature_schema is invalid JSON."
                ) from exc
            return parsed if isinstance(parsed, dict) else {}
        return raw if isinstance(raw, dict) else {}

    def _feature_names(self) -> list[str]:
        schema = self._feature_schema()
        names = schema.get("feature_names") or self._metadata.get("feature_list") or []
        return [str(name) for name in names]

    def _feature_values(self, ctx: PaceContext, feature_names: list[str]) -> list[float]:
        schema = self._feature_schema()
        categorical_features = [str(name) for name in schema.get("categorical_features") or []]
        categorical_values = schema.get("categorical_values") or {}
        numeric_values = self._numeric_values(ctx)
        category_values = self._categorical_values(ctx)

        values: list[float] = []
        for feature_name in feature_names:
            if feature_name in numeric_values:
                values.append(_float_or_nan(numeric_values[feature_name]))
                continue
            encoded = False
            for categorical_feature in categorical_features:
                prefix = f"{categorical_feature}__"
                if feature_name.startswith(prefix):
                    expected = feature_name[len(prefix):]
                    allowed = [str(v) for v in categorical_values.get(categorical_feature, [])]
                    actual = category_values.get(categorical_feature, "UNKNOWN")
                    if actual not in allowed and "UNKNOWN" in allowed:
                        actual = "UNKNOWN"
                    values.append(1.0 if actual == expected else 0.0)
                    encoded = True
                    break
            if not encoded:
                values.append(np.nan)
        return values

    def _numeric_values(self, ctx: PaceContext) -> dict[str, float | int | bool | None]:
        race_progress = ctx.race_progress
        if race_progress is None and ctx.lap_number is not None and ctx.total_laps:
            race_progress = max(0.0, min(1.0, ctx.lap_number / ctx.total_laps))
        fuel_proxy = ctx.fuel_proxy
        if fuel_proxy is None and race_progress is not None:
            fuel_proxy = max(0.0, min(1.0, 1.0 - race_progress))
        gap_to_ahead_ms = ctx.gap_to_ahead_ms
        is_in_traffic = ctx.is_in_traffic
        if is_in_traffic is None and gap_to_ahead_ms is not None:
            is_in_traffic = gap_to_ahead_ms < 1_500
        dirty_air_proxy_ms = ctx.dirty_air_proxy_ms
        if dirty_air_proxy_ms is None and gap_to_ahead_ms is not None:
            dirty_air_proxy_ms = max(0, 2_000 - gap_to_ahead_ms)
        lap_in_stint = ctx.lap_in_stint if ctx.lap_in_stint is not None else ctx.tyre_age
        stint_number = (
            ctx.stint_number if ctx.stint_number is not None else ctx.stint_position
        )
        return {
            "tyre_age": ctx.tyre_age,
            "lap_number": ctx.lap_number,
            "stint_number": stint_number,
            "lap_in_stint": lap_in_stint,
            "lap_in_stint_ratio": ctx.lap_in_stint_ratio,
            "race_progress": race_progress,
            "fuel_proxy": fuel_proxy,
            "track_temp_c": ctx.track_temp_c,
            "air_temp_c": ctx.air_temp_c,
            "humidity_pct": ctx.humidity_pct,
            "position": ctx.position,
            "gap_to_ahead_ms": gap_to_ahead_ms,
            "gap_to_leader_ms": ctx.gap_to_leader_ms,
            "is_in_traffic": is_in_traffic,
            "dirty_air_proxy_ms": dirty_air_proxy_ms,
            "driver_pace_offset_ms": (
                ctx.driver_pace_offset_ms if ctx.driver_pace_offset_ms is not None else 0.0
            ),
            "driver_pace_offset_missing": (
                True if ctx.driver_pace_offset_missing is None else ctx.driver_pace_offset_missing
            ),
        }

    def _categorical_values(self, ctx: PaceContext) -> dict[str, str]:
        return {
            "circuit_id": _slug(ctx.circuit_id),
            "compound": str(ctx.compound or "UNKNOWN").upper(),
            "driver_code": str(ctx.driver_code or "UNKNOWN").upper(),
            "team_code": _slug(ctx.team_code or "UNKNOWN"),
        }

    def _confidence(self, ctx: PaceContext) -> float:
        calibrated = self._calibrated_base_confidence()
        if calibrated is not None:
            return max(0.0, min(1.0, calibrated - self._support_penalty(ctx)))
        return self._legacy_r2_confidence()

    def _calibrated_base_confidence(self) -> float | None:
        calibration = self._metadata.get("confidence_calibration") or {}
        if not isinstance(calibration, dict):
            return None
        raw = calibration.get("base_confidence")
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, value)) if math.isfinite(value) else None

    def _legacy_r2_confidence(self) -> float:
        metrics = self._metadata.get("aggregate_metrics") or {}
        if not isinstance(metrics, dict):
            return 0.5
        raw = (
            metrics.get("holdout_r2")
            or metrics.get("xgb_r2")
            or metrics.get("validation_r2")
            or metrics.get("train_mean_holdout_r2")
        )
        if raw is None:
            return 0.5
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return 0.5

    def _support_penalty(self, ctx: PaceContext) -> float:
        schema = self._feature_schema()
        categorical_features = [str(name) for name in schema.get("categorical_features") or []]
        categorical_values = schema.get("categorical_values") or {}
        category_values = self._categorical_values(ctx)
        penalty = 0.0
        for feature in categorical_features:
            allowed = {str(value) for value in categorical_values.get(feature, [])}
            actual = category_values.get(feature, "UNKNOWN")
            if actual not in allowed:
                penalty += 0.08

        numeric_values = self._numeric_values(ctx)
        for feature in schema.get("numeric_features") or []:
            value = numeric_values.get(str(feature))
            if value is None:
                penalty += 0.015
        if numeric_values.get("driver_pace_offset_missing") is True:
            penalty += 0.05
        return min(0.45, penalty)


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _float_or_nan(value: float | int | bool | None) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)
