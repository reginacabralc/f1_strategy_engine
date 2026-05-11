"""Engine loop — the main processing pipeline (master plan §6.10).

The :class:`EngineLoop` reads events from :attr:`~pitwall.core.topics.Topics.events`,
applies each to :class:`~pitwall.engine.state.RaceState`, and on every
``lap_complete`` event:

1. Resets each driver's ``undercut_score`` to ``None``.
2. Calls :func:`~pitwall.engine.undercut.evaluate_undercut` for every
   relevant pair returned by
   :func:`~pitwall.engine.state.compute_relevant_pairs`.
3. Stores the computed score on the attacker's
   :attr:`~pitwall.engine.state.DriverState.undercut_score`.
4. Broadcasts ``alert`` messages for viable undercuts.
5. Broadcasts a ``snapshot`` message with the updated race state.

The loop runs as a background :mod:`asyncio` task.  It consumes from
``topics.events`` which is fed by :class:`~pitwall.engine.replay_manager.ReplayManager`.

The loop is agnostic to *how* messages are delivered — it delegates to a
:class:`Broadcaster` Protocol.  In production the broadcaster is a
:class:`~pitwall.api.connections.ConnectionManager`; in tests a simple mock.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from pitwall.core.topics import Topics
from pitwall.engine.pit_loss import PitLossTable, lookup_pit_loss
from pitwall.engine.projection import PacePredictor
from pitwall.engine.state import DriverState, RaceState, compute_relevant_pairs
from pitwall.engine.undercut import UndercutDecision, evaluate_undercut

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Broadcaster Protocol
# ---------------------------------------------------------------------------


class Broadcaster(Protocol):
    """Deliver JSON-serialisable messages to all connected WebSocket clients."""

    async def broadcast_json(self, data: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# EngineLoop
# ---------------------------------------------------------------------------


class EngineLoop:
    """Runs the per-lap undercut calculation and broadcasts results.

    Thread safety: designed to run in a single asyncio event loop; do not
    share between threads.
    """

    def __init__(
        self,
        topics: Topics,
        broadcaster: Broadcaster,
        predictor: PacePredictor,
        pit_loss_table: PitLossTable,
        predictor_name: str = "scipy",
    ) -> None:
        self._topics = topics
        self._broadcaster = broadcaster
        self._predictor = predictor
        self._pit_loss_table = pit_loss_table
        self._predictor_name = predictor_name
        self._state = RaceState()
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def state(self) -> RaceState:
        """Read-only snapshot of the current race state."""
        return self._state

    def set_predictor(self, predictor: PacePredictor, name: str = "scipy") -> None:
        """Swap the active predictor at runtime (used by lifespan / config endpoint)."""
        self._predictor = predictor
        self._predictor_name = name

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="engine-loop")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def predictor_name(self) -> str:
        """Name of the currently active pace predictor."""
        return self._predictor_name

    # ------------------------------------------------------------------
    # Background task
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            event = await self._topics.events.get()
            try:
                self._state.apply(event)
                if event["type"] == "lap_complete":
                    await self._on_lap_complete()
            except Exception:
                logger.exception("Engine loop error on %s event", event.get("type"))

    async def _on_lap_complete(self) -> None:
        # Reset scores from the previous lap.
        for d in self._state.drivers.values():
            d.undercut_score = None

        track_status = self._state.track_status

        if track_status in ("SC", "VSC"):
            # §6.9: Safety Car / Virtual Safety Car — suspend undercut calculation.
            # Broadcast one session-level alert so the frontend can show the flag.
            alert_type = "SUSPENDED_SC" if track_status == "SC" else "SUSPENDED_VSC"
            await self._broadcaster.broadcast_json(
                _suspension_message(alert_type, self._state)
            )
        else:
            # Normal racing conditions: evaluate every relevant pair.
            circuit_id = self._state.circuit_id
            for atk, def_ in compute_relevant_pairs(self._state):
                pit_loss = lookup_pit_loss(circuit_id, atk.team_code, self._pit_loss_table)
                decision = evaluate_undercut(self._state, atk, def_, self._predictor, pit_loss)
                self._state.drivers[atk.driver_code].undercut_score = decision.score

                if decision.should_alert:
                    await self._broadcaster.broadcast_json(_alert_message(decision, self._state))

        # Always broadcast the snapshot so clients stay in sync.
        await self._broadcaster.broadcast_json(_snapshot_message(self._state, self._predictor_name))


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _driver_to_dict(d: DriverState) -> dict[str, Any]:
    return {
        "driver_code": d.driver_code,
        "team_code": d.team_code,
        "position": d.position,
        "gap_to_leader_ms": d.gap_to_leader_ms,
        "gap_to_ahead_ms": d.gap_to_ahead_ms,
        "last_lap_ms": d.last_lap_ms,
        "compound": d.compound,
        "tyre_age": d.tyre_age,
        "is_in_pit": d.is_in_pit,
        "is_lapped": d.is_lapped,
        "last_pit_lap": d.last_pit_lap,
        "stint_number": d.stint_number,
        "undercut_score": d.undercut_score,
    }


def _snapshot_message(state: RaceState, predictor_name: str) -> dict[str, Any]:
    return {
        "v": 1,
        "type": "snapshot",
        "ts": _now_iso(),
        "payload": {
            "session_id": state.session_id,
            "current_lap": state.current_lap,
            "track_status": state.track_status,
            "track_temp_c": state.track_temp_c,
            "air_temp_c": state.air_temp_c,
            "humidity_pct": state.humidity_pct,
            "drivers": sorted(
                [_driver_to_dict(d) for d in state.drivers.values()],
                key=lambda d: (d["position"] is None, d["position"]),
            ),
            "active_predictor": predictor_name,
            "last_event_ts": (state.last_event_ts.isoformat() if state.last_event_ts else None),
        },
    }


def _suspension_message(alert_type: str, state: RaceState) -> dict[str, Any]:
    """Session-level suspension alert (SC or VSC active)."""
    return {
        "v": 1,
        "type": "alert",
        "ts": _now_iso(),
        "payload": {
            "alert_type": alert_type,
            "attacker": None,
            "defender": None,
            "score": 0.0,
            "confidence": 0.0,
            "estimated_gain_ms": 0,
            "pit_loss_ms": 0,
            "gap_actual_ms": None,
            "session_id": state.session_id,
            "current_lap": state.current_lap,
        },
    }


def _alert_message(decision: UndercutDecision, state: RaceState) -> dict[str, Any]:
    return {
        "v": 1,
        "type": "alert",
        "ts": _now_iso(),
        "payload": {
            "alert_type": decision.alert_type,
            "attacker": decision.attacker_code,
            "defender": decision.defender_code,
            "score": round(decision.score, 4),
            "confidence": round(decision.confidence, 4),
            "estimated_gain_ms": decision.estimated_gain_ms,
            "pit_loss_ms": decision.pit_loss_ms,
            "gap_actual_ms": decision.gap_actual_ms,
            "session_id": state.session_id,
            "current_lap": state.current_lap,
        },
    }
