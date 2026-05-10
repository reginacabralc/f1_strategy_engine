#!/usr/bin/env python
"""Ingest one FastF1 race/session.

Despite the historical name, Day 2 intentionally supports one round only.
"""

from __future__ import annotations

from pitwall.ingest.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
