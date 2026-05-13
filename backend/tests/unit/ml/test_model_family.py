from __future__ import annotations

from pitwall.ml.model_family import XGBoostModelAdapter, deferred_model_families


def test_xgboost_model_adapter_reports_default_family() -> None:
    adapter = XGBoostModelAdapter()

    assert adapter.family == "xgboost"
    assert "max_depth" in adapter.default_hyperparameters()


def test_catboost_and_lightgbm_are_deferred() -> None:
    deferred = deferred_model_families()

    assert deferred["catboost"].status == "deferred"
    assert deferred["lightgbm"].status == "deferred"
