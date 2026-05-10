"""Export the FastAPI-generated OpenAPI spec to a file.

This script is the seam between Stream B (which owns the spec via the
FastAPI app) and Stream D (which wires the export into CI on Day 7).

Usage::

    # From the repo root, with the backend package installed in editable
    # mode (`uv pip install -e backend/[dev]`):
    python scripts/export_openapi.py
    python scripts/export_openapi.py --output build/openapi.json
    python scripts/export_openapi.py --format yaml \\
        --output docs/interfaces/openapi_generated.yaml

The exported file is the *runtime* spec (what the FastAPI app actually
serves). It is compared against ``docs/interfaces/openapi_v1.yaml``
(the *agreed* spec) by ``backend/tests/contract/test_openapi_export.py``.
A drift between the two is a signal that either the implementation or
the contract moved without the other being updated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_app() -> Any:
    """Import the FastAPI app at run time so this script does not block
    on import errors when ``--help`` is the only argument."""
    from pitwall.api.main import create_app

    return create_app()


def _dump(spec: dict[str, Any], output: Path, fmt: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        output.write_text(json.dumps(spec, indent=2, sort_keys=True))
    elif fmt == "yaml":
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "PyYAML is required for --format yaml; "
                "install with `pip install pyyaml`."
            ) from exc
        output.write_text(yaml.safe_dump(spec, sort_keys=False))
    else:  # pragma: no cover - argparse already validates
        raise ValueError(f"Unknown format: {fmt}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/openapi.json"),
        help="Destination file (default: build/openapi.json).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "yaml"],
        default=None,
        help="Output format. Default: inferred from --output extension "
        "(.yaml/.yml → yaml; otherwise json).",
    )
    args = parser.parse_args(argv)

    fmt = args.format or (
        "yaml" if args.output.suffix.lower() in (".yaml", ".yml") else "json"
    )

    app = _load_app()
    spec = app.openapi()

    _dump(spec, args.output, fmt)

    n_paths = len(spec.get("paths", {}))
    n_schemas = len(spec.get("components", {}).get("schemas", {}))
    print(f"Wrote {args.output} ({fmt.upper()}, {n_paths} paths, {n_schemas} schemas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
