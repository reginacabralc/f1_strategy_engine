"""Degradation fitting utilities for Stream A."""

from pitwall.degradation.fit import fit_degradation, fit_quadratic_group
from pitwall.degradation.models import DegradationFitResult
from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor

__all__ = [
    "DegradationFitResult",
    "ScipyCoefficient",
    "ScipyPredictor",
    "fit_degradation",
    "fit_quadratic_group",
]
