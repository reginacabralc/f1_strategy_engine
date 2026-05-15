"""XGBoost-backed PacePredictor — Stream A E10.

The class loads the native Booster plus its metadata sidecar and reconstructs
the same feature schema used during training.  The model predicts
``lap_time_delta_ms``; the predictor adds the runtime reference pace from the
sidecar to return an absolute lap-time prediction.

Usage::

    predictor = XGBoostPredictor.from_file("models/xgb_pace_v1.json")
    engine_loop.set_predictor(predictor, "xgboost")
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, SupportsFloat, cast

from pitwall.engine.projection import PaceContext, PacePrediction, UnsupportedContextError
from pitwall.ml.train import FeatureSchema, encode_features, make_dmatrix

VALID_RUNTIME_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})


class XGBoostPredictor:
    """Pace predictor backed by a trained XGBoost regressor.

    The model is expected to be serialised with
    ``XGBRegressor.save_model(path)`` (native JSON format).  An optional
    sidecar file ``<model>.meta.json`` stores training metadata
    (feature list, training date, MAE, R²) and is loaded automatically
    when present.
    """

    def __init__(self, model: Any, metadata: dict[str, Any]) -> None:
        self._model = model
        self._metadata = metadata
        self._schema = _schema_from_metadata(metadata)
        self._runtime_reference_pace = _mapping(metadata.get("runtime_reference_pace"))
        self._runtime_driver_offsets = _mapping(metadata.get("runtime_driver_offsets"))
        self._confidence = _confidence_from_metadata(metadata)

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
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"XGBoost model not found at '{path}'. "
                "Run 'make train-xgb' to train and serialise the model."
            )

        import xgboost as xgb  # lazy import — xgboost is heavy

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
        """Predict absolute lap time for the given context."""

        schema = getattr(self, "_schema", None)
        if schema is None:
            raise UnsupportedContextError("XGBoostPredictor: metadata is missing feature_schema")
        compound = str(ctx.compound).upper()
        if compound not in VALID_RUNTIME_COMPOUNDS:
            raise UnsupportedContextError(f"XGBoostPredictor: unsupported compound {compound!r}")
        reference_lap_time_ms = self._reference_lap_time_ms(ctx.circuit_id, compound)
        if reference_lap_time_ms is None:
            raise UnsupportedContextError(
                f"XGBoostPredictor: no runtime reference pace for "
                f"({ctx.circuit_id!r}, {compound!r})"
            )

        row = self._feature_row(ctx, compound, reference_lap_time_ms)
        polars = __import__("polars")
        encoded = encode_features(polars.DataFrame([row]), schema)
        dmatrix = make_dmatrix(encoded, include_target=False)
        delta_ms = float(self._model.predict(dmatrix)[0])
        predicted_lap_time_ms = max(1, round(reference_lap_time_ms + delta_ms))
        return PacePrediction(
            predicted_lap_time_ms=predicted_lap_time_ms,
            confidence=getattr(self, "_confidence", 0.0),
        )

    def is_available(self, circuit_id: str, compound: str) -> bool:
        """Return whether the model has the metadata needed for this context."""

        return (
            getattr(self, "_schema", None) is not None
            and str(compound).upper() in VALID_RUNTIME_COMPOUNDS
            and self._reference_lap_time_ms(circuit_id, str(compound).upper()) is not None
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> dict[str, Any]:
        """Training metadata from the ``.meta.json`` sidecar (may be empty)."""
        return self._metadata

    def _feature_row(
        self,
        ctx: PaceContext,
        compound: str,
        reference_lap_time_ms: float,
    ) -> dict[str, object]:
        lap_number = _lap_number(ctx)
        race_progress = (
            max(0.0, min(1.0, lap_number / ctx.total_laps))
            if lap_number is not None and ctx.total_laps is not None and ctx.total_laps > 0
            else None
        )
        driver_offset = self._driver_offset_ms(ctx.driver_code, ctx.circuit_id, compound)
        lap_in_stint = ctx.lap_in_stint if ctx.lap_in_stint is not None else ctx.tyre_age
        return {
            "session_id": None,
            "circuit_id": ctx.circuit_id,
            "driver_code": ctx.driver_code,
            "team_code": ctx.team_code,
            "compound": compound,
            "tyre_age": ctx.tyre_age,
            "lap_number": lap_number,
            "stint_number": ctx.stint_position,
            "lap_in_stint": lap_in_stint,
            "lap_in_stint_ratio": None,
            "race_progress": race_progress,
            "fuel_proxy": (1.0 - race_progress) if race_progress is not None else None,
            "track_temp_c": ctx.track_temp_c,
            "air_temp_c": ctx.air_temp_c,
            "position": None,
            "gap_to_ahead_ms": None,
            "gap_to_leader_ms": None,
            "is_in_traffic": False,
            "dirty_air_proxy_ms": 0,
            "driver_pace_offset_ms": driver_offset,
            "driver_pace_offset_missing": driver_offset == 0.0,
            "reference_lap_time_ms": reference_lap_time_ms,
        }

    def _reference_lap_time_ms(self, circuit_id: str, compound: str) -> float | None:
        reference_pace = _mapping(getattr(self, "_runtime_reference_pace", {}))
        by_circuit = _mapping(reference_pace.get("by_circuit_compound"))
        by_compound = _mapping(reference_pace.get("by_compound"))
        value = by_circuit.get(_compound_key(circuit_id, compound))
        if value is None:
            value = by_compound.get(compound)
        return _float_or_none(value)

    def _driver_offset_ms(self, driver_code: str, circuit_id: str, compound: str) -> float:
        driver_offsets = _mapping(getattr(self, "_runtime_driver_offsets", {}))
        exact = _mapping(driver_offsets.get("exact"))
        fallback = _mapping(driver_offsets.get("by_driver_compound"))
        value = exact.get(_driver_offset_key(driver_code, circuit_id, compound))
        if value is None:
            value = fallback.get(f"{driver_code}|{compound}")
        return _float_or_none(value) or 0.0


def _schema_from_metadata(metadata: dict[str, Any]) -> FeatureSchema | None:
    payload = metadata.get("feature_schema")
    if not isinstance(payload, dict):
        return None
    return FeatureSchema.from_json(payload)


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _confidence_from_metadata(metadata: dict[str, Any]) -> float:
    aggregate = _mapping(metadata.get("aggregate_metrics"))
    r2 = _float_or_none(aggregate.get("holdout_r2"))
    if r2 is None:
        r2 = _float_or_none(aggregate.get("xgb_r2"))
    if r2 is None:
        return 0.0
    return max(0.0, min(1.0, r2))


def _lap_number(ctx: PaceContext) -> int | None:
    if ctx.total_laps is None or ctx.laps_remaining is None:
        return None
    return max(1, ctx.total_laps - ctx.laps_remaining)


def _compound_key(circuit_id: str, compound: str) -> str:
    return f"{circuit_id}|{compound.upper()}"


def _driver_offset_key(driver_code: str, circuit_id: str, compound: str) -> str:
    return f"{driver_code}|{circuit_id}|{compound.upper()}"


def _float_or_none(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, str | int | float) and not hasattr(value, "__float__"):
        return None
    try:
        number = float(cast(str | int | float | SupportsFloat, value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
