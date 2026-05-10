"""Data-access layer.

Each repository is a Protocol with at least one concrete implementation.
The Protocol is the seam between the API layer (Stream B) and the
persistence layer (Stream A). V1 ships in-memory implementations
populated with fixture data so the API works end-to-end before the
SQL layer is wired on Day 3.
"""

from pitwall.repositories.sessions import (
    InMemorySessionRepository,
    SessionRepository,
    SessionRow,
)
from pitwall.repositories.sql import SqlSessionEventLoader, SqlSessionRepository

__all__ = [
    "InMemorySessionRepository",
    "SessionRepository",
    "SessionRow",
    "SqlSessionEventLoader",
    "SqlSessionRepository",
]
