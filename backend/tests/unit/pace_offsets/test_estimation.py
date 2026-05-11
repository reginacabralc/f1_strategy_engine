"""Unit tests for driver pace offset estimation (synthetic data only)."""

from __future__ import annotations

import pytest

from pitwall.pace_offsets.estimation import (
    compute_driver_offsets,
    compute_reference_pace,
    validate_offset_results,
)
from pitwall.pace_offsets.models import DriverOffsetResult


def _lap(circuit_id: str, compound: str, driver_code: str, lap_time_ms: float) -> dict[str, object]:
    return {
        "circuit_id": circuit_id,
        "compound": compound,
        "driver_code": driver_code,
        "lap_time_ms": lap_time_ms,
    }


# ---------------------------------------------------------------------------
# compute_reference_pace
# ---------------------------------------------------------------------------


class TestComputeReferencePace:
    def test_single_group_median(self) -> None:
        rows = [
            _lap("monaco", "SOFT", "VER", 75_000),
            _lap("monaco", "SOFT", "HAM", 76_000),
            _lap("monaco", "SOFT", "LEC", 77_000),
        ]
        refs = compute_reference_pace(rows)
        assert refs[("monaco", "SOFT")] == 76_000.0

    def test_two_groups_are_independent(self) -> None:
        rows = [
            _lap("monaco", "SOFT", "VER", 75_000),
            _lap("monaco", "MEDIUM", "VER", 77_000),
        ]
        refs = compute_reference_pace(rows)
        assert ("monaco", "SOFT") in refs
        assert ("monaco", "MEDIUM") in refs

    def test_ignores_unsupported_compound(self) -> None:
        rows = [_lap("monaco", "INTER", "VER", 80_000)]
        refs = compute_reference_pace(rows)
        assert ("monaco", "INTER") not in refs

    def test_ignores_none_lap_time(self) -> None:
        rows = [
            {"circuit_id": "monaco", "compound": "SOFT", "driver_code": "VER", "lap_time_ms": None}
        ]
        refs = compute_reference_pace(rows)
        assert not refs

    def test_ignores_missing_circuit_id(self) -> None:
        rows = [
            {"circuit_id": None, "compound": "SOFT", "driver_code": "VER", "lap_time_ms": 75_000}
        ]
        refs = compute_reference_pace(rows)
        assert not refs

    def test_median_over_even_count(self) -> None:
        rows = [
            _lap("monaco", "SOFT", "A", 74_000),
            _lap("monaco", "SOFT", "B", 76_000),
        ]
        refs = compute_reference_pace(rows)
        assert refs[("monaco", "SOFT")] == 75_000.0


# ---------------------------------------------------------------------------
# compute_driver_offsets
# ---------------------------------------------------------------------------


def _make_rows(*, n_ver: int = 5, n_ham: int = 5, n_nor: int = 3) -> list[dict[str, object]]:
    # reference = median of all laps = median([75000]*n_ver + [77000]*n_ham + [76000]*n_nor)
    rows: list[dict[str, object]] = []
    for _ in range(n_ver):
        rows.append(_lap("monaco", "SOFT", "VER", 75_000))
    for _ in range(n_ham):
        rows.append(_lap("monaco", "SOFT", "HAM", 77_000))
    for _ in range(n_nor):
        rows.append(_lap("monaco", "SOFT", "NOR", 76_000))
    return rows


