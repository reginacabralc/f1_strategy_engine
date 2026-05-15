from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pitwall.ingest.manifest import (
    IngestionStatus,
    RaceManifestEntry,
    RaceManifestError,
    build_ingestion_report,
    ingest_manifest_entries,
    load_race_manifest,
    validate_manifest_entries,
)


def test_load_manifest_applies_defaults_and_filters_by_as_of_date(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    path.write_text(
        """
default_session: R
as_of_date: 2026-05-13
races:
  - year: 2024
    round: 1
    label: Bahrain Grand Prix
  - year: 2026
    round: 5
    label: Canadian Grand Prix
    race_date: 2026-05-24
  - year: 2026
    round: 1
    label: Australian Grand Prix
    race_date: 2026-03-08
    enabled: false
""",
        encoding="utf-8",
    )

    manifest = load_race_manifest(path)

    assert manifest.as_of_date == date(2026, 5, 13)
    assert manifest.entries[0].session == "R"
    assert manifest.entries[0].session_id == "bahrain_2024_R"
    assert [entry.label for entry in manifest.enabled_entries()] == ["Bahrain Grand Prix"]
    assert [entry.label for entry in manifest.skipped_future_entries()] == ["Canadian Grand Prix"]


def test_validate_manifest_rejects_duplicate_enabled_entries() -> None:
    entries = [
        RaceManifestEntry(year=2024, round_number=1, session="R", label="Bahrain"),
        RaceManifestEntry(year=2024, round_number=1, session="R", label="Bahrain duplicate"),
    ]

    with pytest.raises(RaceManifestError, match="duplicate"):
        validate_manifest_entries(entries, as_of_date=date(2026, 5, 13))


def test_ingest_manifest_entries_records_success_skips_and_failures() -> None:
    entries = [
        RaceManifestEntry(year=2024, round_number=1, session="R", label="Bahrain"),
        RaceManifestEntry(
            year=2026,
            round_number=5,
            session="R",
            label="Canada",
            race_date=date(2026, 5, 24),
        ),
        RaceManifestEntry(year=2025, round_number=1, session="R", label="Australia"),
    ]

    def fake_ingest(entry: RaceManifestEntry) -> dict[str, int]:
        if entry.year == 2025:
            raise RuntimeError("FastF1 unavailable")
        return {"laps": 100, "stints": 20}

    report = ingest_manifest_entries(
        entries,
        ingest_entry=fake_ingest,
        as_of_date=date(2026, 5, 13),
        continue_on_error=True,
    )

    assert report.summary == {
        "attempted": 2,
        "succeeded": 1,
        "skipped": 1,
        "failed": 1,
    }
    assert [item.status for item in report.items] == [
        IngestionStatus.SUCCEEDED,
        IngestionStatus.SKIPPED,
        IngestionStatus.FAILED,
    ]
    assert report.items[1].reason == "future_session"
    assert "FastF1 unavailable" in str(report.items[2].error)


def test_ingestion_report_is_json_serializable() -> None:
    report = build_ingestion_report(
        items=[],
        generated_at="2026-05-13T00:00:00+00:00",
        as_of_date=date(2026, 5, 13),
    )

    payload = report.to_json_dict()

    assert payload["generated_at"] == "2026-05-13T00:00:00+00:00"
    assert payload["as_of_date"] == "2026-05-13"
    assert payload["summary"]["attempted"] == 0
