"""The Redis coverage document must list every registered route and match the code."""

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "route_inventory", ROOT / "scripts" / "route_inventory.py"
)
assert _spec and _spec.loader
inv: Any = importlib.util.module_from_spec(_spec)
sys.modules["route_inventory"] = inv
_spec.loader.exec_module(inv)


def test_every_cached_endpoint_is_documented_and_vice_versa() -> None:
    rows = inv.inventory()
    cached = {r["function"] for r in rows if r["c"]["redis"] == "cached"}
    assert cached == set(inv.CACHED)


def test_every_route_is_classified_with_a_reason() -> None:
    for r in inv.inventory():
        c = r["c"]
        assert c["redis"] in ("cached", "no-cache")
        assert c["redis"] == "cached" or c["reason"] not in ("", "-")
        if r["method"] != "GET":
            assert c["redis"] == "no-cache"


def test_coverage_document_is_current() -> None:
    doc = (ROOT / "docs" / "REDIS-ENDPOINT-COVERAGE.md").read_text(encoding="utf-8")
    assert doc.replace("\r\n", "\n") == inv.markdown(), "regenerate with scripts/route_inventory.py"
