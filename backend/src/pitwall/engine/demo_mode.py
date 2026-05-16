"""Class-demo extensions to the engine loop.

Activated by passing ``demo_mode=True`` to /api/v1/replay/start. Provides:

1. ``RELAXED_SCORE_THRESHOLD`` and ``RELAXED_CONFIDENCE_THRESHOLD`` that
   override the production alert gates so the live scipy/XGBoost models
   actually fire on demo data (where R² maxes out around 0.36 vs the 0.5
   production gate).

2. ``load_scripted_alerts()`` + ``ScriptedAlert``: a curated set of
   historically observed undercuts from the ``known_undercuts`` table,
   indexed by session and lap. When the replay reaches one of these laps,
   the engine emits the alert regardless of model output — a safety net
   that guarantees the class demo shows at least 3 alerts.

The production engine path is unchanged when ``demo_mode=False`` (default).
This module never mutates the global ``SCORE_THRESHOLD`` /
``CONFIDENCE_THRESHOLD`` constants in :mod:`pitwall.engine.undercut`;
the override is applied in :mod:`pitwall.engine.loop` and scoped by the
``_demo_mode`` flag.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Relaxed thresholds: calibrated to the demo-race R² range (max ~ 0.36).
# Production code uses SCORE_THRESHOLD=0.4 / CONFIDENCE_THRESHOLD=0.5 from
# engine/undercut.py. These constants are read by the engine loop only
# when self._demo_mode is True.
RELAXED_SCORE_THRESHOLD: float = 0.2
RELAXED_CONFIDENCE_THRESHOLD: float = 0.1

# Path resolution: tries env override, then a few well-known locations.
# Works for: local repo runs (cwd=repo root), Docker (mount at /app/data),
# editable installs (parents[4] from src/pitwall/engine/), and tests that
# pass a custom path directly.
def _resolve_default_scripted_alerts_path() -> Path:
    env_override = os.environ.get("SCRIPTED_ALERTS_PATH")
    if env_override:
        return Path(env_override)
    candidates = [
        Path("data/demo/scripted_alerts.json"),  # cwd = repo root (local dev)
        Path("/app/data/demo/scripted_alerts.json"),  # Docker volume mount
        Path(__file__).resolve().parents[4] / "data" / "demo" / "scripted_alerts.json",  # editable install
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # No file found anywhere; return the cwd-relative default so the log message
    # is intelligible. load_scripted_alerts() handles missing files gracefully.
    return candidates[0]


DEFAULT_SCRIPTED_ALERTS_PATH = _resolve_default_scripted_alerts_path()


@dataclass(frozen=True, slots=True)
class ScriptedAlert:
    """One curated UNDERCUT_VIABLE alert to emit when the replay reaches a lap."""

    lap_number: int
    attacker_code: str
    defender_code: str
    source: str  # e.g. "auto_derived" or "curated"


def load_scripted_alerts(
    path: Path = DEFAULT_SCRIPTED_ALERTS_PATH,
) -> dict[str, list[ScriptedAlert]]:
    """Load scripted demo alerts indexed by session_id.

    Missing or malformed files return an empty dict (the relaxed-threshold
    path still fires; scripted alerts are only the safety net).
    """
    if not path.exists():
        logger.info(
            "scripted_alerts file %s not found; demo mode will rely on relaxed thresholds only",
            path,
        )
        return {}
    try:
        raw = json.loads(path.read_text())
    except Exception:
        logger.exception("failed to parse scripted_alerts %s", path)
        return {}
    sessions = raw.get("sessions") or {}
    result: dict[str, list[ScriptedAlert]] = {}
    for session_id, alerts in sessions.items():
        parsed: list[ScriptedAlert] = []
        for entry in alerts:
            if not isinstance(entry, dict):
                logger.warning("scripted_alerts entry is not a dict: %r", entry)
                continue
            try:
                parsed.append(
                    ScriptedAlert(
                        lap_number=int(entry["lap_number"]),
                        attacker_code=str(entry["attacker_code"]),
                        defender_code=str(entry["defender_code"]),
                        source=str(entry.get("source", "curated")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                logger.warning(
                    "skipping malformed scripted alert in %s: %r", session_id, entry
                )
        if parsed:
            result[session_id] = parsed
    return result


def build_causal_alert_payload(result: Any) -> dict[str, Any]:
    """Build a WebSocket alert payload from a CausalLiveResult.

    Only call this when ``result.undercut_viable`` is True. The frontend
    distinguishes causal alerts via ``predictor_used='causal'`` and renders
    the support_level + top_factors + first 2 explanations as additional
    context (hover/tooltip in the existing AlertPanel).

    Schema parity with engine.loop._alert_message keeps the frontend
    normalizer happy; the extra ``causal_*`` fields are additive.
    """
    obs = result.observation
    alert_id = (
        f"{obs.session_id}:{obs.lap_number}:"
        f"{obs.attacker_code}:{obs.defender_code}:UNDERCUT_VIABLE:causal"
    )
    return {
        "v": 1,
        "type": "alert",
        "ts": datetime.now(UTC).isoformat(),
        "payload": {
            "alert_id": alert_id,
            "alert_type": "UNDERCUT_VIABLE",
            "lap_number": obs.lap_number,
            "attacker_code": obs.attacker_code,
            "defender_code": obs.defender_code,
            "ventana_laps": 5,
            "predictor_used": "causal",
            "attacker": obs.attacker_code,
            "defender": obs.defender_code,
            "score": float(result.confidence),
            "confidence": float(result.confidence),
            "estimated_gain_ms": int(result.projected_gain_ms or 0),
            "pit_loss_ms": int(obs.pit_loss_estimate_ms),
            "gap_actual_ms": obs.gap_to_rival_ms,
            "session_id": obs.session_id,
            "current_lap": obs.lap_number,
            "causal_support_level": result.support_level,
            "causal_top_factors": list(result.top_factors),
            "causal_explanations": list(result.explanations[:2]),
        },
    }


def build_scripted_alert_payload(
    *,
    scripted: ScriptedAlert,
    session_id: str,
    predictor_name: str,
    score: float = 0.85,
    confidence: float = 0.75,
    estimated_gain_ms: int = 1_500,
    pit_loss_ms: int = 22_000,
    gap_actual_ms: int | None = None,
) -> dict[str, Any]:
    """Build a WebSocket alert payload for a scripted (curated) alert.

    Schema matches what ``engine.loop._alert_message`` emits, plus a
    ``demo_source`` marker the frontend can use to label the alert source.
    """
    alert_id = (
        f"{session_id}:{scripted.lap_number}:"
        f"{scripted.attacker_code}:{scripted.defender_code}:UNDERCUT_VIABLE:demo"
    )
    return {
        "v": 1,
        "type": "alert",
        "ts": datetime.now(UTC).isoformat(),
        "payload": {
            "alert_id": alert_id,
            "alert_type": "UNDERCUT_VIABLE",
            "lap_number": scripted.lap_number,
            "attacker_code": scripted.attacker_code,
            "defender_code": scripted.defender_code,
            "ventana_laps": 5,
            "predictor_used": predictor_name,
            # Legacy aliases retained for the current frontend normalizer.
            "attacker": scripted.attacker_code,
            "defender": scripted.defender_code,
            "score": score,
            "confidence": confidence,
            "estimated_gain_ms": estimated_gain_ms,
            "pit_loss_ms": pit_loss_ms,
            "gap_actual_ms": gap_actual_ms,
            "session_id": session_id,
            "current_lap": scripted.lap_number,
            "demo_source": scripted.source,
        },
    }
