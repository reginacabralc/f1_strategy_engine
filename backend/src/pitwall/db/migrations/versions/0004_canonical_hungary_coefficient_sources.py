"""Canonicalize Hungary coefficient source-session labels.

Revision ID: 0004_hungary_sources
Revises: 0003_canonical_hungary_slug
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_hungary_sources"
down_revision: str | None = "0003_canonical_hungary_slug"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE degradation_coefficients
        SET source_sessions = array_replace(
            source_sessions,
            'hungarian_2024_R',
            'hungary_2024_R'
        )
        WHERE source_sessions @> ARRAY['hungarian_2024_R']::text[]
        """
    )


def downgrade() -> None:
    """Leave canonical source-session labels in place on downgrade."""
