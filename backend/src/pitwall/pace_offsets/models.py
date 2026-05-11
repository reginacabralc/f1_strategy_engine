"""Typed records for driver pace offset estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MIN_SAMPLES = 5
MAX_ABSURD_OFFSET_MS = 10_000
VALID_OFFSET_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})

OffsetStatus = Literal["fitted", "skipped_insufficient_data"]


@dataclass(frozen=True, slots=True)
class DriverOffsetResult:
    """Pace offset for one driver/circuit/compound group.

    offset_ms < 0 → driver is faster than the group median reference.
    offset_ms > 0 → driver is slower than the group median reference.
    """

    driver_code: str
    circuit_id: str
    compound: str
    status: OffsetStatus
    offset_ms: float | None = None
    n_samples: int = 0
    iqr_ms: float | None = None
    std_ms: float | None = None

    @property
    def is_usable(self) -> bool:
        return self.status == "fitted" and self.offset_ms is not None
