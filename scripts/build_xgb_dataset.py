#!/usr/bin/env python
"""Build the Day 7 XGBoost lap-level pace dataset."""

from __future__ import annotations

from pathlib import Path

from pitwall.db.engine import create_db_engine
from pitwall.degradation.dataset import DEMO_SESSION_IDS
from pitwall.ml.dataset import build_dataset_from_db, write_dataset

DATASET_PATH = Path("data/ml/xgb_pace_dataset.parquet")
METADATA_PATH = Path("data/ml/xgb_pace_dataset.meta.json")


def main() -> int:
    engine = create_db_engine()
    with engine.begin() as connection:
        result = build_dataset_from_db(connection, session_ids=DEMO_SESSION_IDS)

    write_dataset(result, dataset_path=DATASET_PATH, metadata_path=METADATA_PATH)

    print(f"Wrote {DATASET_PATH}")
    print(f"Wrote {METADATA_PATH}")
    print(f"Rows: {result.metadata['row_count']}")
    print(f"Usable rows: {result.metadata['usable_row_count']}")
    print(f"Sessions: {', '.join(result.metadata['sessions_included'])}")
    print("Folds:")
    for fold in result.metadata["folds"]:
        print(
            f"  {fold['fold_id']}: holdout={fold['holdout_session_id']} "
            f"train={','.join(fold['train_session_ids'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
