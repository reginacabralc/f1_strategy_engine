from __future__ import annotations

from typing import Any

from pitwall.api import main as api_main
from pitwall.engine.loop import EngineLoop
from pitwall.engine.pit_loss import PitLossTable


class _FakeConnection:
    pass


class _FakeEngine:
    def connect(self) -> _FakeEngine:
        return self

    def __enter__(self) -> _FakeConnection:
        return _FakeConnection()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_build_pit_loss_table_loads_persisted_estimates(monkeypatch: Any) -> None:
    expected: PitLossTable = {"monaco": {"mercedes": 20_115, None: 20_561}}

    monkeypatch.setattr(api_main, "create_db_engine", lambda: _FakeEngine())
    monkeypatch.setattr(api_main, "load_pit_loss_table", lambda connection: expected)

    assert api_main._build_pit_loss_table() == expected


def test_build_pit_loss_table_falls_back_to_empty_table(monkeypatch: Any) -> None:
    def _raise() -> None:
        raise RuntimeError("DATABASE_URL missing")

    monkeypatch.setattr(api_main, "create_db_engine", _raise)

    assert api_main._build_pit_loss_table() == {}


def test_create_app_initializes_engine_with_persisted_pit_loss_table(
    monkeypatch: Any,
) -> None:
    expected: PitLossTable = {"bahrain": {"ferrari": 24_311, None: 25_071}}

    monkeypatch.setattr(api_main, "_build_pit_loss_table", lambda: expected)

    app = api_main.create_app()

    assert app.state.engine_loop._pit_loss_table == expected


def test_engine_loop_can_swap_pit_loss_table_at_runtime() -> None:
    loop = EngineLoop.__new__(EngineLoop)
    replacement: PitLossTable = {"hungary": {"mclaren": 21_252, None: 20_393}}

    loop.set_pit_loss_table(replacement)

    assert loop._pit_loss_table == replacement
