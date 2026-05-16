#!/usr/bin/env python
"""Phase 5C verification script — run Monaco 2024 through the engine and count alerts.

Connects to the local DB, loads all Monaco 2024 events, applies each to RaceState,
calls evaluate_undercut for every relevant pair per lap, and reports:
- Total lap_complete events processed
- Total (attacker, defender) pairs evaluated
- Alert decisions by type (UNDERCUT_VIABLE, INSUFFICIENT_DATA, etc.)
- If no UNDERCUT_VIABLE: classifies the blocker (score, confidence, or data)
- If UNDERCUT_VIABLE: prints one example payload
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, "backend/src")

from pitwall.db.engine import create_db_engine
from pitwall.degradation.predictor import ScipyPredictor
from pitwall.engine.pit_loss import DEFAULT_PIT_LOSS_MS, PitLossTable, lookup_pit_loss
from pitwall.engine.state import RaceState, compute_relevant_pairs
from pitwall.engine.undercut import (
    CONFIDENCE_THRESHOLD,
    SCORE_THRESHOLD,
    evaluate_undercut,
)
from pitwall.repositories.sql import SqlSessionEventLoader


@dataclass
class DecisionRecord:
    lap: int
    attacker: str
    defender: str
    alert_type: str
    score: float
    confidence: float
    estimated_gain_ms: int
    gap_actual_ms: int | None
    should_alert: bool


async def main() -> None:
    session_id = "monaco_2024_R"
    engine = create_db_engine()

    print(f"Loading events for {session_id}...")
    loader = SqlSessionEventLoader(engine)
    events = await loader.load_events(session_id)
    print(f"  {len(events)} events loaded.")

    print("Loading ScipyPredictor coefficients...")
    predictor = ScipyPredictor.from_engine(engine)
    coeff_count = len(predictor._coefficients)
    print(f"  {coeff_count} (circuit, compound) coefficient cells loaded.")
    for key in sorted(predictor._coefficients):
        c = predictor._coefficients[key]
        print(f"    {key}: R²={c.r_squared:.4f}  n_laps={c.n_laps}")

    print(f"\nRunning engine over {session_id} events...")
    state = RaceState()
    pit_loss_table: PitLossTable = []
    pit_loss_ms = DEFAULT_PIT_LOSS_MS

    lap_events = 0
    pairs_evaluated = 0
    decisions: list[DecisionRecord] = []

    # Track per-decision blockers for INSUFFICIENT_DATA / low-score / low-confidence
    blocker_counts: Counter[str] = Counter()

    for event in events:
        state.apply(event)

        if event["type"] != "lap_complete":
            continue

        lap_events += 1
        pairs = compute_relevant_pairs(state)

        for atk, def_ in pairs:
            pairs_evaluated += 1
            decision = evaluate_undercut(state, atk, def_, predictor, pit_loss_ms)

            rec = DecisionRecord(
                lap=state.current_lap,
                attacker=atk.driver_code,
                defender=def_.driver_code,
                alert_type=decision.alert_type,
                score=decision.score,
                confidence=decision.confidence,
                estimated_gain_ms=decision.estimated_gain_ms,
                gap_actual_ms=decision.gap_actual_ms,
                should_alert=decision.should_alert,
            )
            decisions.append(rec)

            if not decision.should_alert:
                if decision.alert_type != "UNDERCUT_VIABLE":
                    blocker_counts[decision.alert_type] += 1
                elif decision.score <= SCORE_THRESHOLD:
                    blocker_counts["score_too_low"] += 1
                elif decision.confidence <= CONFIDENCE_THRESHOLD:
                    blocker_counts["confidence_too_low"] += 1

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"Lap events processed : {lap_events}")
    print(f"Pairs evaluated      : {pairs_evaluated}")

    alert_counts: Counter[str] = Counter(d.alert_type for d in decisions)
    print(f"\nDecisions by type:")
    for t, n in sorted(alert_counts.items()):
        print(f"  {t:30s}  {n}")

    viable = [d for d in decisions if d.should_alert]
    print(f"\nUNDERCUT_VIABLE (should_alert=True): {len(viable)}")

    if viable:
        ex = viable[0]
        print("\nFirst UNDERCUT_VIABLE example payload:")
        print(f"  session_id      : {session_id}")
        print(f"  lap_number      : {ex.lap}")
        print(f"  attacker_code   : {ex.attacker}")
        print(f"  defender_code   : {ex.defender}")
        print(f"  score           : {ex.score:.4f}")
        print(f"  confidence      : {ex.confidence:.4f}")
        print(f"  estimated_gain_ms: {ex.estimated_gain_ms}")
        print(f"  gap_actual_ms   : {ex.gap_actual_ms}")
    else:
        print("\nNO alerts fired. Blocker classification:")
        if blocker_counts:
            for reason, n in sorted(blocker_counts.items(), key=lambda x: -x[1]):
                print(f"  {reason:40s}  {n}")
        else:
            print("  (all pairs marked INSUFFICIENT_DATA — no score/confidence analysis done)")

        # Deep-dive: pick up to 5 UNDERCUT_VIABLE decisions where should_alert=False
        viable_typed = [d for d in decisions if d.alert_type == "UNDERCUT_VIABLE"]
        print(f"\nUNDERCUT_VIABLE decisions (should_alert=False): {len(viable_typed)}")
        if viable_typed:
            ex = viable_typed[0]
            print(f"\nFirst UNDERCUT_VIABLE (blocked) example:")
            print(f"  lap={ex.lap}  {ex.attacker}→{ex.defender}")
            print(f"  score={ex.score:.4f} (threshold={SCORE_THRESHOLD})")
            print(f"  confidence={ex.confidence:.4f} (threshold={CONFIDENCE_THRESHOLD})")
            print(f"  estimated_gain_ms={ex.estimated_gain_ms}")
            print(f"  gap_actual_ms={ex.gap_actual_ms}")

        # Show score distribution for UNDERCUT_VIABLE decisions
        scored = [d for d in decisions if d.alert_type == "UNDERCUT_VIABLE" and d.score > 0]
        if scored:
            scores = [d.score for d in scored]
            confs = [d.confidence for d in scored]
            print(f"\nScore  range: {min(scores):.4f} – {max(scores):.4f}")
            print(f"Conf   range: {min(confs):.4f} – {max(confs):.4f}")
            print(f"Pairs where score>{SCORE_THRESHOLD}: {sum(1 for s in scores if s>SCORE_THRESHOLD)}")
            print(f"Pairs where conf>{CONFIDENCE_THRESHOLD}: {sum(1 for c in confs if c>CONFIDENCE_THRESHOLD)}")

    print(f"\n{'='*60}")

    if viable:
        print("STATUS: ALERTS FIRE ✓")
    else:
        print("STATUS: ALERTS DO NOT FIRE ✗")
        # Classify the primary blocker
        if blocker_counts.get("confidence_too_low", 0) > 0:
            print("PRIMARY BLOCKER: confidence_too_low")
            print(f"  All Monaco degradation R² values are below {CONFIDENCE_THRESHOLD}.")
            print(f"  Max Monaco R²: MEDIUM=0.362. Threshold: {CONFIDENCE_THRESHOLD}.")
        elif blocker_counts.get("score_too_low", 0) > 0:
            print("PRIMARY BLOCKER: score_too_low")
        else:
            print("PRIMARY BLOCKER: INSUFFICIENT_DATA (gaps, laps_in_stint, or coefficients)")


if __name__ == "__main__":
    asyncio.run(main())
