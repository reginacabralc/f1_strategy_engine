"""Pit-loss lookup for the undercut engine.

The pit loss is the wall-clock time a driver loses during a pit stop
versus staying out: the sum of the pit lane transit time, the stationary
time during the tyre change, and any time lost in the pit-lane speed limiter
zone relative to racing speed.

V1 uses a constant lookup table populated by Stream A's
``scripts/compute_pit_loss.py`` once the demo races are ingested. Until
that table is populated the fallback constant of 21 s is used, which is
typical for Monaco (a slow-pit-lane circuit).  Stream A's Day 6 task
("pit loss por (circuito, equipo) calculado y persistido") writes the real
estimates.

Table shape
-----------
``PitLossTable = {circuit_id: {team_code: pit_loss_ms, None: circuit_avg}}``

``None`` as a team key stores the circuit-level median — used when the
specific team is not in the table.  All values are in whole milliseconds.
"""

from __future__ import annotations

DEFAULT_PIT_LOSS_MS: int = 21_000
"""Fallback pit-loss used when no estimate exists for a (circuit, team) pair.

21 000 ms is a conservative upper-bound for most modern F1 circuits.
Monaco typically sees 22-24 s; high-speed circuits (Monza, Spa) can be
as low as 18 s.  The bound errs on the side of *underestimating* the
viability of an undercut, which is the safer direction.
"""

PitLossTable = dict[str, dict[str | None, int]]
"""Pit-loss estimates keyed by ``{circuit_id: {team_code | None: ms}}``.

``None`` as the team key stores the circuit-level fallback (median across
all teams with enough samples).
"""


def lookup_pit_loss(
    circuit_id: str,
    team_code: str | None,
    table: PitLossTable,
    *,
    default: int = DEFAULT_PIT_LOSS_MS,
) -> int:
    """Return the best available pit-loss estimate for ``(circuit, team)``.

    Fallback chain:
    1. Exact ``(circuit_id, team_code)`` entry.
    2. Circuit-level median (``table[circuit_id][None]``).
    3. ``default`` (hard-coded constant).

    Args:
        circuit_id:  Circuit slug (e.g. ``"monaco"``).
        team_code:   Team slug (e.g. ``"mercedes"``), or ``None`` if unknown.
        table:       Populated by Stream A; may be empty in V1.
        default:     Used when the table has no entry for this circuit.

    Returns:
        Pit-loss estimate in whole milliseconds.
    """
    circuit_table = table.get(circuit_id, {})
    if team_code is not None and team_code in circuit_table:
        return circuit_table[team_code]
    if None in circuit_table:
        return circuit_table[None]
    return default
