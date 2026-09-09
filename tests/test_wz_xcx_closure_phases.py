from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def wz_audit():
    return _load(
        "wz_audit_closure",
        ROOT / ".agents" / "skills" / "wz" / "scripts" / "audit_engagement.py",
    )


@pytest.fixture(scope="module")
def xcx_audit():
    return _load(
        "xcx_audit_closure",
        ROOT / ".agents" / "skills" / "xcx" / "scripts" / "audit_miniapp_engagement.py",
    )


def test_new_wz_and_xcx_phase_lists_omit_retest():
    wz_init = _load(
        "wz_init_closure",
        ROOT / ".agents" / "skills" / "wz" / "scripts" / "init_engagement.py",
    )
    xcx_init = _load(
        "xcx_init_closure",
        ROOT / ".agents" / "skills" / "xcx" / "scripts" / "init_miniapp_engagement.py",
    )
    from authorized_assessment.orchestration.xcx_graph import XCX_PHASES

    assert "retest" not in wz_init.PHASES
    assert "retest" not in xcx_init.PHASES
    assert "retest" not in XCX_PHASES
    assert wz_init.PHASES[wz_init.PHASES.index("cleanup") + 1] == "reporting"
    assert xcx_init.PHASES[xcx_init.PHASES.index("cleanup") + 1] == "reporting"


def test_xcx_graph_connects_cleanup_directly_to_reporting():
    from authorized_assessment.orchestration.xcx_graph import build_xcx_graph

    graph = build_xcx_graph(created_at="fixed")
    assert {node.phase for node in graph.nodes if node.phase == "retest"} == set()
    cleanup = next(node for node in graph.nodes if node.phase == "cleanup")
    reporting = next(node for node in graph.nodes if node.phase == "reporting")
    assert any(edge.from_node == cleanup.node_id and edge.to_node == reporting.node_id for edge in graph.edges)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("confirmed", ["L1"]),
        ("accepted_risk", ["L1"]),
        ("fixed", ["L1"]),
        ("rejected", []),
        ("duplicate", []),
        ("out_of_scope", []),
        ("needs_login", []),
        ("blocked", []),
    ],
)
def test_wz_reportable_review_items(wz_audit, status, expected):
    ledger = [{"item_id": "L1", "status": status}]
    assert wz_audit.reportable_review_items(ledger) == expected


@pytest.mark.parametrize("status", ["confirmed", "accepted_risk", "fixed"])
def test_xcx_reportable_review_items_include_reportable_statuses(xcx_audit, status):
    assert xcx_audit.reportable_review_items([{"item_id": "M1", "status": status}]) == ["M1"]


def test_xcx_reportable_review_items_ignore_legacy_retest_statuses(xcx_audit):
    ledger = [
        {"item_id": "M1", "status": "retest_passed"},
        {"item_id": "M2", "status": "retest_failed"},
    ]
    assert xcx_audit.reportable_review_items(ledger) == []