class TestComputeDriverOffsets:
    def test_fitted_offsets_correct_sign(self) -> None:
        rows = _make_rows()
        results = compute_driver_offsets(rows, min_samples=5)
        fitted = {r.driver_code: r for r in results if r.status == "fitted"}
        assert "VER" in fitted
        assert "HAM" in fitted
        assert fitted["VER"].offset_ms is not None and fitted["VER"].offset_ms < 0
        assert fitted["HAM"].offset_ms is not None and fitted["HAM"].offset_ms > 0

    def test_offset_values_are_relative_to_median_reference(self) -> None:
        # 5 VER laps at 74_000 and 5 HAM laps at 76_000 → reference = 75_000
        rows = [_lap("monaco", "SOFT", "VER", 74_000) for _ in range(5)]
        rows += [_lap("monaco", "SOFT", "HAM", 76_000) for _ in range(5)]
        results = compute_driver_offsets(rows, min_samples=5)
        fitted = {r.driver_code: r for r in results if r.status == "fitted"}
        assert fitted["VER"].offset_ms is not None
        assert fitted["HAM"].offset_ms is not None
        assert abs(fitted["VER"].offset_ms - (-1_000.0)) < 0.01
        assert abs(fitted["HAM"].offset_ms - 1_000.0) < 0.01

    def test_skips_driver_with_insufficient_samples(self) -> None:
        rows = _make_rows()
        results = compute_driver_offsets(rows, min_samples=5)
        skipped = {r.driver_code: r for r in results if r.status == "skipped_insufficient_data"}
        assert "NOR" in skipped
        assert skipped["NOR"].n_samples == 3

    def test_min_samples_threshold_is_respected(self) -> None:
        rows = _make_rows()
        results = compute_driver_offsets(rows, min_samples=3)
        fitted = {r.driver_code: r for r in results if r.status == "fitted"}
        assert "NOR" in fitted

    def test_n_samples_reflects_actual_lap_count(self) -> None:
        rows = _make_rows()
        results = compute_driver_offsets(rows, min_samples=5)
        ver = next(r for r in results if r.driver_code == "VER")
        assert ver.n_samples == 5

    def test_returns_empty_list_on_no_rows(self) -> None:
        assert compute_driver_offsets([]) == []

    def test_multi_circuit_offsets_are_independent(self) -> None:
        rows = [_lap("monaco", "SOFT", "VER", 75_000) for _ in range(5)]
        rows += [_lap("bahrain", "SOFT", "VER", 90_000) for _ in range(5)]
        rows += [_lap("bahrain", "SOFT", "HAM", 91_000) for _ in range(5)]
        results = compute_driver_offsets(rows, min_samples=5)
        monaco_ver = next(
            r for r in results if r.driver_code == "VER" and r.circuit_id == "monaco"
        )
        bahrain_ver = next(
            r for r in results if r.driver_code == "VER" and r.circuit_id == "bahrain"
        )
        assert monaco_ver.offset_ms == 0.0
        assert bahrain_ver.offset_ms is not None and bahrain_ver.offset_ms < 0


# ---------------------------------------------------------------------------
# validate_offset_results
# ---------------------------------------------------------------------------


class TestValidateOffsetResults:
    def _fitted(self, offset_ms: float = -500.0) -> DriverOffsetResult:
        return DriverOffsetResult(
            driver_code="VER",
            circuit_id="monaco",
            compound="SOFT",
            status="fitted",
            offset_ms=offset_ms,
            n_samples=10,
        )

    def test_accepts_valid_offset(self) -> None:
        validate_offset_results([self._fitted()])  # no exception

    def test_rejects_empty_fitted_list(self) -> None:
        skipped = DriverOffsetResult(
            driver_code="VER",
            circuit_id="monaco",
            compound="SOFT",
            status="skipped_insufficient_data",
            n_samples=3,
        )
        with pytest.raises(ValueError, match="no driver offsets"):
            validate_offset_results([skipped])

    def test_rejects_absurd_positive_offset(self) -> None:
        with pytest.raises(ValueError, match="absurd"):
            validate_offset_results([self._fitted(offset_ms=15_000.0)])

    def test_rejects_absurd_negative_offset(self) -> None:
        with pytest.raises(ValueError, match="absurd"):
            validate_offset_results([self._fitted(offset_ms=-15_000.0)])

    def test_accepts_offset_at_boundary(self) -> None:
        validate_offset_results([self._fitted(offset_ms=10_000.0)])

    def test_rejects_none_offset_on_fitted_row(self) -> None:
        bad = DriverOffsetResult(
            driver_code="VER",
            circuit_id="monaco",
            compound="SOFT",
            status="fitted",
            offset_ms=None,
            n_samples=10,
        )
        with pytest.raises(ValueError, match="None"):
            validate_offset_results([bad])
