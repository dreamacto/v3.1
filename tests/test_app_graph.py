"""APP orchestration graph tests (batch B9/W21; mirrors tests/test_xcx_graph.py).

锁定：契约 ↔ 工厂对齐（Draft 2020-12 校验零错）、非法输入 fail-closed、加固复核
屏障先于 static_analysis、双审批门（device_instrumentation / app_hardened_unpack）
不可自动推进、常量与 init 种子同源。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from authorized_assessment.orchestration.app_graph import (
    APP_APPROVAL_GATE_SUPPLIERS,
    APP_APPROVAL_GATES,
    APP_BRANCHES,
    APP_CURSOR_FILE,
    APP_PHASES,
    build_app_graph,
    validate_app_graph,
)

ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "init_app_engagement.py"


def load_schema():
    return json.loads((ROOT / "contracts" / "app_graph_schema.json").read_text(encoding="utf-8"))


def load_init_module():
    spec = importlib.util.spec_from_file_location("app_init_for_graph_test", INIT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_app_graph_contract_and_factory_are_aligned():
    schema = load_schema()
    assert schema["$id"] == "app_graph_schema"
    assert schema["properties"]["workflow"] == {"const": "app"}
    assert schema["$defs"]["node"]["properties"]["cursor_file"] == {"const": "phase_status.app.json"}
    graph = build_app_graph(created_at="2026-09-01T00:00:00+00:00")
    errors = list(Draft202012Validator(schema).iter_errors(graph.to_dict()))
    assert errors == []
    assert validate_app_graph(graph) == []
    assert {node.cursor_file for node in graph.nodes} == {APP_CURSOR_FILE}
    assert {node.phase for node in graph.nodes if node.kind == "verifier"} == {"verifier"}


def test_app_graph_constants_match_init_seed():
    init = load_init_module()
    assert APP_PHASES == init.PHASES
    assert APP_BRANCHES == init.PHASE_BRANCHES


@pytest.mark.parametrize(
    "mutation",
    [
        "empty",
        "wrong_workflow_wz",
        "wrong_workflow_xcx",
        "wrong_cursor_wz",
        "wrong_cursor_xcx",
        "unknown_edge",
        "cycle",
        "gate_kind_task",
        "gate_outbound_edge",
        "gate_missing",
    ],
)
def test_app_graph_rejects_empty_and_illegal_inputs(mutation):
    graph = build_app_graph(created_at="fixed").to_dict()
    if mutation == "empty":
        graph["nodes"] = []
    elif mutation == "wrong_workflow_wz":
        graph["workflow"] = "wz"
    elif mutation == "wrong_workflow_xcx":
        graph["workflow"] = "xcx"
    elif mutation == "wrong_cursor_wz":
        graph["nodes"][0]["cursor_file"] = "phase_status.json"
    elif mutation == "wrong_cursor_xcx":
        graph["nodes"][0]["cursor_file"] = "phase_status.miniapp.json"
    elif mutation == "unknown_edge":
        graph["edges"].append({"edge_id": "edge_bad", "from": "node_missing", "to": graph["nodes"][0]["node_id"], "kind": "depends_on"})
    elif mutation == "cycle":
        first, second = graph["nodes"][:2]
        graph["edges"].append({"edge_id": "edge_cycle", "from": second["node_id"], "to": first["node_id"], "kind": "depends_on"})
    elif mutation == "gate_kind_task":
        gate = next(node for node in graph["nodes"] if node["phase"] == "device_instrumentation")
        gate["kind"] = "task"
    elif mutation == "gate_outbound_edge":
        gate = next(node for node in graph["nodes"] if node["phase"] == "app_hardened_unpack")
        target = next(node for node in graph["nodes"] if node["phase"] == "static_analysis")
        graph["edges"].append({"edge_id": "edge_gate_auto_advance", "from": gate["node_id"], "to": target["node_id"], "kind": "depends_on"})
    else:  # gate_missing
        gate_id = next(node["node_id"] for node in graph["nodes"] if node["phase"] == "device_instrumentation")
        graph["nodes"] = [node for node in graph["nodes"] if node["node_id"] != gate_id]
        graph["edges"] = [edge for edge in graph["edges"] if gate_id not in (edge["from"], edge["to"])]
    assert validate_app_graph(graph)


def test_approval_gates_are_control_nodes_that_never_auto_advance():
    graph = build_app_graph(created_at="fixed")
    node_by_phase = {node.phase: node for node in graph.nodes}
    node_by_id = {node.node_id: node for node in graph.nodes}
    for gate in APP_APPROVAL_GATES:
        node = node_by_phase[gate]
        assert node.kind == "approval"
        assert gate not in APP_PHASES  # 不在 33 阶段自动链上
        incoming = [edge for edge in graph.edges if edge.to_node == node.node_id]
        outgoing = [edge for edge in graph.edges if edge.from_node == node.node_id]
        assert outgoing == []  # 零出边：图编排永不自动推进审批门
        assert incoming, f"approval gate {gate} must have gates suppliers"
        assert all(edge.kind == "gates" for edge in incoming)
        suppliers = {node_by_id[edge.from_node].phase for edge in incoming if edge.from_node in node_by_id}
        assert suppliers == set(APP_APPROVAL_GATE_SUPPLIERS[gate])
    # 供能语义：设备门由动态两阶段供能、脱壳门由解包阶段供能（SKILL 约束 1 hard stop）。
    assert set(APP_APPROVAL_GATE_SUPPLIERS["device_instrumentation"]) == {"dynamic_setup", "dynamic_mapping"}
    assert set(APP_APPROVAL_GATE_SUPPLIERS["app_hardened_unpack"]) == {"package_unpack_decompile"}


def test_hardening_review_barrier_precedes_static_analysis():
    graph = build_app_graph(created_at="fixed")
    phases = [node.phase for node in graph.nodes if node.phase in APP_PHASES]
    assert phases.index("package_integrity_hardening_review") < phases.index("static_analysis")
    hardening = next(node for node in graph.nodes if node.phase == "package_integrity_hardening_review")
    barrier = next(node for node in graph.nodes if node.phase == "package_integrity_hardening_review.barrier")
    static = next(node for node in graph.nodes if node.phase == "static_analysis")
    assert any(edge.from_node == barrier.node_id and edge.to_node == static.node_id for edge in graph.edges)
    assert hardening.kind == "task"
    assert barrier.join == "barrier"


def test_each_branch_phase_has_explicit_barrier_and_no_direct_skip():
    graph = build_app_graph(created_at="fixed")
    for phase, branches in APP_BRANCHES.items():
        phase_node = next(node for node in graph.nodes if node.phase == phase)
        barrier = next(node for node in graph.nodes if node.phase == f"{phase}.barrier")
        branch_nodes = {node.node_id for node in graph.nodes if node.phase.startswith(f"{phase}.") and node.kind == "worker"}
        assert len(branch_nodes) == len(branches)
        assert barrier.join == "barrier"
        assert {edge.to_node for edge in graph.edges if edge.from_node == phase_node.node_id} == branch_nodes
        assert {edge.from_node for edge in graph.edges if edge.to_node == barrier.node_id} == branch_nodes
