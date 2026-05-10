"""Scipy-backed implementation of the PacePredictor contract."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

from pitwall.engine.projection import PaceContext, PacePrediction, UnsupportedContextError
from pitwall.ingest.normalize import clean_nulls, slugify

COEFFICIENT_SQL = """
    SELECT
        circuit_id,
        compound,
        a,
        b,
        c,
        r_squared,
        n_laps
    FROM degradation_coefficients
    WHERE model_type = 'quadratic_v1'
"""


class CoefficientConnection(Protocol):
    def execute(self, statement: object) -> Iterable[Any]: ...


@dataclass(frozen=True, slots=True)
class ScipyCoefficient:
    """Persisted quadratic coefficient for one circuit/compound cell."""

    circuit_id: str
    compound: str
    a: float
    b: float
    c: float
    r_squared: float | None
    n_laps: int | None = None

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> ScipyCoefficient:
        cleaned = clean_nulls(row)
        return cls(
            circuit_id=_normalise_circuit(str(cleaned["circuit_id"])),
            compound=str(cleaned["compound"]).upper(),
            a=float(cleaned["a"]),
            b=float(cleaned["b"]),
            c=float(cleaned["c"]),
            r_squared=float(cleaned["r_squared"]) if cleaned.get("r_squared") is not None else None,
            n_laps=int(cleaned["n_laps"]) if cleaned.get("n_laps") is not None else None,
        )

    def predict_ms(self, tyre_age: int) -> int:
        return max(1, round(self.a + self.b * tyre_age + self.c * tyre_age * tyre_age))

    @property
    def confidence(self) -> float:
        if self.r_squared is None:
            return 0.0
        return max(0.0, min(1.0, self.r_squared))


class ScipyPredictor:
    """Baseline predictor using persisted quadratic degradation coefficients."""

    def __init__(self, coefficients: Iterable[ScipyCoefficient]) -> None:
        self._coefficients = {
            (_normalise_circuit(coefficient.circuit_id), coefficient.compound.upper()): coefficient
            for coefficient in coefficients
        }

    @classmethod
    def from_connection(cls, connection: CoefficientConnection) -> ScipyPredictor:
        rows = connection.execute(_sql_text(COEFFICIENT_SQL))
        return cls(
            ScipyCoefficient.from_mapping(
                dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            )
            for row in rows
        )

    @classmethod
    def from_engine(cls, engine: Any) -> ScipyPredictor:
        with engine.connect() as connection:
            return cls.from_connection(connection)

    def predict(self, ctx: PaceContext) -> PacePrediction:
        coefficient = self._coefficients.get(_key(ctx.circuit_id, ctx.compound))
        if coefficient is None:
            raise UnsupportedContextError(
                f"no scipy coefficient for ({ctx.circuit_id}, {ctx.compound})"
            )
        return PacePrediction(
            predicted_lap_time_ms=coefficient.predict_ms(ctx.tyre_age),
            confidence=coefficient.confidence,
        )

    def is_available(self, circuit_id: str, compound: str) -> bool:
        return _key(circuit_id, compound) in self._coefficients


def _key(circuit_id: str, compound: str) -> tuple[str, str]:
    return (_normalise_circuit(circuit_id), compound.upper())


def _normalise_circuit(circuit_id: str) -> str:
    return slugify(circuit_id)


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
