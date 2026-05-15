"""Matplotlib diagnostics for XGBoost pace-model artifacts."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_FIGURE_DIR = Path("reports/figures")


def generate_diagnostic_plots(
    *,
    metadata: Mapping[str, Any],
    prediction_rows: Sequence[Mapping[str, Any]],
    output_dir: Path = DEFAULT_FIGURE_DIR,
) -> list[Path]:
    """Generate model diagnostic plots and return written paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        _plot_fold_metrics(metadata, output_dir / "fold_metrics.png"),
        _plot_predicted_vs_actual(prediction_rows, output_dir / "predicted_vs_actual.png"),
        _plot_residual_distribution(prediction_rows, output_dir / "residual_distribution.png"),
        _plot_residuals_by_session(prediction_rows, output_dir / "residuals_by_session.png"),
        _plot_error_by_tyre_age(prediction_rows, output_dir / "error_by_tyre_age.png"),
        _plot_feature_importance(metadata, output_dir / "feature_importance.png"),
        _plot_target_distribution(metadata, output_dir / "target_distribution_by_fold.png"),
    ]
    return [path for path in paths if path.exists()]


def _pyplot() -> Any:
    os.environ.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "pitwall-matplotlib"),
    )
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    return plt


def _plot_fold_metrics(metadata: Mapping[str, Any], path: Path) -> Path:
    plt = _pyplot()
    folds = list(metadata.get("fold_metrics", []))
    labels = [
        str(row.get("fold_id") or row.get("holdout_session") or idx)
        for idx, row in enumerate(folds, start=1)
    ]
    x = list(range(len(folds)))
    plt.figure(figsize=(8, 4))
    plt.plot(
        x,
        [float(row.get("holdout_mae_ms", 0.0)) for row in folds],
        marker="o",
        label="XGBoost MAE",
    )
    plt.plot(
        x,
        [float(row.get("zero_holdout_mae_ms", 0.0)) for row in folds],
        marker="o",
        label="Zero MAE",
    )
    plt.plot(
        x,
        [float(row.get("train_mean_holdout_mae_ms", 0.0)) for row in folds],
        marker="o",
        label="Train mean MAE",
    )
    plt.xticks(x, labels, rotation=30, ha="right")
    plt.ylabel("milliseconds")
    plt.title("Fold MAE comparison")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path


def _plot_predicted_vs_actual(rows: Sequence[Mapping[str, Any]], path: Path) -> Path:
    plt = _pyplot()
    actual = [float(row["actual_ms"]) for row in rows]
    predicted = [float(row["predicted_ms"]) for row in rows]
    plt.figure(figsize=(5, 5))
    plt.scatter(actual, predicted, alpha=0.7)
    if actual:
        lower = min([*actual, *predicted])
        upper = max([*actual, *predicted])
        plt.plot([lower, upper], [lower, upper], color="black", linewidth=1)
    plt.xlabel("Actual delta ms")
    plt.ylabel("Predicted delta ms")
    plt.title("Predicted vs actual")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path


def _plot_residual_distribution(rows: Sequence[Mapping[str, Any]], path: Path) -> Path:
    plt = _pyplot()
    residuals = [float(row["residual_ms"]) for row in rows]
    plt.figure(figsize=(7, 4))
    plt.hist(residuals, bins=min(30, max(1, len(residuals))))
    plt.xlabel("Residual ms")
    plt.ylabel("Count")
    plt.title("Residual distribution")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path


def _plot_residuals_by_session(rows: Sequence[Mapping[str, Any]], path: Path) -> Path:
    plt = _pyplot()
    grouped: dict[str, list[float]] = {}
    for row in rows:
        label = str(row.get("session_id") or row.get("circuit_id") or "unknown")
        grouped.setdefault(label, []).append(abs(float(row["residual_ms"])))
    labels = list(grouped)
    values = [sum(items) / len(items) for items in grouped.values()]
    plt.figure(figsize=(8, 4))
    plt.bar(labels, values)
    plt.ylabel("Mean absolute residual ms")
    plt.title("Residuals by session")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path


def _plot_error_by_tyre_age(rows: Sequence[Mapping[str, Any]], path: Path) -> Path:
    plt = _pyplot()
    x = [float(row.get("tyre_age") or row.get("lap_in_stint") or 0.0) for row in rows]
    y = [abs(float(row["residual_ms"])) for row in rows]
    plt.figure(figsize=(7, 4))
    plt.scatter(x, y, alpha=0.7)
    plt.xlabel("Tyre age")
    plt.ylabel("Absolute residual ms")
    plt.title("Error by tyre age")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path


def _plot_feature_importance(metadata: Mapping[str, Any], path: Path) -> Path:
    plt = _pyplot()
    rows = list(metadata.get("top_feature_importances", []))[:15]
    labels = [str(row.get("feature")) for row in rows]
    values = [float(row.get("gain", 0.0)) for row in rows]
    plt.figure(figsize=(8, 4))
    plt.barh(labels[::-1], values[::-1])
    plt.xlabel("Gain")
    plt.title("Top feature importances")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path


def _plot_target_distribution(metadata: Mapping[str, Any], path: Path) -> Path:
    plt = _pyplot()
    rows = list(metadata.get("fold_metrics", []))
    labels = [str(row.get("fold_id") or index) for index, row in enumerate(rows, start=1)]
    means = [
        float((row.get("target_distribution") or {}).get("mean_ms", 0.0))
        for row in rows
    ]
    plt.figure(figsize=(8, 4))
    plt.bar(labels, means)
    plt.ylabel("Mean target delta ms")
    plt.title("Target distribution by validation fold")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path
