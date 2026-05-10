"""FastAPI dependency providers.

These are the seams Stream A will drop into when the SQL repositories
are ready. Today the providers return the in-memory implementations so
the API works end-to-end without a database.

Tests should override providers with ``app.dependency_overrides`` rather
than monkey-patching this module:

    app.dependency_overrides[get_session_repository] = lambda: my_repo
"""

from __future__ import annotations

from functools import lru_cache

from pitwall.repositories.sessions import (
    InMemorySessionRepository,
    SessionRepository,
)


@lru_cache(maxsize=1)
def get_session_repository() -> SessionRepository:
    """Return the active :class:`SessionRepository`.

    V1 default: in-memory fixture covering the three demo races.
    Stream A will switch this to a SQL-backed repository on Day 3 by
    swapping the body of this function (or by reading the active
    implementation from :class:`~pitwall.core.config.Settings`).
    """
    return InMemorySessionRepository()
