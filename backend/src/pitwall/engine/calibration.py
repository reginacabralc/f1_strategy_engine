"""Cold-tyre penalty calibration — master plan Day 9.

The default cold-tyre penalties in :data:`~pitwall.engine.projection.COLD_TYRE_PENALTIES_MS`
are hand-tuned constants ``(800, 300, 0)``.  This module provides
:func:`calibrate_cold_tyre_penalties` to compute empirical values from
the ingested historical out-lap data once Stream A has populated the DB.

Usage (once Stream A runs ``make compute-cold-tyre-penalties``)::

    # Build a list of per-driver out-lap deltas from the DB
    outlap_deltas = [
        [920, 310, 0],   # driver A pit stop: +920 ms outlap, +310 ms lap 2
        [780, 290, 0],   # driver B pit stop
        ...
    ]
    penalties = calibrate_cold_tyre_penalties(outlap_deltas)
    # Pass to project_pace:
    project_pace(..., cold_tyre_penalties=penalties)

Until the calibration is run the engine uses the module-level defaults.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median


def calibrate_cold_tyre_penalties(
    outlap_deltas: Sequence[Sequence[int]],
    n_penalty_laps: int = 3,
) -> tuple[int, ...]:
    """Estimate cold-tyre lap-time penalties from historical out-lap data.

    Args:
        outlap_deltas: Each entry is a sequence of observed deltas (ms)
            between the actual lap time and the expected clean-air reference
            for laps 1, 2, 3, … after a pit stop.  Positive = slower than
            expected.  Sequences shorter than *n_penalty_laps* are accepted;
            missing positions default to 0.
        n_penalty_laps: Number of penalty laps to return.  Laps beyond this
            are assumed penalty-free.

    Returns:
        Tuple of ``n_penalty_laps`` median penalties (ms), non-negative.
        If no observations are provided, returns ``(0,) * n_penalty_laps``.

    Example::

        >>> calibrate_cold_tyre_penalties([[800, 300, 0], [850, 280, 10]])
        (825, 290, 5)
    """
    if not outlap_deltas:
        return (0,) * n_penalty_laps

    by_position: list[list[int]] = [[] for _ in range(n_penalty_laps)]
    for deltas in outlap_deltas:
        for pos in range(n_penalty_laps):
            if pos < len(deltas):
                by_position[pos].append(deltas[pos])

    result: list[int] = []
    for pos in range(n_penalty_laps):
        if by_position[pos]:
            result.append(max(0, round(median(by_position[pos]))))
        else:
            result.append(0)

    return tuple(result)
