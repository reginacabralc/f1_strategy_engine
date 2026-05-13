#!/usr/bin/env python
"""Generate XGBoost pace-model diagnostic plots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from pitwall.ml.dataset import TARGET_COLUMN
from pitwall.ml.plots import DEFAULT_FIGURE_DIR, generate_diagnostic_plots
from pitwall.ml.train import (
    DEFAULT_DATASET_METADATA_PATH,
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_METADATA_PATH,
    DEFAULT_MODEL_PATH,
    FeatureSchema,
    encode_features,
    load_dataset,
    make_dmatrix,
    select_usable_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--dataset-meta", type=Path, default=DEFAULT_DATASET_METADATA_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--model-meta", type=Path, default=DEFAULT_MODEL_METADATA_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    parser.add_argument("--max-rows", type=int, default=5000)
    args = parser.parse_args()

    frame, _dataset_metadata = load_dataset(args.dataset, args.dataset_meta)
    metadata = json.loads(args.model_meta.read_text())
    prediction_rows = _prediction_rows(
        frame=frame,
        model_path=args.model,
        metadata=metadata,
        max_rows=args.max_rows,
    )
    paths = generate_diagnostic_plots(
        metadata=metadata,
        prediction_rows=prediction_rows,
        output_dir=args.output_dir,
    )
    print(f"Wrote {len(paths)} diagnostic plot(s) to {args.output_dir}")
    for path in paths:
        print(f"  {path}")
    return 0


def _prediction_rows(
    *,
    frame: object,
    model_path: Path,
    metadata: dict[str, object],
    max_rows: int,
) -> list[dict[str, object]]:
    import xgboost as xgb

    usable = select_usable_rows(frame).head(max_rows)  # type: ignore[arg-type]
    schema = FeatureSchema.from_json(metadata["feature_schema"])  # type: ignore[arg-type]
    encoded = encode_features(usable, schema)
    dmatrix = make_dmatrix(encoded, include_target=False)
    booster = xgb.Booster()
    booster.load_model(str(model_path))
    predictions = np.asarray(booster.predict(dmatrix), dtype=np.float64)
    rows = usable.to_dicts()
    return [
        {
            "actual_ms": float(row[TARGET_COLUMN]),
            "predicted_ms": float(prediction),
            "residual_ms": float(prediction) - float(row[TARGET_COLUMN]),
            "session_id": row.get("session_id"),
            "circuit_id": row.get("circuit_id"),
            "tyre_age": row.get("tyre_age"),
            "lap_in_stint": row.get("lap_in_stint"),
        }
        for row, prediction in zip(rows, predictions, strict=True)
    ]


if __name__ == "__main__":
    raise SystemExit(main())
