"""Degradation fitting utilities for Stream A."""

from pitwall.degradation.fit import fit_degradation, fit_quadratic_group
from pitwall.degradation.models import DegradationFitResult

__all__ = ["DegradationFitResult", "fit_degradation", "fit_quadratic_group"]
