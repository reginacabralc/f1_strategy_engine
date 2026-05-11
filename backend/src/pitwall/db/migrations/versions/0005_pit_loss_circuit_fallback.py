"""Allow circuit-level pit-loss fallback rows.

Revision ID: 0005_pit_loss_fallback
Revises: 0004_hungary_sources
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_pit_loss_fallback"
down_revision: str | None = "0004_hungary_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE pit_loss_estimates DROP CONSTRAINT IF EXISTS pit_loss_estimates_pkey")
    op.execute("ALTER TABLE pit_loss_estimates ALTER COLUMN team_code DROP NOT NULL")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_pit_loss_estimates_circuit_team
        ON pit_loss_estimates (circuit_id, COALESCE(team_code, '__circuit__'))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_pit_loss_estimates_circuit_team")
    op.execute("DELETE FROM pit_loss_estimates WHERE team_code IS NULL")
    op.execute("ALTER TABLE pit_loss_estimates ALTER COLUMN team_code SET NOT NULL")
    op.execute(
        """
        ALTER TABLE pit_loss_estimates
        ADD PRIMARY KEY (circuit_id, team_code)
        """
    )
