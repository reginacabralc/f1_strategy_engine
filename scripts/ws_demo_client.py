#!/usr/bin/env python3
"""Demo WebSocket client — streams live messages from /ws/v1/live.

Usage::

    # default: connect to local dev server
    python scripts/ws_demo_client.py

    # custom URL
    python scripts/ws_demo_client.py ws://localhost:8000/ws/v1/live

Requires the ``websockets`` package::

    pip install websockets

Then start the backend and a replay before running this client::

    make up && make seed
    curl -s -X POST http://localhost:8000/api/v1/replay/start \\
         -H 'Content-Type: application/json' \\
         -d '{"session_id": "monaco_2024_R", "speed_factor": 30}'
"""

from __future__ import annotations

import asyncio
import json
import sys


async def stream(url: str) -> None:
    try:
        import websockets  # type: ignore[import-untyped]
    except ImportError:
        print("Install websockets first:  pip install websockets", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to {url} …  (Ctrl-C to quit)\n")
    async with websockets.connect(url) as ws:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                print(raw)
                continue

            msg_type = msg.get("type", "?")
            ts = msg.get("ts", "")[:19]  # trim to seconds

            if msg_type == "alert":
                p = msg.get("payload", {})
                print(
                    f"[{ts}] ALERT  {p.get('alert_type')}  "
                    f"{p.get('attacker')} → {p.get('defender')}  "
                    f"score={p.get('score', 0):.3f}  "
                    f"conf={p.get('confidence', 0):.3f}  "
                    f"gain={p.get('estimated_gain_ms', 0)} ms"
                )
            elif msg_type == "snapshot":
                p = msg.get("payload", {})
                n_drivers = len(p.get("drivers", []))
                print(
                    f"[{ts}] SNAP   lap={p.get('current_lap')}  "
                    f"status={p.get('track_status')}  "
                    f"drivers={n_drivers}  "
                    f"predictor={p.get('active_predictor')}"
                )
            else:
                print(f"[{ts}] {msg_type.upper()}")


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws/v1/live"
    try:
        asyncio.run(stream(url))
    except KeyboardInterrupt:
        print("\nDisconnected.")


if __name__ == "__main__":
    main()
