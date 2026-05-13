"""Manifest-driven multi-race ingestion helpers."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pitwall.ingest.normalize import build_session_id

DEFAULT_MANIFEST_PATH = Path("data/reference/ml_race_manifest.yaml")
DEFAULT_REPORT_PATH = Path("data/ml/ingestion_report.json")


class RaceManifestError(ValueError):
    """Raised when the race manifest is malformed."""


class IngestionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RaceManifestEntry:
    year: int
    round_number: int
    session: str = "R"
    label: str | None = None
    enabled: bool = True
    race_date: date | None = None

    @property
    def key(self) -> tuple[int, int, str]:
        return (self.year, self.round_number, self.session)

    @property
    def display_label(self) -> str:
        return self.label or f"{self.year} round {self.round_number}"

    @property
    def session_id(self) -> str:
        event = {"EventName": self.display_label}
        return build_session_id(event, self.year, self.session)

    def is_future(self, as_of_date: date | None) -> bool:
        return as_of_date is not None and self.race_date is not None and self.race_date > as_of_date

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "round": self.round_number,
            "session": self.session,
            "label": self.label,
            "enabled": self.enabled,
            "race_date": self.race_date.isoformat() if self.race_date else None,
            "session_id": self.session_id,
        }


@dataclass(frozen=True, slots=True)
class RaceManifest:
    entries: tuple[RaceManifestEntry, ...]
    as_of_date: date | None = None
    default_session: str = "R"

    def enabled_entries(self) -> list[RaceManifestEntry]:
        return [
            entry
            for entry in self.entries
            if entry.enabled and not entry.is_future(self.as_of_date)
        ]

    def disabled_entries(self) -> list[RaceManifestEntry]:
        return [entry for entry in self.entries if not entry.enabled]

    def skipped_future_entries(self) -> list[RaceManifestEntry]:
        return [
            entry
            for entry in self.entries
            if entry.enabled and entry.is_future(self.as_of_date)
        ]


@dataclass(frozen=True, slots=True)
class IngestionReportItem:
    entry: RaceManifestEntry
    status: IngestionStatus
    counts: Mapping[str, int] | None = None
    reason: str | None = None
    error: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            **self.entry.to_json_dict(),
            "status": self.status.value,
            "counts": dict(self.counts or {}),
            "reason": self.reason,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class IngestionReport:
    items: tuple[IngestionReportItem, ...]
    generated_at: str
    as_of_date: date | None

    @property
    def summary(self) -> dict[str, int]:
        succeeded = sum(1 for item in self.items if item.status == IngestionStatus.SUCCEEDED)
        skipped = sum(1 for item in self.items if item.status == IngestionStatus.SKIPPED)
        failed = sum(1 for item in self.items if item.status == IngestionStatus.FAILED)
        return {
            "attempted": succeeded + failed,
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
        }

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "summary": self.summary,
            "items": [item.to_json_dict() for item in self.items],
        }

    def write_json(self, path: Path = DEFAULT_REPORT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json_dict(), indent=2, sort_keys=True) + "\n")


def load_race_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> RaceManifest:
    """Load a YAML race manifest from disk."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency issue for CLI users.
        raise RuntimeError("PyYAML is required to read race manifests.") from exc

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise RaceManifestError("manifest root must be a mapping")

    default_session = str(payload.get("default_session") or "R")
    as_of_date = _parse_date(payload.get("as_of_date"))
    race_payloads = payload.get("races")
    if not isinstance(race_payloads, Sequence):
        raise RaceManifestError("manifest must contain a races list")

    entries = tuple(
        _entry_from_mapping(row, default_session=default_session) for row in race_payloads
    )
    validate_manifest_entries(entries, as_of_date=as_of_date)
    return RaceManifest(entries=entries, as_of_date=as_of_date, default_session=default_session)


def validate_manifest_entries(
    entries: Iterable[RaceManifestEntry],
    *,
    as_of_date: date | None,
) -> None:
    """Validate manifest entries without touching FastF1."""

    seen_enabled: set[tuple[int, int, str]] = set()
    for entry in entries:
        if entry.year < 1950:
            raise RaceManifestError(f"invalid season for {entry.display_label}: {entry.year}")
        if entry.round_number <= 0:
            raise RaceManifestError(
                f"invalid round for {entry.display_label}: {entry.round_number}"
            )
        if not entry.session:
            raise RaceManifestError(f"missing session for {entry.display_label}")
        if entry.enabled and entry.key in seen_enabled:
            raise RaceManifestError(f"duplicate enabled race entry: {entry.key}")
        if entry.enabled:
            seen_enabled.add(entry.key)
        if entry.race_date is not None and entry.race_date.year != entry.year:
            raise RaceManifestError(
                f"race_date year does not match season for {entry.display_label}"
            )
    if as_of_date is not None and as_of_date.year < 1950:
        raise RaceManifestError(f"invalid as_of_date: {as_of_date}")


def ingest_manifest_entries(
    entries: Iterable[RaceManifestEntry],
    *,
    ingest_entry: Callable[[RaceManifestEntry], Mapping[str, int]],
    as_of_date: date | None,
    continue_on_error: bool,
) -> IngestionReport:
    """Run an injected ingestion function for entries and return a report."""

    items: list[IngestionReportItem] = []
    for entry in entries:
        if not entry.enabled:
            items.append(
                IngestionReportItem(
                    entry=entry,
                    status=IngestionStatus.SKIPPED,
                    reason="disabled",
                )
            )
            continue
        if entry.is_future(as_of_date):
            items.append(
                IngestionReportItem(
                    entry=entry,
                    status=IngestionStatus.SKIPPED,
                    reason="future_session",
                )
            )
            continue
        try:
            counts = dict(ingest_entry(entry))
        except Exception as exc:
            items.append(
                IngestionReportItem(
                    entry=entry,
                    status=IngestionStatus.FAILED,
                    error=str(exc),
                )
            )
            if not continue_on_error:
                raise
            continue
        items.append(
            IngestionReportItem(
                entry=entry,
                status=IngestionStatus.SUCCEEDED,
                counts=counts,
            )
        )

    return build_ingestion_report(
        items=items,
        generated_at=datetime.now(UTC).isoformat(),
        as_of_date=as_of_date,
    )


def build_ingestion_report(
    *,
    items: Iterable[IngestionReportItem],
    generated_at: str,
    as_of_date: date | None,
) -> IngestionReport:
    return IngestionReport(
        items=tuple(items),
        generated_at=generated_at,
        as_of_date=as_of_date,
    )


def _entry_from_mapping(row: Any, *, default_session: str) -> RaceManifestEntry:
    if not isinstance(row, Mapping):
        raise RaceManifestError(f"race entry must be a mapping: {row!r}")
    if "year" not in row or "round" not in row:
        raise RaceManifestError(f"race entry missing year/round: {row!r}")
    return RaceManifestEntry(
        year=int(row["year"]),
        round_number=int(row["round"]),
        session=str(row.get("session") or default_session),
        label=str(row["label"]) if row.get("label") is not None else None,
        enabled=bool(row.get("enabled", True)),
        race_date=_parse_date(row.get("race_date")),
    )


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise RaceManifestError(f"invalid date value: {value!r}")
