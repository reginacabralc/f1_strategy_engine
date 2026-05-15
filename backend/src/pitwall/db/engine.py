"""Minimal SQLAlchemy engine configuration."""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine


def database_url_from_env(*, load_dotenv_file: bool = True) -> str:
    """Return ``DATABASE_URL`` from environment or raise a helpful error."""

    if load_dotenv_file:
        try:
            from dotenv import load_dotenv
        except ImportError:
            pass
        else:
            load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env or export "
            "DATABASE_URL=postgresql+psycopg://pitwall:pitwall@localhost:5433/pitwall"
        )
    return database_url


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured Postgres database."""

    return create_engine(database_url or database_url_from_env(), future=True)
