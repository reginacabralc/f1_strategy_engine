"""Small FastF1 boundary for one-session ingestion."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path("data/cache")
FASTF1_CACHE_ENV = "FASTF1_CACHE_DIR"


@dataclass(frozen=True, slots=True)
class FastF1SessionData:
    year: int
    round_number: int
    session_code: str
    event: dict[str, Any]
    session_start: datetime | None
    laps: Any
    results: Any
    weather: Any


def cache_dir_from_env() -> Path:
    """Return configured FastF1 cache path, defaulting to ``data/cache``."""

    return Path(os.environ.get(FASTF1_CACHE_ENV, str(DEFAULT_CACHE_DIR)))


def enable_fastf1_cache(cache_dir: Path | None = None) -> Path:
    """Create and enable the FastF1 cache directory."""

    cache_path = cache_dir or cache_dir_from_env()
    cache_path.mkdir(parents=True, exist_ok=True)
    try:
        fastf1 = import_module("fastf1")
    except ImportError as exc:  # pragma: no cover - exercised by CLI users.
        raise RuntimeError(
            "FastF1 is not installed. Install backend dependencies first, then rerun ingestion."
        ) from exc

    fastf1.Cache.enable_cache(str(cache_path))
    return cache_path


def load_race_session(
    *,
    year: int,
    round_number: int,
    session_code: str,
    cache_dir: Path | None = None,
) -> FastF1SessionData:
    """Load one FastF1 session for a year/round/session tuple."""

    enable_fastf1_cache(cache_dir)
    try:
        fastf1 = import_module("fastf1")
    except ImportError as exc:  # pragma: no cover - guarded above.
        raise RuntimeError("FastF1 is not installed.") from exc

    session = fastf1.get_session(year, round_number, session_code)
    try:
        session.load(laps=True, telemetry=False, weather=True, messages=False)
    except TypeError:
        session.load(telemetry=False, weather=True)
    except Exception as exc:
        raise RuntimeError(
            f"FastF1 could not load {year} round {round_number} session {session_code}: {exc}"
        ) from exc

    event = _event_to_dict(getattr(session, "event", {}))
    return FastF1SessionData(
        year=year,
        round_number=round_number,
        session_code=session_code,
        event=event,
        session_start=_session_start(session, event),
        laps=getattr(session, "laps", None),
        results=getattr(session, "results", None),
        weather=getattr(session, "weather_data", None),
    )


def _event_to_dict(event: Any) -> dict[str, Any]:
    if hasattr(event, "to_dict"):
        return dict(event.to_dict())
    if isinstance(event, dict):
        return dict(event)
    return {}


def _session_start(session: Any, event: dict[str, Any]) -> datetime | None:
    for source, keys in (
        (session, ("date", "Date")),
        (event, ("SessionStartDate", "EventDate", "EventDateUtc", "EventDateLocal")),
    ):
        for key in keys:
            value = getattr(source, key, None) if not isinstance(source, dict) else source.get(key)
            if isinstance(value, datetime):
                return value
            to_pydatetime = getattr(value, "to_pydatetime", None)
            if callable(to_pydatetime):
                converted = to_pydatetime()
                if isinstance(converted, datetime):
                    return converted
    return None
