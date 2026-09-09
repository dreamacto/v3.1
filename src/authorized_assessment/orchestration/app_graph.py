"""Deterministic, offline orchestration graph for the mobile-app (APP) stream.

The graph is a plan only: constructing it performs no network or filesystem I/O.
Worker implementations are deliberately represented as metadata so this module
remains independent from worker registration and execution.

The two APP approval gates (device_instrumentation / app_hardened_unpack) are
control nodes with ``gates``-kind inbound edges only and no outbound edges: the
graph never auto-advances them, and unlocking stays an explicit operator-driven
event (script gate + in-session human confirmation, both keys required).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .graph import GraphSpec
from .graph_builder import GraphBuilder
from .graph_validation import validate_graph

APP_WORKFLOW = "app"
APP_CURSOR_FILE = "phase_status.app.json"
WORKFLOW = APP_WORKFLOW
CURSOR_FILE = APP_CURSOR_FILE

# 33 phases（与 .agents/skills/app/scripts/init_app_engagement.py 的 PHASES 种子同源；
# 漂移由 tests/test_app_graph.py 与 validate_run_contracts.check_app_graph_contract 锁定）。
APP_PHASES = (
    "authorization", "identity", "platform_identification", "material_acquisition",
    "initial_decoding", "preflight", "package_inventory", "package_unpack_decompile",
    "source_reconstruction", "package_integrity_hardening_review", "static_analysis",
    "endpoint_inventory", "host_classification", "dynamic_setup", "dynamic_mapping",
    "static_dynamic_reconciliation", "platform_login_exchange", "session_token_lifecycle",
    "signature_replay", "backend_web_api_testing", "access_control_testing",
    "input_file_testing", "business_logic_testing", "local_data_exposure",
    "crypto_and_secret_handling", "webview_bridge_links", "ipc_component_boundary",
    "cloud_function_testing", "cloud_storage_acl_testing",
    "third_party_sdk_platform_boundary", "candidate_validation", "reporting", "cleanup",
)
PHASES = APP_PHASES

# 12 组复核分支（与 init PHASE_BRANCHES 种子同源，顺序一致）。
APP_BRANCHES: dict[str, tuple[str, ...]] = {
    "package_integrity_hardening_review": ("package_version_inventory", "signing_integrity", "hardening_obfuscation_markers", "debug_switches", "debug_info_exposure", "update_endpoint_environment", "trusted_update_config"),
    "platform_login_exchange": ("oauth_code_one_time", "oauth_code_expiry", "one_click_login_device_binding", "access_token_custody", "uid_authorization_basis"),
    "session_token_lifecycle": ("token_rotation", "token_revocation_logout", "multi_device_login", "stale_token_new_api", "device_user_tenant_binding"),
    "signature_replay": ("nonce_timestamp", "signature_canonicalization", "replay_window", "binding_scope"),
    "local_data_exposure": ("token_persistence", "logout_cleanup", "local_cache_database", "logs_clipboard_screenshots", "temp_files"),
    "crypto_and_secret_handling": ("hardcoded_secrets", "custom_crypto", "weak_random_key_derivation", "debug_config_env_keys"),
    "static_dynamic_reconciliation": ("static_endpoint_base", "dynamic_endpoint_base", "match_status_classification", "hidden_flow_identification", "stale_entry_disposition"),
    "webview_bridge_links": ("webview_allowed_domains", "postmessage_origin", "cookie_token_sharing_boundary", "bridge_method_exposure", "custom_scheme", "deep_link_sensitive_params", "external_app_browser_jump"),
    "ipc_component_boundary": ("exported_activity", "exported_service", "exported_receiver", "exported_provider", "custom_scheme_deeplink", "universal_link", "ios_extension_boundary"),
    "cloud_function_testing": ("anonymous_invocation", "function_parameter_role_validation", "cloud_env_id_mixing"),
    "cloud_storage_acl_testing": ("cloud_database_rules", "object_storage_acl", "signed_url_binding"),
    "third_party_sdk_platform_boundary": ("third_party_service_boundary", "platform_shared_asset_attribution"),
}
PHASE_BRANCHES = APP_BRANCHES

# APP 审批门（tool_strategy.json approval_gated_phases；SKILL 约束 1 hard stop）：
# 门节点不在 33 阶段自动链上，只有来自相关 phase 的 gates 入边、没有任何出边——
# 图编排永不自动推进，解锁=操作者显式双钥匙事件。
APP_APPROVAL_GATES: tuple[str, ...] = ("device_instrumentation", "app_hardened_unpack")
APPROVAL_GATES = APP_APPROVAL_GATES
APP_APPROVAL_GATE_SUPPLIERS: dict[str, tuple[str, ...]] = {
    # 设备改动/注入/绕过（root、用户 CA、frida-server、重打包、SSL pinning bypass、
    # 反调试 patch）在动态两阶段被需要。
    "device_instrumentation": ("dynamic_setup", "dynamic_mapping"),
    # 加固壳包脱壳在解包阶段被需要；壳包默认 blocked，不自动脱壳。
    "app_hardened_unpack": ("package_unpack_decompile",),
}
APPROVAL_GATE_SUPPLIERS = APP_APPROVAL_GATE_SUPPLIERS

# Stable binding contract. Consumers may replace these IDs in their registry;
# the graph itself never imports or invokes workers.
APP_PHASE_WORKERS = {
    phase: (f"worker_app_{phase}_code", f"worker_app_{phase}_analyst", f"worker_app_{phase}_verifier")
    for phase in APP_PHASES
}
APP_ROLE_WORKERS = APP_PHASE_WORKERS


def _branch_node_id(phase: str, branch: str) -> str:
    return f"node_{phase}__branch_{branch}"


def build_app_graph(
    graph_id: str = "graph_app_static",
    assessment_id: str = "assessment_app",
    *,
    created_at: str | None = None,
) -> GraphSpec:
    """Build the complete APP graph deterministically and without side effects."""
    builder = GraphBuilder(graph_id, assessment_id, APP_WORKFLOW, created_at=created_at, cursor_file=APP_CURSOR_FILE)
    authorization = builder.add_node("authorization", kind="gate", order=0)
    scope = builder.add_node("scope", kind="gate", order=1)
    builder.add_edge(authorization, scope)
    previous: str | None = scope
    phase_nodes: dict[str, str] = {}
    branch_joins: dict[str, str] = {}
    for order, phase in enumerate(APP_PHASES):
        if phase in {"authorization", "scope"}:
            phase_nodes[phase] = authorization if phase == "authorization" else scope
            continue
        kind = "checkpoint" if phase == "preflight" else "task"
        node = builder.add_node(phase, kind=kind, order=order + 2)
        phase_nodes[phase] = node
        if previous is not None:
            builder.add_edge(previous, node)
        previous = node
        branches = APP_BRANCHES.get(phase, ())
        if branches:
            branch_nodes = [builder.add_node(f"{phase}.{branch}", node_id=_branch_node_id(phase, branch), kind="worker", order=order * 100 + index + 1) for index, branch in enumerate(branches)]
            builder.fan_out(node, branch_nodes, kind="produces")
            join = builder.add_node(f"{phase}.barrier", node_id=f"node_{phase}__barrier", kind="checkpoint", join="barrier", order=order * 100 + len(branches) + 1)
            builder.fan_in(branch_nodes, join, join="barrier")
            branch_joins[phase] = join
            previous = join
    # 审批门：gates 入边来自相关 phase，零出边（不可自动推进）。
    gate_nodes: dict[str, str] = {}
    for gate_index, gate in enumerate(APP_APPROVAL_GATES):
        gate_node = builder.add_node(gate, kind="approval", order=9000 + gate_index)
        gate_nodes[gate] = gate_node
        for supplier in APP_APPROVAL_GATE_SUPPLIERS[gate]:
            builder.add_edge(phase_nodes[supplier], gate_node, kind="gates")
    approval = builder.add_node("approval", kind="approval", order=10000)
    verifier = builder.add_node("verifier", kind="verifier", order=10001, terminal=True)
    builder.add_edge(previous, approval)
    builder.add_edge(approval, verifier)
    return builder.build().with_metadata(
        workflow=APP_WORKFLOW,
        cursor_file=APP_CURSOR_FILE,
        phases=list(APP_PHASES),
        branches={phase: list(branches) for phase, branches in APP_BRANCHES.items()},
        phase_nodes=phase_nodes,
        branch_barriers=branch_joins,
        phase_roles={phase: {"code": workers[0], "analyst": workers[1], "verifier": workers[2]} for phase, workers in APP_PHASE_WORKERS.items()},
        role_order=["code", "analyst", "verifier"],
        approval_gates=list(APP_APPROVAL_GATES),
        approval_gate_nodes=gate_nodes,
        approval_gate_suppliers={gate: list(suppliers) for gate, suppliers in APP_APPROVAL_GATE_SUPPLIERS.items()},
        approval_gates_auto_advance=False,
    )


app_graph = build_app_graph


def validate_app_graph(graph: GraphSpec | Mapping[str, Any]) -> list[str]:
    """Return APP-specific violations; malformed or cross-stream graphs fail closed."""
    try:
        errors = list(validate_graph(graph))
        data = graph.to_planning_dict() if isinstance(graph, GraphSpec) else dict(graph)
    except Exception as exc:
        return [f"invalid graph input: {exc}"]
    if data.get("workflow") != APP_WORKFLOW:
        errors.append("workflow must be 'app'")
    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        return list(dict.fromkeys(errors + ["nodes must be a list"]))
    phases = {node.get("phase") for node in nodes if isinstance(node, Mapping)}
    node_by_phase = {node.get("phase"): node for node in nodes if isinstance(node, Mapping)}
    node_by_id = {node.get("node_id"): node for node in nodes if isinstance(node, Mapping)}
    edge_list = data.get("edges", [])
    edges = [edge for edge in edge_list if isinstance(edge, Mapping)]
    for node in nodes:
        if isinstance(node, Mapping) and node.get("cursor_file") not in (None, APP_CURSOR_FILE):
            errors.append("APP graph may only use phase_status.app.json")
    missing = [phase for phase in APP_PHASES if phase not in phases]
    if missing:
        errors.append(f"missing APP phases: {missing}")
    # 审批门结构：在场、kind=approval、入边仅 gates、零出边（不可自动推进）、不在自动链。
    for gate in APP_APPROVAL_GATES:
        gate_node = node_by_phase.get(gate)
        if gate_node is None:
            errors.append(f"missing APP approval gate node: {gate}")
            continue
        if gate_node.get("kind") != "approval":
            errors.append(f"APP approval gate {gate} must be an approval node")
        if gate in APP_PHASES:
            errors.append(f"APP approval gate {gate} must not sit in the auto-advance phase chain")
        incoming = [edge for edge in edges if edge.get("to") == gate_node.get("node_id")]
        outgoing = [edge for edge in edges if edge.get("from") == gate_node.get("node_id")]
        if any(edge.get("kind") != "gates" for edge in incoming):
            errors.append(f"APP approval gate {gate} may only have gates-kind inbound edges")
        expected_suppliers = set(APP_APPROVAL_GATE_SUPPLIERS[gate])
        actual_suppliers = {
            node_by_id.get(edge.get("from"), {}).get("phase")
            for edge in incoming
        }
        if actual_suppliers != expected_suppliers:
            errors.append(
                f"APP approval gate {gate} suppliers drift: {sorted(str(s) for s in actual_suppliers)} != {sorted(expected_suppliers)}"
            )
        if outgoing:
            errors.append(f"APP approval gate {gate} must not auto-advance (no outbound edges allowed)")
    for forbidden in ("phase_status.json", "phase_status.miniapp.json", "run_status.json"):
        if forbidden in str(data):
            errors.append(f"forbidden non-APP cursor in graph: {forbidden}")
    return list(dict.fromkeys(errors))


def assert_valid_app_graph(graph: GraphSpec | Mapping[str, Any]) -> GraphSpec | Mapping[str, Any]:
    errors = validate_app_graph(graph)
    if errors:
        raise ValueError("invalid APP graph: " + "; ".join(errors))
    return graph


def graph_dict(graph: GraphSpec | Mapping[str, Any]) -> dict[str, Any]:
    return graph.to_dict() if isinstance(graph, GraphSpec) else dict(graph)


def graph_from_dict(data: Mapping[str, Any]) -> GraphSpec:
    graph = GraphSpec.from_dict(data)
    assert_valid_app_graph(graph)
    return graph

validate = validate_app_graph

__all__ = ["APP_WORKFLOW", "APP_CURSOR_FILE", "WORKFLOW", "CURSOR_FILE", "APP_PHASES", "PHASES", "APP_BRANCHES", "PHASE_BRANCHES", "APP_APPROVAL_GATES", "APPROVAL_GATES", "APP_APPROVAL_GATE_SUPPLIERS", "APPROVAL_GATE_SUPPLIERS", "APP_PHASE_WORKERS", "APP_ROLE_WORKERS", "build_app_graph", "app_graph", "validate_app_graph", "assert_valid_app_graph", "graph_dict", "graph_from_dict"]
