"""ML predictors for pace projection (Stream A E10).

``XGBoostPredictor`` implements the same :class:`~pitwall.engine.projection.PacePredictor`
Protocol as :class:`~pitwall.degradation.predictor.ScipyPredictor`, allowing runtime
swapping via ``POST /api/v1/config/predictor``.

Full feature engineering is wired by Stream A in E10.  Until then,
:meth:`~XGBoostPredictor.predict` raises :class:`~pitwall.engine.projection.UnsupportedContextError`
so the engine gracefully returns ``INSUFFICIENT_DATA`` for every pair.
"""
