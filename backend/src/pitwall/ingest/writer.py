"""Writer layer for normalized ingestion outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class WriteSummary:
    output_dir: Path
    counts: dict[str, int]


class ProcessedFileWriter:
    """Write normalized records under ``data/processed/<session_id>/``."""

    def __init__(self, base_dir: Path = Path("data/processed")) -> None:
        self.base_dir = base_dir

    def write_session(self, session_id: str, outputs: dict[str, Any]) -> WriteSummary:
        output_dir = self.base_dir / session_id
        output_dir.mkdir(parents=True, exist_ok=True)

        counts: dict[str, int] = {}
        for name in ("laps", "stints", "drivers", "pit_stops", "weather"):
            records = list(outputs.get(name, []))
            counts[name] = len(records)
            self._write_records(output_dir / f"{name}.parquet", records)

        metadata = outputs.get("metadata", {})
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        counts["metadata"] = 1 if metadata else 0
        return WriteSummary(output_dir=output_dir, counts=counts)

    def _write_records(self, path: Path, records: list[dict[str, Any]]) -> None:
        try:
            import polars as pl
        except ImportError as exc:  # pragma: no cover - exercised by CLI users.
            raise RuntimeError(
                "Polars is required to write parquet outputs. Install backend dependencies first."
            ) from exc

        frame = pl.DataFrame(records) if records else pl.DataFrame()
        frame.write_parquet(path)
