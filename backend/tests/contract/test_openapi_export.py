"""Contract: the FastAPI-generated OpenAPI must agree with the static
spec in ``docs/interfaces/openapi_v1.yaml`` for every path the backend
implements.

Day 2 implements three paths: ``/health``, ``/ready``, and
``/api/v1/sessions``. The static spec also describes the Day-3+ paths
(``/api/v1/replay/start``, ``/api/v1/replay/stop``,
``/api/v1/sessions/{session_id}/snapshot``,
``/api/v1/degradation``, ``/api/v1/backtest/{session_id}``,
``/api/v1/config/predictor``); those are not yet implemented and are
explicitly tolerated by this test.

What we *do* enforce:

1. Every operation present in the live spec is also present in the
   static spec (no rogue endpoints).
2. ``operationId`` matches between the two for every implemented
   operation (Stream C codegen depends on these names).
3. Tags match.
4. The static spec parses cleanly as OpenAPI 3.0.

The reverse direction (static -> live) is enforced by ``IMPLEMENTED``
below: we list the paths that should already be implemented and fail
if any of them is missing in the live spec. As Stream B implements
more endpoints, that list grows; as a result this test also grows
into the "OpenAPI in CI" deliverable noted in the Day 2 plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]
from openapi_spec_validator import validate

from pitwall.api.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
STATIC_SPEC = REPO_ROOT / "docs" / "interfaces" / "openapi_v1.yaml"

# Paths that Stream B has implemented as of today. Add to this list as
# routes land; CI will then enforce that those routes stay in sync with
# the static contract.
IMPLEMENTED: dict[str, set[str]] = {
    "/health":                 {"get"},
    "/ready":                  {"get"},
    "/api/v1/sessions":        {"get"},
    "/api/v1/replay/start":    {"post"},
    "/api/v1/replay/stop":     {"post"},
}


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def static_spec() -> dict[str, Any]:
    with STATIC_SPEC.open() as f:
        return cast(dict[str, Any], yaml.safe_load(f))


@pytest.fixture(scope="module")
def live_spec() -> dict[str, Any]:
    return create_app().openapi()


# --------------------------------------------------------------------------
# Static spec health
# --------------------------------------------------------------------------


def test_static_spec_is_valid_openapi(static_spec: dict[str, Any]) -> None:
    validate(static_spec)


# --------------------------------------------------------------------------
# Live -> static (no rogue endpoints)
# --------------------------------------------------------------------------


def test_every_live_operation_exists_in_static_spec(
    live_spec: dict[str, Any], static_spec: dict[str, Any]
) -> None:
    static_paths: dict[str, dict[str, Any]] = static_spec["paths"]
    for path, methods in live_spec.get("paths", {}).items():
        assert path in static_paths, (
            f"Live API exposes {path!r} but the static spec at "
            f"{STATIC_SPEC} does not. Update the static spec or remove "
            f"the route."
        )
        for method in methods:
            assert method in static_paths[path], (
                f"Live API exposes {method.upper()} {path} but the "
                f"static spec does not."
            )


# --------------------------------------------------------------------------
# operationId agreement (Stream C codegen)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, method",
    [(p, m) for p, methods in IMPLEMENTED.items() for m in methods],
)
def test_operation_id_matches_static_spec(
    path: str,
    method: str,
    live_spec: dict[str, Any],
    static_spec: dict[str, Any],
) -> None:
    live_op_id = live_spec["paths"][path][method].get("operationId")
    static_op_id = static_spec["paths"][path][method].get("operationId")
    assert live_op_id is not None, (
        f"{method.upper()} {path} has no operationId in the live spec — "
        f"add `operation_id=...` to the FastAPI route."
    )
    assert static_op_id is not None, (
        f"{method.upper()} {path} has no operationId in {STATIC_SPEC}."
    )
    assert live_op_id == static_op_id, (
        f"operationId drift on {method.upper()} {path}: "
        f"live={live_op_id!r} vs static={static_op_id!r}."
    )


# --------------------------------------------------------------------------
# Tag agreement
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, method",
    [(p, m) for p, methods in IMPLEMENTED.items() for m in methods],
)
def test_tags_match_static_spec(
    path: str,
    method: str,
    live_spec: dict[str, Any],
    static_spec: dict[str, Any],
) -> None:
    live_tags = set(live_spec["paths"][path][method].get("tags", []))
    static_tags = set(static_spec["paths"][path][method].get("tags", []))
    assert live_tags == static_tags, (
        f"tag drift on {method.upper()} {path}: "
        f"live={sorted(live_tags)} vs static={sorted(static_tags)}."
    )


# --------------------------------------------------------------------------
# Static -> live (every implemented op is exposed)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, method",
    [(p, m) for p, methods in IMPLEMENTED.items() for m in methods],
)
def test_implemented_route_is_exposed_in_live_spec(
    path: str, method: str, live_spec: dict[str, Any]
) -> None:
    paths = live_spec.get("paths", {})
    assert path in paths, (
        f"IMPLEMENTED claims {method.upper()} {path} but the live FastAPI "
        f"app does not expose that path."
    )
    assert method in paths[path], (
        f"IMPLEMENTED claims {method.upper()} {path} but the live FastAPI "
        f"app exposes {sorted(paths[path])} instead."
    )
