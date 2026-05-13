"""Minimal model-family adapter surface for pace-model experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pitwall.ml.train import default_hyperparameters


class ModelFamilyAdapter(Protocol):
    @property
    def family(self) -> str: ...

    def default_hyperparameters(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class DeferredModelFamily:
    family: str
    status: str
    reason: str


class XGBoostModelAdapter:
    @property
    def family(self) -> str:
        return "xgboost"

    def default_hyperparameters(self) -> dict[str, Any]:
        return default_hyperparameters()


def deferred_model_families() -> dict[str, DeferredModelFamily]:
    reason = (
        "Deferred to V2 to avoid adding install/platform risk before the temporal "
        "data coverage and leakage-safe validation problem is solved."
    )
    return {
        "catboost": DeferredModelFamily("catboost", "deferred", reason),
        "lightgbm": DeferredModelFamily("lightgbm", "deferred", reason),
    }
