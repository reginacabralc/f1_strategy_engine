"""XGBoost-backed PacePredictor — Stream A E10.

The class handles the **load-from-file lifecycle** and satisfies the
:class:`~pitwall.engine.projection.PacePredictor` Protocol so it can be
hot-swapped into the engine at runtime via ``POST /api/v1/config/predictor``.

Feature construction (tyre_age, compound encoding, circuit encoding,
driver_skill_offset, fuel_proxy, …) is Stream A's responsibility and will
be wired in E10.  Until then :meth:`predict` raises
:class:`~pitwall.engine.projection.UnsupportedContextError`, which the
engine handles gracefully as ``INSUFFICIENT_DATA`` for every pair.

Usage (once the model file exists)::

    predictor = XGBoostPredictor.from_file("models/xgb_pace_v1.json")
    engine_loop.set_predictor(predictor, "xgboost")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pitwall.engine.projection import PaceContext, PacePrediction, UnsupportedContextError


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

        .. note::
            Feature construction is wired by Stream A in E10.  Until then
            this method raises :class:`~pitwall.engine.projection.UnsupportedContextError`,
            which the engine converts to ``INSUFFICIENT_DATA``.
        """
        # Stream A wires the full feature pipeline here (E10).
        # Until then, the engine falls back to INSUFFICIENT_DATA for every pair.
        raise UnsupportedContextError(
            f"XGBoostPredictor: feature pipeline not yet implemented for "
            f"({ctx.circuit_id!r}, {ctx.compound!r}). "
            "Stream A wires feature construction in E10."
        )

    def is_available(self, circuit_id: str, compound: str) -> bool:
        """Return ``False`` until the feature pipeline is wired (E10).

        Once Stream A wires feature construction, XGBoost is available for
        all (circuit, compound) combinations — no per-cell sparse lookup needed.
        """
        return False  # feature pipeline not yet implemented

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> dict[str, Any]:
        """Training metadata from the ``.meta.json`` sidecar (may be empty)."""
        return self._metadata
