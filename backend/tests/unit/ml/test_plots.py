from __future__ import annotations

from pathlib import Path

from pitwall.ml.plots import generate_diagnostic_plots


def test_generate_diagnostic_plots_writes_expected_files(tmp_path: Path) -> None:
    metadata = {
        "fold_metrics": [
            {
                "fold_id": "fold_001",
                "holdout_mae_ms": 900.0,
                "holdout_rmse_ms": 1200.0,
                "zero_holdout_mae_ms": 1000.0,
                "zero_holdout_rmse_ms": 1300.0,
                "train_mean_holdout_mae_ms": 950.0,
                "target_distribution": {"count": 2, "mean_ms": 10.0, "std_ms": 3.0},
            }
        ],
        "top_feature_importances": [
            {"feature": "tyre_age", "gain": 4.0},
            {"feature": "fuel_proxy", "gain": 2.0},
        ],
    }
    prediction_rows = [
        {
            "actual_ms": 100.0,
            "predicted_ms": 90.0,
            "residual_ms": -10.0,
            "session_id": "s1",
            "circuit_id": "bahrain",
            "tyre_age": 4,
            "lap_in_stint": 3,
        },
        {
            "actual_ms": 200.0,
            "predicted_ms": 220.0,
            "residual_ms": 20.0,
            "session_id": "s2",
            "circuit_id": "jeddah",
            "tyre_age": 9,
            "lap_in_stint": 8,
        },
    ]

    paths = generate_diagnostic_plots(
        metadata=metadata,
        prediction_rows=prediction_rows,
        output_dir=tmp_path,
    )

    names = {path.name for path in paths}
    assert "fold_metrics.png" in names
    assert "predicted_vs_actual.png" in names
    assert "residual_distribution.png" in names
    assert all(path.exists() for path in paths)
