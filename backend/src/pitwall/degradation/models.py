"""Typed records for degradation fitting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

VALID_FIT_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})
FITTABLE_STATUSES = frozenset({"fitted", "fitted_warn"})

FitStatus = Literal[
    "fitted",
    "fitted_warn",
    "skipped_insufficient_data",
    "skipped_fit_error",
]


@dataclass(frozen=True, slots=True)
class DegradationFitResult:
    """Quadratic degradation fit output for one circuit/session compound group."""

    circuit_id: str
    compound: str
    source_sessions: tuple[str, ...]
    status: FitStatus
    a: float | None = None
    b: float | None = None
    c: float | None = None
    r2: float | None = None
    rmse_ms: float | None = None
    n_laps: int = 0
    min_tyre_age: int | None = None
    max_tyre_age: int | None = None
    model_type: str = "quadratic_v1"
    warning: str | None = None

    @property
    def is_fittable(self) -> bool:
        return (
            self.status in FITTABLE_STATUSES
            and self.a is not None
            and self.b is not None
            and self.c is not None
        )
