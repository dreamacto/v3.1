#!/usr/bin/env python3
"""validate_run_contracts.py —— run 契约校验入口（主规范 13.3 离线验收命令；阻塞项 B3）。

校验三层一致性（离线、零网络）：
  1. contracts/*.json 可解析且结构完整（workflow / run_quality / rule_precedence /
     context_snapshot / candidate_identity / tool_capability / injection_candidate /
     graphql / api_reconciliation / miniapp_auth / miniapp_storage_package /
     miniapp_reconciliation / miniapp_cloud / miniapp_webview /
     app_auth / app_storage_package / app_reconciliation / app_webview /
     app_ipc / app_cloud / app_graph）；
  2. 状态模型无漂移：契约 ↔ 实现常量（run_lifecycle 报告生命周期与质量结论许可集、
     quality gate 五态与门控原因、fh_review_dispatch verdict 枚举 ⊆ review_statuses、
     finding 8 状态三方交叉、candidate_identity 键集/枚举/限量 ↔ canonical_keys、
     tool_capability 字段集/状态枚举 ↔ tools/registry 模块 ↔ tools/tool_registry.json、
     injection_candidate 类别/证据形态/升级规则 ↔ injection_candidates 模块、
     miniapp_auth 三 phase 分支/产物路径/形状 ↔ miniapp 三模块引擎、
     miniapp_storage_package 三 phase 分支/产物路径/形状 ↔ miniapp 三模块引擎、
     app 六契约分支/产物路径/CSV 表头/行级枚举 ↔ .agents/skills/app 的
     init/audit 种子常量 + src/authorized_assessment/app/ 全部引擎常量（B5：hardening/
     static_extraction/webview/ipc 与共享骨架；B6：auth 三模块 + local/crypto +
     reconciliation + cloud 三模块——契约↔引擎↔种子三处同源收口，含红线锚点与
     零网络 import 扫描；B9：app_graph_schema 结构 + orchestration/app_graph 工厂
     ↔ init 种子同源，双审批门不可自动推进）；
  3. 门控阈值无漂移：run_quality_schema.gate_thresholds ↔ GateThresholds 默认值。

退出码：0 全部通过；1 存在违例。--json 输出机器可读报告；--root 可指向其他根（用于负例）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
_SRC = SCRIPT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

REQUIRED_WORKFLOW_KEYS = (
    "phase_statuses",
    "review_statuses",
    "scope_states",
    "authorization_states",
    "blocked_actions",
    "phase_cursor_required",
    "report_required",
    "report_lifecycle_states",
    "quality_status_states",
)
EXPECTED_REPORT_STATES = (
    "report_generated",
    "report_reviewed",
    "report_accepted",
    "report_delivered",
    "report_superseded",
)
EXPECTED_QUALITY_STATES = ("VALID", "PARTIAL", "INCONCLUSIVE", "FAILED", "BLOCKED")
EXPECTED_GATE_THRESHOLD_KEYS = (
    "probe_coverage_min",
    "probe_ok_ratio_min",
    "rate_limit_skip_ratio_max",
    "transport_error_ratio_max",
    "waf_block_ratio_max",
)
REQUIRED_PRECEDENCE_COUNT = 11
REQUIRED_SNAPSHOT_FIELDS = (
    "task_type",
    "workflow",
    "phase",
    "loaded_sources",
    "source_hashes",
    "policy_digest",
    "current_facts",
    "historical_inputs",
    "excluded_sources",
    "context_conflicts",
    "created_at",
)

ORCHESTRATION_CONTRACTS = (
    "assessment_schema.json",
    "worker_manifest_schema.json",
    "task_envelope_schema.json",
    "worker_result_schema.json",
    "policy_decision_schema.json",
    "checkpoint_schema.json",
    "event_schema.json",
    "metric_event_schema.json",
    "approval_schema.json",
    "graph_schema.json",
    "worker_error_schema.json",
)
ORCHESTRATION_FORBIDDEN_PROPERTY_NAMES = {
    "cookie", "token", "password", "secret", "session", "session_key",
    "raw_response", "har", "traceback",
}

EXPECTED_IDENTITY_KEY_FIELDS = {
    "generic": ("canonical_target", "endpoint", "http_method", "parameter_name",
                "input_location", "test_family"),
    "api": ("canonical_host", "normalized_path", "http_method", "parameter_names",
            "content_type", "source_kind"),
    "miniapp": ("miniapp_id", "backend_host", "normalized_path", "http_method",
                "parameter_names", "package_version"),
}
EXPECTED_MERGE_KEY_FIELDS = (
    "canonical_target", "product_or_component", "normalized_endpoint", "http_method",
    "vulnerability_family", "root_cause_signature", "parameter_scope",
)
EXPECTED_CROSS_RUN_FIELDS = ("first_seen", "last_seen", "seen_count", "latest_status",
                             "latest_evidence_ref")

# APP 流 B4（W19 上半）：六个必需契约 + review JSON 12 键形状（与 miniapp 契约同构）。
REQUIRED_APP_CONTRACTS = (
    "app_auth_schema.json",
    "app_storage_package_schema.json",
    "app_reconciliation_schema.json",
    "app_webview_schema.json",
    "app_ipc_schema.json",
    "app_cloud_schema.json",
)
# APP 流 B9（W21）：编排 graph 契约（JSON-Schema 元契约形态，同 xcx_graph_schema）。
REQUIRED_APP_GRAPH_CONTRACTS = (
    "app_graph_schema.json",
)
APP_REVIEW_ARTIFACT_KEYS = (
    "schema_version", "contract", "phase", "observation_schema_version",
    "row_fields", "summary_fields", "substatuses", "rows", "summaries",
    "violations", "authorization_basis", "updated_at",
)
_APP_SKILL_MODULES: dict[str, object] = {}


def _injection_rule_shape(rule: object) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...], tuple[tuple[str, ...], ...]]:
    """把 upgrade_rules 条目归一化为 (required_all, required_any_groups, required_any_branches)。"""
    if not isinstance(rule, dict):
        return (), (), ()
    groups = rule.get("required_any_groups") or ()
    branches = rule.get("required_any_branches") or ()
    return (
        tuple(rule.get("required_all") or ()),
        tuple(tuple(g) for g in groups),
        tuple(tuple(b) for b in branches),
    )


def _load_json(path: Path) -> tuple[object, str | None]:
    if not path.is_file():
        return None, f"missing contract file: {path.name}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"unparseable contract file {path.name}: {exc}"


def check_orchestration_contract(path: Path) -> list[str]:
    data, err = _load_json(path)
    if err:
        return [err]
    if not isinstance(data, dict):
        return [f"{path.name} must be an object"]
    violations: list[str] = []
    for field in ("schema_version", "contract", "type", "required", "properties", "invariants"):
        if field not in data:
            violations.append(f"{path.name} missing {field}")
    if data.get("schema_version") != "1.0":
        violations.append(f"{path.name} schema_version drift")
    if data.get("type") != "object":
        violations.append(f"{path.name} type must be object")
    if not isinstance(data.get("required"), list) or not data["required"]:
        violations.append(f"{path.name}.required missing or empty")
    if not isinstance(data.get("properties"), dict) or not data["properties"]:
        violations.append(f"{path.name}.properties missing or empty")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append(f"{path.name}.invariants missing or empty")

    def walk_keys(node: object):
        if isinstance(node, dict):
            for key, value in node.items():
                yield str(key).lower()
                yield from walk_keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk_keys(value)

    forbidden = sorted(
        set(walk_keys(data.get("properties", {}))) & ORCHESTRATION_FORBIDDEN_PROPERTY_NAMES
    )
    if forbidden:
        violations.append(f"{path.name} forbidden sensitive property names: {forbidden}")

    props = data.get("properties", {})
    if path.name == "worker_manifest_schema.json":
        permissions = props.get("permissions", {}).get("properties", {})
        for field in ("write_scope", "write_approval", "write_cursor", "write_confirmed"):
            if permissions.get(field, {}).get("const") is not False:
                violations.append(f"worker_manifest_schema.permissions.{field} must be false")
    if path.name == "task_envelope_schema.json":
        actions = props.get("action", {}).get("enum")
        if actions != ["offline", "read_only", "metadata"]:
            violations.append(f"task_envelope_schema.action enum drift: {actions!r}")
    if path.name == "worker_result_schema.json":
        if "gate" not in props:
            violations.append("worker_result_schema missing gate")
        for field in ("facts_used", "reasoning_summary", "alternative_explanations", "hypotheses", "unknowns", "coverage", "not_tested", "next_hints"):
            if field not in props:
                violations.append(f"worker_result_schema missing analyst field: {field}")
    if path.name == "checkpoint_schema.json":
        status_files = props.get("status_file", {}).get("enum", [])
        for value in ("phase_status.json", "phase_status.miniapp.json"):
            if value not in status_files:
                violations.append(f"checkpoint_schema.status_file missing {value}")
    if path.name == "approval_schema.json":
        for field in ("script_gate", "human_confirmation"):
            if field not in props:
                violations.append(f"approval_schema missing {field}")
    if path.name == "graph_schema.json":
        for field in ("nodes", "edges"):
            if field not in props:
                violations.append(f"graph_schema missing {field}")
    return violations


def check_orchestration_contracts(root: Path) -> list[str]:
    contracts = root / "contracts"
    violations: list[str] = []
    for name in ORCHESTRATION_CONTRACTS:
        violations.extend(check_orchestration_contract(contracts / name))
    return violations


def check_workflow_schema(contracts: Path) -> list[str]:
    violations: list[str] = []
    data, err = _load_json(contracts / "workflow_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    for key in REQUIRED_WORKFLOW_KEYS:
        value = data.get(key)
        if not isinstance(value, list) or not value:
            violations.append(f"workflow_schema.{key} missing or empty")
    report_states = data.get("report_lifecycle_states")
    if isinstance(report_states, list) and tuple(report_states) != EXPECTED_REPORT_STATES:
        violations.append(
            f"workflow_schema.report_lifecycle_states drift: {report_states!r} != {list(EXPECTED_REPORT_STATES)!r}"
        )
    quality_states = data.get("quality_status_states")
    if isinstance(quality_states, list) and tuple(quality_states) != EXPECTED_QUALITY_STATES:
        violations.append(
            f"workflow_schema.quality_status_states drift: {quality_states!r} != {list(EXPECTED_QUALITY_STATES)!r}"
        )
    miniapp = data.get("miniapp_phase_status")
    if not isinstance(miniapp, dict):
        violations.append("workflow_schema.miniapp_phase_status missing")
    else:
        if miniapp.get("stream") != "miniapp_xcx":
            violations.append("workflow_schema.miniapp_phase_status.stream drift")
        if miniapp.get("status_file") != "phase_status.miniapp.json":
            violations.append("workflow_schema.miniapp_phase_status.status_file drift")
        if miniapp.get("legacy_standalone_status_file") != "phase_status.json":
            violations.append("workflow_schema.miniapp_phase_status.legacy_standalone_status_file drift")
    return violations


def check_run_quality_schema(contracts: Path) -> list[str]:
    violations: list[str] = []
    data, err = _load_json(contracts / "run_quality_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    if tuple(data.get("quality_status_states") or ()) != EXPECTED_QUALITY_STATES:
        violations.append(
            f"run_quality_schema.quality_status_states drift: {data.get('quality_status_states')!r}"
        )
    reasons = data.get("gate_reasons")
    if not isinstance(reasons, list) or not reasons:
        violations.append("run_quality_schema.gate_reasons missing or empty")
    required = data.get("required")
    properties = data.get("properties")
    if not isinstance(required, list) or not required:
        violations.append("run_quality_schema.required missing or empty")
    if not isinstance(properties, dict) or not properties:
        violations.append("run_quality_schema.properties missing or empty")
    elif isinstance(required, list):
        for field in required:
            if field not in properties:
                violations.append(f"run_quality_schema.required field not in properties: {field}")
    thresholds = data.get("gate_thresholds")
    if not isinstance(thresholds, dict):
        violations.append("run_quality_schema.gate_thresholds missing")
    else:
        for key in EXPECTED_GATE_THRESHOLD_KEYS:
            value = thresholds.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                violations.append(f"run_quality_schema.gate_thresholds.{key} not numeric")
    return violations
def check_rule_precedence(contracts: Path) -> list[str]:
    violations: list[str] = []
    data, err = _load_json(contracts / "rule_precedence.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    levels = data.get("levels")
    if not isinstance(levels, list) or len(levels) != REQUIRED_PRECEDENCE_COUNT:
        violations.append(
            f"rule_precedence.levels must have exactly {REQUIRED_PRECEDENCE_COUNT} levels, "
            f"got {len(levels) if isinstance(levels, list) else type(levels).__name__}"
        )
    conflict = data.get("conflict_handling")
    if not isinstance(conflict, dict) or not conflict.get("rules"):
        violations.append("rule_precedence.conflict_handling missing or empty")
    return violations


def check_context_snapshot_schema(contracts: Path) -> list[str]:
    violations: list[str] = []
    data, err = _load_json(contracts / "context_snapshot_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    required = data.get("required")
    if not isinstance(required, list):
        violations.append("context_snapshot_schema.required missing")
        return violations
    for field in REQUIRED_SNAPSHOT_FIELDS:
        if field not in required:
            violations.append(f"context_snapshot_schema.required missing field: {field}")
    return violations


def check_candidate_identity_schema(contracts: Path) -> list[str]:
    violations: list[str] = []
    data, err = _load_json(contracts / "candidate_identity_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    key_fields = data.get("key_fields")
    if not isinstance(key_fields, dict):
        violations.append("candidate_identity_schema.key_fields missing")
    else:
        for kind, expected in EXPECTED_IDENTITY_KEY_FIELDS.items():
            actual = key_fields.get(kind)
            if tuple(actual or ()) != expected:
                violations.append(
                    f"candidate_identity_schema.key_fields.{kind} drift: {actual!r} != {list(expected)!r}"
                )
    merge_keys = data.get("merge_keys")
    if not isinstance(merge_keys, dict) or tuple(merge_keys.get("fields") or ()) != EXPECTED_MERGE_KEY_FIELDS:
        violations.append("candidate_identity_schema.merge_keys.fields missing or drifted")
    cross_run = data.get("cross_run_retention")
    if not isinstance(cross_run, dict) or tuple(cross_run.get("fields") or ()) != EXPECTED_CROSS_RUN_FIELDS:
        violations.append("candidate_identity_schema.cross_run_retention.fields missing or drifted")
    for key in ("http_methods", "input_locations", "vulnerability_families", "parameter_scopes"):
        if not isinstance(data.get(key), list) or not data[key]:
            violations.append(f"candidate_identity_schema.{key} missing or empty")
    if not isinstance(data.get("source_kinds"), dict) or not data["source_kinds"]:
        violations.append("candidate_identity_schema.source_kinds missing or empty")
    if not isinstance(data.get("quota_rules"), dict) or not data["quota_rules"]:
        violations.append("candidate_identity_schema.quota_rules missing")
    required = data.get("required")
    properties = data.get("properties")
    if isinstance(required, list) and isinstance(properties, dict):
        for field in required:
            if field not in properties:
                violations.append(f"candidate_identity_schema.required field not in properties: {field}")
    return violations


def check_tool_capability_schema(root: Path) -> list[str]:
    """Batch 4：tool_capability 契约 ↔ registry 模块 ↔ tools/tool_registry.json 三方校验。"""
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "tool_capability_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    try:
        from authorized_assessment.tools import registry as tool_registry
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"tool registry module import failed: {exc}"]
    if data.get("schema_version") != tool_registry.REGISTRY_SCHEMA_VERSION:
        violations.append(
            f"tool_capability_schema.schema_version drift: {data.get('schema_version')!r} "
            f"!= {tool_registry.REGISTRY_SCHEMA_VERSION!r}"
        )
    for schema_key, module_constant in (
        ("tool_required_fields", tool_registry.TOOL_REQUIRED_FIELDS),
        ("tool_optional_fields", tool_registry.TOOL_OPTIONAL_FIELDS),
        ("forbidden_control_fields", tool_registry.FORBIDDEN_CONTROL_FIELDS),
        ("status_values", tool_registry.STATUS_VALUES),
    ):
        schema_value = data.get(schema_key)
        if not isinstance(schema_value, list) or tuple(schema_value) != tuple(module_constant):
            violations.append(
                f"tool_capability_schema.{schema_key} drift: {schema_value!r} "
                f"!= {list(module_constant)!r}"
            )
    registry, reg_err = tool_registry.load_registry(root / "tools" / "tool_registry.json")
    if reg_err:
        return violations + [reg_err]
    assert registry is not None
    violations += tool_registry.validate_registry(registry)
    violations += tool_registry.check_status_consistency(registry, root)
    config, cfg_err = _load_json(root / "gov_exercise_config.json")
    if cfg_err:
        violations.append(f"gov_exercise_config.json: {cfg_err}")
    else:
        assert config is not None
        violations += tool_registry.check_config_coverage(registry, config)
    strategy, stg_err = _load_json(root / "tool_strategy.json")
    if stg_err:
        violations.append(f"tool_strategy.json: {stg_err}")
    else:
        assert strategy is not None
        violations += tool_registry.check_tool_strategy_references(registry, strategy, root)
    return violations


def check_injection_candidate_schema(root: Path) -> list[str]:
    """Batch 6：injection_candidate 契约 ↔ injection_candidates 模块 ↔ finding 8 状态交叉。"""
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "injection_candidate_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    try:
        from authorized_assessment.triage import injection_candidates as ic
        from authorized_assessment.quality import finding_quality_gate
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"injection candidates module import failed: {exc}"]
    for schema_key, module_constant in (
        ("categories", ic.INJECTION_CATEGORIES),
        ("category_summary_required_fields", ic.CATEGORY_SUMMARY_FIELDS),
        ("candidate_status_values", ic.CANDIDATE_STATUS_VALUES),
        ("evidence_kinds", ic.EVIDENCE_KINDS),
        ("insufficient_evidence_kinds", ic.INSUFFICIENT_EVIDENCE_KINDS),
        ("applicable_values", ic.APPLICABLE_VALUES),
    ):
        schema_value = data.get(schema_key)
        if not isinstance(schema_value, list) or tuple(schema_value) != tuple(module_constant):
            violations.append(
                f"injection_candidate_schema.{schema_key} drift: {schema_value!r} "
                f"!= {list(module_constant)!r}"
            )
    # 三统计概念分离 + 观察版本化（操作员决定①②③）的契约↔实现交叉。
    observation = data.get("observation_schema")
    if not isinstance(observation, dict) or not observation.get("fields"):
        violations.append("injection_candidate_schema.observation_schema missing or empty")
    else:
        if observation.get("version") != ic.OBSERVATION_SCHEMA_VERSION:
            violations.append(
                f"observation_schema.version drift: {observation.get('version')!r} "
                f"!= {ic.OBSERVATION_SCHEMA_VERSION!r}"
            )
        schema_fields = observation.get("fields")
        if isinstance(schema_fields, dict) and tuple(sorted(schema_fields)) != tuple(
            sorted(ic.OBSERVATION_FIELD_DOCS)
        ):
            violations.append(
                "observation_schema.fields drift against OBSERVATION_FIELD_DOCS (键名集合演进必须同步)"
            )
        for key in ("versioning_rule", "not_proof_semantics", "source_required"):
            if not str(observation.get(key) or "").strip():
                violations.append(f"observation_schema.{key} missing or empty")
    if not isinstance(data.get("summary_structure"), str) or not data["summary_structure"]:
        violations.append("injection_candidate_schema.summary_structure missing or empty")
    try:
        from authorized_assessment.analysis.coverage_matrix import COVERAGE_SUBSTATUSES
    except Exception as exc:  # noqa: BLE001
        violations.append(f"coverage_matrix import failed: {exc}")
    else:
        if tuple(data.get("category_status_values") or ()) != COVERAGE_SUBSTATUSES:
            violations.append(
                "category_status_values drift: injection_candidate_schema vs COVERAGE_SUBSTATUSES"
            )
    if tuple(data.get("definitive_result_statuses") or ()) != tuple(ic.DEFINITIVE_RESULT_STATUSES):
        violations.append(
            f"definitive_result_statuses drift: {data.get('definitive_result_statuses')!r} "
            f"!= {list(ic.DEFINITIVE_RESULT_STATUSES)!r}"
        )
    screening = data.get("category_screening")
    if not isinstance(screening, dict) or set(screening) != set(ic.CATEGORY_SCREENING):
        violations.append("injection_candidate_schema.category_screening missing or drifted")
    else:
        for phase, cats in screening.items():
            if tuple(cats or ()) != ic.CATEGORY_SCREENING[phase]:
                violations.append(
                    f"injection_candidate_schema.category_screening.{phase} drift: {cats!r}"
                )
    evidence_kinds = data.get("evidence_kinds") or []
    if isinstance(evidence_kinds, list) and not set(
        data.get("insufficient_evidence_kinds") or []
    ) <= set(evidence_kinds):
        violations.append("injection_candidate_schema.insufficient_evidence_kinds not subset of evidence_kinds")
    rules = data.get("upgrade_rules")
    if not isinstance(rules, dict) or set(rules) != set(ic.INJECTION_CATEGORIES):
        violations.append(
            "injection_candidate_schema.upgrade_rules must cover exactly all 15 categories"
        )
    if isinstance(rules, dict):
        for category, rule in rules.items():
            for kind in (rule or {}).get("required_all") or []:
                if kind not in evidence_kinds:
                    violations.append(
                        f"injection_candidate_schema.upgrade_rules.{category} unknown evidence kind: {kind!r}"
                    )
            for group in (rule or {}).get("required_any_groups") or []:
                if not isinstance(group, list) or not group:
                    violations.append(
                        f"injection_candidate_schema.upgrade_rules.{category} empty evidence group"
                    )
                    continue
                for kind in group:
                    if kind not in evidence_kinds:
                        violations.append(
                            f"injection_candidate_schema.upgrade_rules.{category} unknown evidence kind: {kind!r}"
                        )
            for branch in (rule or {}).get("required_any_branches") or []:
                if not isinstance(branch, list) or not branch:
                    violations.append(
                        f"injection_candidate_schema.upgrade_rules.{category} empty evidence branch"
                    )
                    continue
                for kind in branch:
                    if kind not in evidence_kinds:
                        violations.append(
                            f"injection_candidate_schema.upgrade_rules.{category} unknown evidence kind: {kind!r}"
                        )
            if _injection_rule_shape(rule) != _injection_rule_shape(ic._UPGRADE_RULES.get(category)):
                violations.append(
                    f"injection_candidate_schema.upgrade_rules.{category} drift against module rules"
                )
    if not isinstance(data.get("row_rules"), dict) or not data["row_rules"]:
        violations.append("injection_candidate_schema.row_rules missing or empty")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append("injection_candidate_schema.invariants missing or empty")
    if tuple(data.get("candidate_status_values") or ()) != finding_quality_gate.FINDING_STATUS_STATES:
        violations.append(
            "candidate status states drift between injection_candidate_schema and finding quality gate module"
        )
    return violations


def check_graphql_schema(root: Path) -> list[str]:
    """Batch 7：graphql 契约 ↔ graphql_review/graphql_inventory 模块 ↔ finding 8 状态交叉。"""
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "graphql_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    try:
        from authorized_assessment.triage import graphql_inventory, graphql_review
        from authorized_assessment.quality import finding_quality_gate
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"graphql modules import failed: {exc}"]
    for schema_key, module_constant in (
        ("review_categories", graphql_review.GRAPHQL_CATEGORIES),
        ("evidence_kinds", graphql_review.GRAPHQL_EVIDENCE_KINDS),
        ("insufficient_evidence_kinds", graphql_review.GRAPHQL_INSUFFICIENT_EVIDENCE_KINDS),
        ("candidate_status_values", graphql_review.ic.CANDIDATE_STATUS_VALUES),
        ("applicable_values", graphql_review.ic.APPLICABLE_VALUES),
        ("definitive_result_statuses", graphql_review.ic.DEFINITIVE_RESULT_STATUSES),
    ):
        schema_value = data.get(schema_key)
        if not isinstance(schema_value, list) or tuple(schema_value) != tuple(module_constant):
            violations.append(
                f"graphql_schema.{schema_key} drift: {schema_value!r} != {list(module_constant)!r}"
            )
    try:
        from authorized_assessment.analysis.coverage_matrix import COVERAGE_SUBSTATUSES
    except Exception as exc:  # noqa: BLE001
        violations.append(f"coverage_matrix import failed: {exc}")
    else:
        if tuple(data.get("category_status_values") or ()) != COVERAGE_SUBSTATUSES:
            violations.append(
                "category_status_values drift: graphql_schema vs COVERAGE_SUBSTATUSES"
            )
    inventory = data.get("inventory")
    if not isinstance(inventory, dict):
        violations.append("graphql_schema.inventory missing")
    else:
        if tuple(inventory.get("row_fields") or ()) != tuple(graphql_inventory.INVENTORY_ROW_FIELDS):
            violations.append("graphql_schema.inventory.row_fields drift against module")
        if tuple(inventory.get("surface_kinds") or ()) != tuple(graphql_inventory.GRAPHQL_SURFACE_KINDS):
            violations.append("graphql_schema.inventory.surface_kinds drift against module")
        if not isinstance(inventory.get("row_rules"), dict) or not inventory["row_rules"]:
            violations.append("graphql_schema.inventory.row_rules missing or empty")
    evidence_kinds = data.get("evidence_kinds") or []
    if isinstance(evidence_kinds, list) and not set(
        data.get("insufficient_evidence_kinds") or []
    ) <= set(evidence_kinds):
        violations.append("graphql_schema.insufficient_evidence_kinds not subset of evidence_kinds")
    rules = data.get("upgrade_rules")
    if not isinstance(rules, dict) or set(rules) != set(graphql_review.GRAPHQL_UPGRADE_RULES):
        violations.append(
            "graphql_schema.upgrade_rules drift: must match module rules exactly"
            "（不在表内的类别永不升级）"
        )
    if isinstance(rules, dict):
        for category, rule in rules.items():
            schema_shape = (
                tuple(rule.get("required_all") or ()),
                tuple(tuple(g) for g in rule.get("required_any_groups") or ()),
                tuple(tuple(b) for b in rule.get("required_any_branches") or ()),
            )
            module_shape = (
                tuple((graphql_review.GRAPHQL_UPGRADE_RULES.get(category) or {}).get("required_all") or ()),
                tuple(tuple(g) for g in (graphql_review.GRAPHQL_UPGRADE_RULES.get(category) or {}).get("required_any_groups") or ()),
                tuple(tuple(b) for b in (graphql_review.GRAPHQL_UPGRADE_RULES.get(category) or {}).get("required_any_branches") or ()),
            )
            if schema_shape != module_shape:
                violations.append(
                    f"graphql_schema.upgrade_rules.{category} drift against module rules"
                )
            check_groups = list(rule.get("required_any_groups") or []) + list(
                rule.get("required_any_branches") or []
            )
            if rule.get("required_all"):
                check_groups.append(list(rule["required_all"]))
            for group in check_groups:
                if not isinstance(group, list) or not group:
                    violations.append(
                        f"graphql_schema.upgrade_rules.{category} empty evidence group"
                    )
                    continue
                for kind in group:
                    if kind not in evidence_kinds:
                        violations.append(
                            f"graphql_schema.upgrade_rules.{category} unknown evidence kind: {kind!r}"
                        )
    never_upgrade = set(data.get("review_categories") or []) - set(rules or {})
    documented_never = {"introspection_exposure", "field_suggestion"}
    if never_upgrade != documented_never:
        violations.append(
            f"graphql_schema.never_upgrade_rule drift: 永不升级类别 {sorted(never_upgrade)} "
            f"与契约文档 {sorted(documented_never)} 不一致"
        )
    if tuple(data.get("candidate_status_values") or ()) != finding_quality_gate.FINDING_STATUS_STATES:
        violations.append(
            "candidate status states drift between graphql_schema and finding quality gate module"
        )
    observation = data.get("observation_schema")
    if not isinstance(observation, dict) or not observation.get("fields"):
        violations.append("graphql_schema.observation_schema missing or empty")
    else:
        if observation.get("version") != graphql_review.ic.OBSERVATION_SCHEMA_VERSION:
            violations.append(
                f"observation_schema.version drift: {observation.get('version')!r} "
                f"!= {graphql_review.ic.OBSERVATION_SCHEMA_VERSION!r}"
            )
        schema_fields = observation.get("fields")
        if isinstance(schema_fields, dict) and tuple(sorted(schema_fields)) != tuple(
            sorted(graphql_review.OBSERVATION_FIELD_DOCS)
        ):
            violations.append(
                "observation_schema.fields drift against graphql_review.OBSERVATION_FIELD_DOCS"
            )
        for key in ("versioning_rule", "not_proof_semantics", "source_required"):
            if not str(observation.get(key) or "").strip():
                violations.append(f"observation_schema.{key} missing or empty")
    if not isinstance(data.get("row_rules"), dict) or not data["row_rules"]:
        violations.append("graphql_schema.row_rules missing or empty")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append("graphql_schema.invariants missing or empty")
    return violations


def check_api_reconciliation_schema(root: Path) -> list[str]:
    """Batch 8（操作员决定⑤⑥）：对账契约 ↔ api_inventory_reconcile 模块同源校验
    + 序列化确定性探针。第 9 契约。"""
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "api_reconciliation_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    try:
        from authorized_assessment.analysis import api_inventory_reconcile as air
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"api_inventory_reconcile import failed: {exc}"]

    def _tuple(value: object) -> tuple:
        return tuple(value) if isinstance(value, list) else ()

    for schema_key, module_constant in (
        ("reconciliation_statuses", air.RECONCILIATION_STATUSES),
        ("object_field_authorization", None),  # 嵌套节单独处理
    ):
        if schema_key == "object_field_authorization":
            continue
        schema_value = data.get(schema_key)
        if not isinstance(schema_value, list) or tuple(schema_value) != tuple(module_constant):
            violations.append(
                f"api_reconciliation_schema.{schema_key} drift: {schema_value!r} != {list(module_constant)!r}"
            )
    # 版本化定义（决定⑥）：登记表/shadow 表/版本字段同源
    versioned = data.get("versioned_definition")
    if not isinstance(versioned, dict):
        violations.append("api_reconciliation_schema.versioned_definition missing")
    else:
        if tuple(versioned.get("version_labels") or ()) != tuple(air.VERSION_LABELS):
            violations.append("api_reconciliation_schema.version_labels drift against module")
        if tuple(versioned.get("shadow_markers") or ()) != tuple(air.SHADOW_MARKERS):
            violations.append("api_reconciliation_schema.shadow_markers drift against module")
        if versioned.get("api_inventory_schema_version") != air.API_INVENTORY_SCHEMA_VERSION:
            violations.append(
                "api_inventory_schema_version drift: contract vs module constant"
            )
        if not str(versioned.get("versioning_rule") or "").strip():
            violations.append("versioned_definition.versioning_rule missing or empty")
    # 子状态枚举（决定②）
    ofa = data.get("object_field_authorization")
    if not isinstance(ofa, dict):
        violations.append("api_reconciliation_schema.object_field_authorization missing")
    else:
        if tuple(ofa.get("statuses") or ()) != tuple(air.OBJECT_FIELD_AUTHORIZATION_STATUSES):
            violations.append("object_field_authorization.statuses drift against module")
        if ofa.get("default") != "inconclusive":
            violations.append("object_field_authorization.default must be inconclusive")
        if not str(ofa.get("not_proof_semantics") or "").strip():
            violations.append("object_field_authorization.not_proof_semantics missing")
    # 状态语义与优先级（决定⑤）
    semantics = data.get("status_semantics")
    if not isinstance(semantics, dict) or set(semantics) != set(air.RECONCILIATION_STATUSES):
        violations.append("status_semantics must cover reconciliation_statuses exactly")
    if not str(data.get("status_priority_rule") or "").strip():
        violations.append("status_priority_rule missing or empty")
    # 来源语义（决定⑥：A-E 含义入契约）
    sources = data.get("source_kinds")
    if not isinstance(sources, dict) or not set(ck_sources()) <= set(sources):
        violations.append("source_kinds must document A-E + unknown")
    if not str(data.get("source_kind_rule") or "").strip():
        violations.append("source_kind_rule missing or empty")
    # CSV 产物契约（决定⑥）：表头同源 + 序列化确定性探针
    artifacts = data.get("csv_artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("files"), dict):
        violations.append("csv_artifacts.files missing")
    else:
        files = artifacts["files"]
        inv_fields = (files.get("api-version-inventory.csv") or {}).get("fields")
        if tuple(inv_fields or ()) != tuple(air.API_VERSION_INVENTORY_CSV_FIELDS):
            violations.append("csv_artifacts.api-version-inventory.csv.fields drift against module")
        rec_fields = (files.get("api-reconciliation.csv") or {}).get("fields")
        if tuple(rec_fields or ()) != tuple(air.API_RECONCILIATION_CSV_FIELDS):
            violations.append("csv_artifacts.api-reconciliation.csv.fields drift against module")
        for name in ("resource-control-review.csv", "third-party-boundary.csv"):
            entry = files.get(name) or {}
            if not str(entry.get("owner_module") or "").strip():
                violations.append(f"csv_artifacts.{name}.owner_module missing")
        if not str(artifacts.get("serialization_rule") or "").strip():
            violations.append("csv_artifacts.serialization_rule missing")
    # 序列化确定性探针（决定⑥：同输入两次逐字节相等 + 乱序输入不改变输出）
    probe = {
        "endpoint_or_surface": "/api/v1/users",
        "canonical_host": "api.example.com",
        "http_method": "GET",
        "content_type": "application/json",
        "source_kind": "A",
        "declared_version": "1.0",
        "version_label": "v1",
        "shadow_markers": ["test", "staging"],
        "source": "openapi.json",
        "evidence_ref": "",
    }
    first = air.serialize_inventory_row(probe)
    second = air.serialize_inventory_row(dict(reversed(list(probe.items()))))
    if first != second or list(first) != list(air.API_VERSION_INVENTORY_CSV_FIELDS):
        violations.append("serialize_inventory_row is not deterministic or field order drifts")
    if first["shadow_markers"] != "staging|test":
        violations.append("serialize_inventory_row shadow_markers serialization rule broken")
    rec_probe = {
        "applicable": "applicable",
        "status": "matched",
        "source": "s",
        "asset": "h",
        "endpoint_or_surface": "/p",
        "reason": "r",
        "evidence_ref": "e",
        "object_field_authorization": "inconclusive",
    }
    rec_first = air.serialize_reconciliation_row(rec_probe)
    rec_second = air.serialize_reconciliation_row(dict(reversed(list(rec_probe.items()))))
    if rec_first != rec_second or list(rec_first) != list(air.API_RECONCILIATION_CSV_FIELDS):
        violations.append("serialize_reconciliation_row is not deterministic or field order drifts")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append("api_reconciliation_schema.invariants missing or empty")
    return violations


def ck_sources() -> tuple[str, ...]:
    """来源键集合（A-E + unknown；独立函数便于负例替换测试）。"""
    return ("A", "B", "C", "D", "E", "unknown")


def check_miniapp_auth_schema(root: Path) -> list[str]:
    """Batch 10：小程序认证态契约 ↔ miniapp 三模块常量同源校验。第 10 契约。

    校验：phases 三键（branches/artifact 路径/描述非空）↔ 引擎常量；
    artifact_fields 三表头 ↔ 引擎形状常量；coverage_substatus 六值枚举 ↔
    coverage_substatus_schema（单一来源交叉）；authorization_basis/observation
    版本/schema 版本/契约名 ↔ 引擎常量；red_lines/invariants 非空。
    """
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "miniapp_auth_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    try:
        from authorized_assessment.miniapp import platform_login_exchange as eng
        from authorized_assessment.miniapp import session_token_lifecycle as stl
        from authorized_assessment.miniapp import signature_replay_review as srr
        from authorized_assessment.miniapp import signature_replay_l0 as srl
        from authorized_assessment.triage import injection_candidates as ic
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"miniapp auth modules import failed: {exc}"]

    if data.get("contract") != eng.MINIAPP_AUTH_CONTRACT:
        violations.append("miniapp_auth_schema.contract drift against engine")
    if data.get("schema_version") != eng.MINIAPP_AUTH_SCHEMA_VERSION:
        violations.append("miniapp_auth_schema.schema_version drift against engine")
    if data.get("observation_schema_version") != ic.OBSERVATION_SCHEMA_VERSION:
        violations.append("miniapp_auth_schema.observation_schema_version drift")
    phases = data.get("phases")
    if not isinstance(phases, dict) or tuple(phases.keys()) != tuple(eng.AUTH_PHASES):
        violations.append("miniapp_auth_schema.phases must match engine AUTH_PHASES exactly")
        return violations
    branch_sources = {
        "platform_login_exchange": eng.PLATFORM_LOGIN_BRANCHES,
        "session_token_lifecycle": stl.SESSION_TOKEN_BRANCHES,
        "signature_replay": srr.SIGNATURE_REPLAY_BRANCHES,
    }
    for phase, spec in phases.items():
        if not isinstance(spec, dict):
            violations.append(f"miniapp_auth_schema.phases.{phase} must be an object")
            continue
        if tuple(spec.get("branches") or ()) != tuple(branch_sources[phase]):
            violations.append(f"miniapp_auth_schema.phases.{phase}.branches drift against module")
        if spec.get("artifact") != eng.AUTH_REVIEW_ARTIFACTS[phase]:
            violations.append(f"miniapp_auth_schema.phases.{phase}.artifact drift against module")
        if not str(spec.get("description") or "").strip():
            violations.append(f"miniapp_auth_schema.phases.{phase}.description missing or empty")
    fields = data.get("artifact_fields")
    if not isinstance(fields, dict):
        violations.append("miniapp_auth_schema.artifact_fields missing")
    else:
        if tuple(fields.get("row_fields") or ()) != tuple(eng.AUTH_REVIEW_ROW_FIELDS):
            violations.append("miniapp_auth_schema.artifact_fields.row_fields drift against engine")
        if tuple(fields.get("summary_fields") or ()) != tuple(eng.AUTH_REVIEW_SUMMARY_FIELDS):
            violations.append(
                "miniapp_auth_schema.artifact_fields.summary_fields drift against engine"
            )
        if tuple(fields.get("artifact_keys") or ()) != tuple(eng.AUTH_REVIEW_ARTIFACT_KEYS):
            violations.append(
                "miniapp_auth_schema.artifact_fields.artifact_keys drift against engine"
            )
    coverage = data.get("coverage_substatus")
    if not isinstance(coverage, dict):
        violations.append("miniapp_auth_schema.coverage_substatus missing")
    else:
        sub, err = _load_json(root / "contracts" / "coverage_substatus_schema.json")
        if err:
            violations.append(err)
        else:
            if tuple(coverage.get("status_values") or ()) != tuple(sub.get("status_values") or ()):
                violations.append(
                    "miniapp_auth_schema.coverage_substatus.status_values drift "
                    "against coverage_substatus_schema"
                )
        if tuple(coverage.get("proven_values") or ()) != ("tested", "not_applicable"):
            violations.append("miniapp_auth_schema.coverage_substatus.proven_values drift")
    if tuple(data.get("authorization_basis_values") or ()) != tuple(eng.AUTHORIZATION_BASIS_VALUES):
        violations.append("miniapp_auth_schema.authorization_basis_values drift against engine")
    if not isinstance(data.get("red_lines"), list) or not data["red_lines"]:
        violations.append("miniapp_auth_schema.red_lines missing or empty")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append("miniapp_auth_schema.invariants missing or empty")
    # P2 ⑧（X-2）：L0 受控重放执行器段 ↔ signature_replay_l0 模块常量同源校验。
    l0 = data.get("l0_executor")
    if not isinstance(l0, dict):
        violations.append("miniapp_auth_schema.l0_executor missing")
    else:
        if l0.get("module") != "src/authorized_assessment/miniapp/signature_replay_l0.py":
            violations.append("miniapp_auth_schema.l0_executor.module drift against module path")
        if l0.get("artifact") != srl.SIGNATURE_REPLAY_L0_ARTIFACT:
            violations.append("miniapp_auth_schema.l0_executor.artifact drift against module")
        if l0.get("mode") != "plan_and_ingest":
            violations.append("miniapp_auth_schema.l0_executor.mode must be plan_and_ingest")
        constraints = l0.get("constraints")
        if not isinstance(constraints, dict):
            violations.append("miniapp_auth_schema.l0_executor.constraints missing")
        else:
            expected_constraints = {
                "allowed_methods": list(srl.L0_ALLOWED_METHODS),
                "endpoint_classes": list(srl.L0_ENDPOINT_CLASSES),
                "allowed_endpoint_class": srl.L0_ALLOWED_ENDPOINT_CLASS,
                "max_endpoints_per_host": srl.L0_MAX_ENDPOINTS_PER_HOST,
                "min_delay_seconds": srl.L0_MIN_DELAY_SECONDS,
                "time_window_offsets_seconds": list(srl.L0_TIME_WINDOW_OFFSETS_SECONDS),
                "replays_per_window": srl.L0_REPLAYS_PER_WINDOW,
                "write_risk_ack_must_be": srl.L0_WRITE_RISK_ACK_MUST_BE,
            }
            for key, expected in expected_constraints.items():
                if constraints.get(key) != expected or type(constraints.get(key)) is not type(expected):
                    violations.append(
                        f"miniapp_auth_schema.l0_executor.constraints.{key} drift: "
                        f"{constraints.get(key)!r} != {expected!r}"
                    )
        if tuple(l0.get("replay_outcomes") or ()) != tuple(srl.L0_REPLAY_OUTCOMES):
            violations.append(
                "miniapp_auth_schema.l0_executor.replay_outcomes drift against module"
            )
        if tuple(l0.get("row_statuses") or ()) != tuple(srl.L0_ROW_STATUSES):
            violations.append("miniapp_auth_schema.l0_executor.row_statuses drift against module")
        if l0.get("row_branch") != srl.L0_ROW_BRANCH:
            violations.append("miniapp_auth_schema.l0_executor.row_branch drift against module")
        if not isinstance(l0.get("red_lines"), list) or not l0["red_lines"]:
            violations.append("miniapp_auth_schema.l0_executor.red_lines missing or empty")
    return violations


def check_miniapp_storage_package_schema(root: Path) -> list[str]:
    """Batch 11：小程序存储/包完整性契约 ↔ miniapp 三模块常量同源校验。第 11 契约。

    校验：phases 三键（branches/artifact 路径/描述非空）↔ 引擎常量；
    artifact_fields 三表头 ↔ 引擎形状常量；coverage_substatus 六值枚举 ↔
    coverage_substatus_schema（单一来源交叉）；authorization_basis/observation
    版本/schema 版本/契约名 ↔ 引擎常量；red_lines/invariants 非空。
    """
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "miniapp_storage_package_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    try:
        from authorized_assessment.miniapp import package_integrity_update as piu
        from authorized_assessment.miniapp import local_data_exposure as lde
        from authorized_assessment.miniapp import crypto_secret_review as csr
        from authorized_assessment.triage import injection_candidates as ic
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"miniapp storage/package modules import failed: {exc}"]

    if data.get("contract") != piu.MINIAPP_STORAGE_PACKAGE_CONTRACT:
        violations.append("miniapp_storage_package_schema.contract drift against engine")
    if data.get("schema_version") != piu.MINIAPP_STORAGE_PACKAGE_SCHEMA_VERSION:
        violations.append("miniapp_storage_package_schema.schema_version drift against engine")
    if data.get("observation_schema_version") != ic.OBSERVATION_SCHEMA_VERSION:
        violations.append("miniapp_storage_package_schema.observation_schema_version drift")
    phases = data.get("phases")
    if not isinstance(phases, dict) or tuple(phases.keys()) != tuple(piu.STORAGE_PACKAGE_PHASES):
        violations.append(
            "miniapp_storage_package_schema.phases must match engine STORAGE_PACKAGE_PHASES exactly"
        )
        return violations
    branch_sources = {
        "package_integrity_update_review": piu.PACKAGE_INTEGRITY_BRANCHES,
        "local_data_exposure": lde.LOCAL_DATA_BRANCHES,
        "crypto_and_secret_handling": csr.CRYPTO_SECRET_BRANCHES,
    }
    for phase, spec in phases.items():
        if not isinstance(spec, dict):
            violations.append(f"miniapp_storage_package_schema.phases.{phase} must be an object")
            continue
        if tuple(spec.get("branches") or ()) != tuple(branch_sources[phase]):
            violations.append(
                f"miniapp_storage_package_schema.phases.{phase}.branches drift against module"
            )
        if spec.get("artifact") != piu.STORAGE_PACKAGE_REVIEW_ARTIFACTS[phase]:
            violations.append(
                f"miniapp_storage_package_schema.phases.{phase}.artifact drift against module"
            )
        if not str(spec.get("description") or "").strip():
            violations.append(
                f"miniapp_storage_package_schema.phases.{phase}.description missing or empty"
            )
    fields = data.get("artifact_fields")
    if not isinstance(fields, dict):
        violations.append("miniapp_storage_package_schema.artifact_fields missing")
    else:
        if tuple(fields.get("row_fields") or ()) != tuple(piu.REVIEW_ROW_FIELDS):
            violations.append(
                "miniapp_storage_package_schema.artifact_fields.row_fields drift against engine"
            )
        if tuple(fields.get("summary_fields") or ()) != tuple(piu.REVIEW_SUMMARY_FIELDS):
            violations.append(
                "miniapp_storage_package_schema.artifact_fields.summary_fields drift against engine"
            )
        if tuple(fields.get("artifact_keys") or ()) != tuple(piu.REVIEW_ARTIFACT_KEYS):
            violations.append(
                "miniapp_storage_package_schema.artifact_fields.artifact_keys drift against engine"
            )
    coverage = data.get("coverage_substatus")
    if not isinstance(coverage, dict):
        violations.append("miniapp_storage_package_schema.coverage_substatus missing")
    else:
        sub, err = _load_json(root / "contracts" / "coverage_substatus_schema.json")
        if err:
            violations.append(err)
        else:
            if tuple(coverage.get("status_values") or ()) != tuple(sub.get("status_values") or ()):
                violations.append(
                    "miniapp_storage_package_schema.coverage_substatus.status_values drift "
                    "against coverage_substatus_schema"
                )
        if tuple(coverage.get("proven_values") or ()) != ("tested", "not_applicable"):
            violations.append("miniapp_storage_package_schema.coverage_substatus.proven_values drift")
    if tuple(data.get("authorization_basis_values") or ()) != tuple(piu.AUTHORIZATION_BASIS_VALUES):
        violations.append(
            "miniapp_storage_package_schema.authorization_basis_values drift against engine"
        )
    if not isinstance(data.get("red_lines"), list) or not data["red_lines"]:
        violations.append("miniapp_storage_package_schema.red_lines missing or empty")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append("miniapp_storage_package_schema.invariants missing or empty")
    return violations


def check_miniapp_reconciliation_schema(root: Path) -> list[str]:
    """Batch 12：小程序 static/dynamic 对账契约 ↔ 对账模块常量同源校验。第 12 契约。

    校验：phases 单键（branches/artifact/csv_fields/endpoint_states/judgment_states）
    ↔ 模块常量；十值端点状态为 CSV 行级枚举（与 coverage_substatus 六值不同源，
    交集恰 needs_manual_validation）；coverage_substatus 六值枚举 ↔
    coverage_substatus_schema（单一来源交叉）；契约名/schema 版本 ↔ 模块常量；
    red_lines/invariants 非空。
    """
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "miniapp_reconciliation_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    try:
        from authorized_assessment.miniapp import static_dynamic_reconciliation as sdr
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"miniapp reconciliation module import failed: {exc}"]

    if data.get("contract") != sdr.MINIAPP_RECONCILIATION_CONTRACT:
        violations.append("miniapp_reconciliation_schema.contract drift against engine")
    if data.get("schema_version") != sdr.MINIAPP_RECONCILIATION_SCHEMA_VERSION:
        violations.append("miniapp_reconciliation_schema.schema_version drift against engine")
    phases = data.get("phases")
    if not isinstance(phases, dict) or tuple(phases.keys()) != (sdr.RECONCILIATION_PHASE,):
        violations.append(
            "miniapp_reconciliation_schema.phases must match engine RECONCILIATION_PHASE exactly"
        )
        return violations
    spec = phases[sdr.RECONCILIATION_PHASE]
    if not isinstance(spec, dict):
        violations.append(
            f"miniapp_reconciliation_schema.phases.{sdr.RECONCILIATION_PHASE} must be an object"
        )
        return violations
    if tuple(spec.get("branches") or ()) != tuple(sdr.RECONCILIATION_BRANCHES):
        violations.append(
            "miniapp_reconciliation_schema.phases.static_dynamic_reconciliation.branches drift "
            "against module"
        )
    if spec.get("artifact") != sdr.RECONCILIATION_ARTIFACT:
        violations.append(
            "miniapp_reconciliation_schema.phases.static_dynamic_reconciliation.artifact drift "
            "against module"
        )
    if tuple(spec.get("csv_fields") or ()) != tuple(sdr.RECONCILIATION_CSV_FIELDS):
        violations.append(
            "miniapp_reconciliation_schema.phases.static_dynamic_reconciliation.csv_fields drift "
            "against module"
        )
    if tuple(spec.get("endpoint_states") or ()) != tuple(sdr.RECONCILIATION_ENDPOINT_STATES):
        violations.append(
            "miniapp_reconciliation_schema.phases.static_dynamic_reconciliation.endpoint_states "
            "drift against module"
        )
    if tuple(spec.get("judgment_states") or ()) != tuple(sdr.RECONCILIATION_JUDGMENT_STATES):
        violations.append(
            "miniapp_reconciliation_schema.phases.static_dynamic_reconciliation.judgment_states "
            "drift against module"
        )
    if not str(spec.get("description") or "").strip():
        violations.append(
            "miniapp_reconciliation_schema.phases.static_dynamic_reconciliation.description "
            "missing or empty"
        )
    coverage = data.get("coverage_substatus")
    if not isinstance(coverage, dict):
        violations.append("miniapp_reconciliation_schema.coverage_substatus missing")
    else:
        sub, err = _load_json(root / "contracts" / "coverage_substatus_schema.json")
        if err:
            violations.append(err)
        else:
            sub_values = tuple(sub.get("status_values") or ())
            if tuple(coverage.get("status_values") or ()) != sub_values:
                violations.append(
                    "miniapp_reconciliation_schema.coverage_substatus.status_values drift "
                    "against coverage_substatus_schema"
                )
            # 十值行级枚举与六值覆盖枚举不同源：交集恰为 needs_manual_validation
            row_states = set(spec.get("endpoint_states") or ())
            if row_states & set(sub_values) != {"needs_manual_validation"}:
                violations.append(
                    "miniapp_reconciliation_schema.endpoint_states overlap with "
                    "coverage_substatus_schema must be exactly needs_manual_validation"
                )
    if not isinstance(data.get("red_lines"), list) or not data["red_lines"]:
        violations.append("miniapp_reconciliation_schema.red_lines missing or empty")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append("miniapp_reconciliation_schema.invariants missing or empty")
    return violations


def check_miniapp_cloud_schema(root: Path) -> list[str]:
    """Batch 12：小程序云三模块契约 ↔ 云模块常量同源校验。第 13 契约。

    校验：phases 三键（branches/artifact/artifact_format/description）↔ 引擎常量；
    review JSON 形状 phase ↔ artifact_fields 三表头；CSV 形状 phase ↔ csv_fields/
    service_types/attribution_values（attribution 与 audit KNOWN_HOST_STATES 集合
    相等）；coverage_substatus 交叉；契约名/schema 版本/observation 版本/
    authorization_basis ↔ 引擎常量；red_lines/invariants 非空。
    """
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "miniapp_cloud_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    try:
        from authorized_assessment.miniapp import cloud_function_review as cfr
        from authorized_assessment.miniapp import cloud_storage_review as csr
        from authorized_assessment.miniapp import third_party_boundary_review as tpb
        from authorized_assessment.triage import injection_candidates as ic
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"miniapp cloud modules import failed: {exc}"]

    if data.get("contract") != cfr.MINIAPP_CLOUD_CONTRACT:
        violations.append("miniapp_cloud_schema.contract drift against engine")
    if data.get("schema_version") != cfr.MINIAPP_CLOUD_SCHEMA_VERSION:
        violations.append("miniapp_cloud_schema.schema_version drift against engine")
    if data.get("observation_schema_version") != ic.OBSERVATION_SCHEMA_VERSION:
        violations.append("miniapp_cloud_schema.observation_schema_version drift")
    phases = data.get("phases")
    if not isinstance(phases, dict) or tuple(phases.keys()) != tuple(cfr.CLOUD_PHASES):
        violations.append(
            "miniapp_cloud_schema.phases must match engine CLOUD_PHASES exactly"
        )
        return violations
    branch_sources = {
        "cloud_function_testing": cfr.CLOUD_FUNCTION_BRANCHES,
        "cloud_storage_acl_testing": csr.CLOUD_STORAGE_BRANCHES,
        "third_party_platform_boundary": tpb.THIRD_PARTY_BRANCHES,
    }
    format_sources = {
        "cloud_function_testing": "review_json",
        "cloud_storage_acl_testing": "review_json",
        "third_party_platform_boundary": "csv",
    }
    for phase, spec in phases.items():
        if not isinstance(spec, dict):
            violations.append(f"miniapp_cloud_schema.phases.{phase} must be an object")
            continue
        if tuple(spec.get("branches") or ()) != tuple(branch_sources[phase]):
            violations.append(
                f"miniapp_cloud_schema.phases.{phase}.branches drift against module"
            )
        if spec.get("artifact") != cfr.CLOUD_REVIEW_ARTIFACTS[phase]:
            violations.append(
                f"miniapp_cloud_schema.phases.{phase}.artifact drift against module"
            )
        if spec.get("artifact_format") != format_sources[phase]:
            violations.append(
                f"miniapp_cloud_schema.phases.{phase}.artifact_format drift against module"
            )
        if not str(spec.get("description") or "").strip():
            violations.append(
                f"miniapp_cloud_schema.phases.{phase}.description missing or empty"
            )
    fields = data.get("artifact_fields")
    if not isinstance(fields, dict):
        violations.append("miniapp_cloud_schema.artifact_fields missing")
    else:
        if tuple(fields.get("row_fields") or ()) != tuple(cfr.CLOUD_REVIEW_ROW_FIELDS):
            violations.append(
                "miniapp_cloud_schema.artifact_fields.row_fields drift against engine"
            )
        if tuple(fields.get("summary_fields") or ()) != tuple(cfr.CLOUD_REVIEW_SUMMARY_FIELDS):
            violations.append(
                "miniapp_cloud_schema.artifact_fields.summary_fields drift against engine"
            )
        if tuple(fields.get("artifact_keys") or ()) != tuple(cfr.CLOUD_REVIEW_ARTIFACT_KEYS):
            violations.append(
                "miniapp_cloud_schema.artifact_fields.artifact_keys drift against engine"
            )
        if tuple(fields.get("review_json_phases") or ()) != tuple(cfr.CLOUD_REVIEW_JSON_PHASES):
            violations.append(
                "miniapp_cloud_schema.artifact_fields.review_json_phases drift against engine"
            )
    tp_spec = phases.get("third_party_platform_boundary")
    if isinstance(tp_spec, dict):
        if tuple(tp_spec.get("csv_fields") or ()) != tuple(tpb.THIRD_PARTY_CSV_FIELDS):
            violations.append(
                "miniapp_cloud_schema.phases.third_party_platform_boundary.csv_fields drift "
                "against module"
            )
        if tuple(tp_spec.get("service_types") or ()) != tuple(tpb.THIRD_PARTY_SERVICE_TYPES):
            violations.append(
                "miniapp_cloud_schema.phases.third_party_platform_boundary.service_types drift "
                "against module"
            )
        if set(tp_spec.get("attribution_values") or []) != set(tpb.THIRD_PARTY_ATTRIBUTION_VALUES):
            violations.append(
                "miniapp_cloud_schema.phases.third_party_platform_boundary.attribution_values "
                "drift against module"
            )
    coverage = data.get("coverage_substatus")
    if not isinstance(coverage, dict):
        violations.append("miniapp_cloud_schema.coverage_substatus missing")
    else:
        sub, err = _load_json(root / "contracts" / "coverage_substatus_schema.json")
        if err:
            violations.append(err)
        else:
            if tuple(coverage.get("status_values") or ()) != tuple(sub.get("status_values") or ()):
                violations.append(
                    "miniapp_cloud_schema.coverage_substatus.status_values drift "
                    "against coverage_substatus_schema"
                )
        if tuple(coverage.get("proven_values") or ()) != ("tested", "not_applicable"):
            violations.append("miniapp_cloud_schema.coverage_substatus.proven_values drift")
    if tuple(data.get("authorization_basis_values") or ()) != tuple(cfr.AUTHORIZATION_BASIS_VALUES):
        violations.append(
            "miniapp_cloud_schema.authorization_basis_values drift against engine"
        )
    if not isinstance(data.get("red_lines"), list) or not data["red_lines"]:
        violations.append("miniapp_cloud_schema.red_lines missing or empty")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append("miniapp_cloud_schema.invariants missing or empty")
    return violations


def check_miniapp_webview_schema(root: Path) -> list[str]:
    """Batch 13：WebView/Bridge/Deep Link 契约 ↔ audit skill 脚本常量同源校验。
    第 14 契约。webview 域无 src 模块（规格 6.8 既有 phase 增固定产物，batch13_0
    D4），实现常量即 canonical audit 脚本（importlib 按路径离线加载，与测试同法）。

    校验：phases 单键（branches）↔ audit WEBVIEW_REVIEW_BRANCHES；三 artifacts 段
    （artifact 路径/各自 branches/1:1 无交集并集恰等/csv_fields/row_enums/判定
    reason 子集）↔ audit 常量；coverage_substatus 交叉；red_lines/invariants 非空。
    """
    violations: list[str] = []
    data, err = _load_json(root / "contracts" / "miniapp_webview_schema.json")
    if err:
        return [err]
    assert isinstance(data, dict)
    # 实现常量从真实仓库加载（SCRIPT_ROOT，与 src 模块经 sys.path 导入同向）；
    # 契约数据从 --root 读取，篡改负例才有意义。
    audit_script = SCRIPT_ROOT / ".agents" / "skills" / "xcx" / "scripts" / "audit_miniapp_engagement.py"
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "validate_webview_audit_script", audit_script
        )
        audit_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit_mod)
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"miniapp webview audit script load failed: {exc}"]

    if data.get("contract") != "miniapp_webview_schema":
        violations.append("miniapp_webview_schema.contract must be miniapp_webview_schema")
    if data.get("schema_version") != "1.0":
        violations.append("miniapp_webview_schema.schema_version drift")
    phases = data.get("phases")
    branch_map = audit_mod.WEBVIEW_REVIEW_BRANCHES
    if not isinstance(phases, dict) or tuple(phases.keys()) != tuple(branch_map):
        violations.append(
            "miniapp_webview_schema.phases must match audit WEBVIEW_REVIEW_BRANCHES exactly"
        )
        return violations
    phase_spec = phases["webview_bridge_links"]
    if not isinstance(phase_spec, dict):
        violations.append("miniapp_webview_schema.phases.webview_bridge_links must be an object")
        return violations
    if tuple(phase_spec.get("branches") or ()) != tuple(
        branch_map["webview_bridge_links"]
    ):
        violations.append(
            "miniapp_webview_schema.phases.webview_bridge_links.branches drift against audit script"
        )
    if phase_spec.get("artifact_format") != "csv":
        violations.append("miniapp_webview_schema.phases.webview_bridge_links.artifact_format drift")
    artifacts = phase_spec.get("artifacts")
    expected_artifacts = (
        (
            audit_mod.WEBVIEW_ORIGIN_INVENTORY_CSV,
            "WEBVIEW_ORIGIN_CSV_FIELDS",
            {"cookie_token_shared": "WEBVIEW_COOKIE_TOKEN_SHARED_VALUES"},
        ),
        (
            audit_mod.WEBVIEW_BRIDGE_METHOD_CSV,
            "WEBVIEW_BRIDGE_CSV_FIELDS",
            {"capability": "WEBVIEW_CAPABILITY_VALUES"},
        ),
        (
            audit_mod.WEBVIEW_DEEP_LINK_QUEUE_CSV,
            "WEBVIEW_DEEP_LINK_CSV_FIELDS",
            {"scheme_type": "WEBVIEW_SCHEME_TYPES", "jump_target": "WEBVIEW_JUMP_TARGETS"},
        ),
    )
    if not isinstance(artifacts, list) or tuple(
        entry.get("artifact") for entry in artifacts if isinstance(entry, dict)
    ) != tuple(item[0] for item in expected_artifacts):
        violations.append(
            "miniapp_webview_schema.phases.webview_bridge_links.artifacts paths drift "
            "against audit script (spec 1667-1669 order)"
        )
        return violations
    # 分支→产物 1:1：无交集、并集恰为七分支，且与 audit WEBVIEW_BRANCH_ARTIFACTS 分组一致
    seen: list[str] = []
    for entry, (rel, fields_name, enums) in zip(artifacts, expected_artifacts):
        if not isinstance(entry, dict):
            continue
        entry_branches = entry.get("branches") or []
        seen.extend(entry_branches)
        mapped = sorted(
            branch for branch, artifact in audit_mod.WEBVIEW_BRANCH_ARTIFACTS.items()
            if artifact == rel
        )
        if sorted(entry_branches) != mapped:
            violations.append(
                f"miniapp_webview_schema.phases.webview_bridge_links.artifacts[{rel}] "
                "branches drift against audit WEBVIEW_BRANCH_ARTIFACTS"
            )
        if tuple(entry.get("csv_fields") or ()) != tuple(getattr(audit_mod, fields_name)):
            violations.append(
                f"miniapp_webview_schema.phases.webview_bridge_links.artifacts[{rel}].csv_fields "
                "drift against audit script"
            )
        row_enums = entry.get("row_enums")
        if not isinstance(row_enums, dict) or set(row_enums) != set(enums):
            violations.append(
                f"miniapp_webview_schema.phases.webview_bridge_links.artifacts[{rel}].row_enums "
                "drift against audit script"
            )
        else:
            for column, constant_name in enums.items():
                if tuple(row_enums.get(column) or ()) != tuple(getattr(audit_mod, constant_name)):
                    violations.append(
                        f"miniapp_webview_schema.phases.webview_bridge_links.artifacts[{rel}]."
                        f"row_enums.{column} drift against audit script"
                    )
        requirements = entry.get("row_requirements")
        if not isinstance(requirements, dict) or not set(
            requirements.get("required_non_empty") or []
        ) <= set(entry.get("csv_fields") or []):
            violations.append(
                f"miniapp_webview_schema.phases.webview_bridge_links.artifacts[{rel}]."
                "row_requirements.required_non_empty must be a subset of csv_fields"
            )
    if len(seen) != len(set(seen)):
        violations.append(
            "miniapp_webview_schema.phases.webview_bridge_links artifacts branches overlap"
        )
    if set(seen) != set(branch_map["webview_bridge_links"]):
        violations.append(
            "miniapp_webview_schema.phases.webview_bridge_links artifacts branch union drift"
        )
    bridge_entry = next(
        (e for e in artifacts if isinstance(e, dict) and e.get("artifact") == audit_mod.WEBVIEW_BRIDGE_METHOD_CSV),
        None,
    )
    if isinstance(bridge_entry, dict):
        requirements = bridge_entry.get("row_requirements") or {}
        if tuple(requirements.get("reason_required_capabilities") or ()) != tuple(
            audit_mod.WEBVIEW_BRIDGE_REASON_CAPABILITIES
        ):
            violations.append(
                "miniapp_webview_schema.phases.webview_bridge_links.reason_required_capabilities "
                "drift against audit script"
            )
    deeplink_entry = next(
        (e for e in artifacts if isinstance(e, dict) and e.get("artifact") == audit_mod.WEBVIEW_DEEP_LINK_QUEUE_CSV),
        None,
    )
    if isinstance(deeplink_entry, dict):
        requirements = deeplink_entry.get("row_requirements") or {}
        if tuple(requirements.get("reason_required_jump_targets") or ()) != tuple(
            audit_mod.WEBVIEW_REASON_JUMP_TARGETS
        ):
            violations.append(
                "miniapp_webview_schema.phases.webview_bridge_links.reason_required_jump_targets "
                "drift against audit script"
            )
    coverage = data.get("coverage_substatus")
    if not isinstance(coverage, dict):
        violations.append("miniapp_webview_schema.coverage_substatus missing")
    else:
        sub, err = _load_json(root / "contracts" / "coverage_substatus_schema.json")
        if err:
            violations.append(err)
        else:
            if tuple(coverage.get("status_values") or ()) != tuple(sub.get("status_values") or ()):
                violations.append(
                    "miniapp_webview_schema.coverage_substatus.status_values drift "
                    "against coverage_substatus_schema"
                )
        if tuple(coverage.get("proven_values") or ()) != ("tested", "not_applicable"):
            violations.append("miniapp_webview_schema.coverage_substatus.proven_values drift")
    if not isinstance(data.get("red_lines"), list) or not data["red_lines"]:
        violations.append("miniapp_webview_schema.red_lines missing or empty")
    if not isinstance(data.get("invariants"), list) or not data["invariants"]:
        violations.append("miniapp_webview_schema.invariants missing or empty")
    return violations


def _app_skill_module(script_name: str) -> tuple[object | None, str | None]:
    """按路径离线加载 .agents/skills/app/scripts/ 下的种子常量脚本（与
    check_miniapp_webview_schema 加载 xcx audit 脚本同法）：实现常量来自真实仓库
    （SCRIPT_ROOT），契约数据来自 --root——篡改负例才有意义。结果进程内缓存。"""
    module = _APP_SKILL_MODULES.get(script_name)
    if module is not None:
        return module, None
    import importlib.util

    path = SCRIPT_ROOT / ".agents" / "skills" / "app" / "scripts" / script_name
    if not path.is_file():
        return None, f"app skill script missing: {script_name}"
    try:
        spec = importlib.util.spec_from_file_location(
            f"validate_app_{script_name[:-3]}", path
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return None, f"app skill script load failed ({script_name}): {exc}"
    _APP_SKILL_MODULES[script_name] = module
    return module, None


def _check_app_common_shape(name: str, data: dict, root: Path) -> list[str]:
    """六个 app 契约的公共结构：schema_version/contract 名/type/phases/red_lines/
    invariants + coverage_substatus 六值枚举 ↔ coverage_substatus_schema 交叉。"""
    violations: list[str] = []
    if data.get("schema_version") != "1.0":
        violations.append(f"{name}.schema_version drift")
    expected_contract = name[: -len(".json")]
    if data.get("contract") != expected_contract:
        violations.append(f"{name}.contract must be {expected_contract}")
    if data.get("type") != "object":
        violations.append(f"{name}.type must be object")
    for field in ("phases", "red_lines", "invariants"):
        value = data.get(field)
        if not isinstance(value, (dict, list)) or not value:
            violations.append(f"{name}.{field} missing or empty")
    coverage = data.get("coverage_substatus")
    if not isinstance(coverage, dict):
        violations.append(f"{name}.coverage_substatus missing")
    else:
        sub, err = _load_json(root / "contracts" / "coverage_substatus_schema.json")
        if err:
            violations.append(err)
        elif tuple(coverage.get("status_values") or ()) != tuple(sub.get("status_values") or ()):
            violations.append(
                f"{name}.coverage_substatus.status_values drift "
                "against coverage_substatus_schema"
            )
        if tuple(coverage.get("proven_values") or ()) != ("tested", "not_applicable"):
            violations.append(f"{name}.coverage_substatus.proven_values drift")
    return violations


def _check_app_phase_specs(name: str, data: dict, init_mod: object) -> list[str]:
    """review/单产物 phase 的逐 phase 校验：branches ↔ init.PHASE_BRANCHES、
    artifact（字符串）↔ init.PHASE_ARTIFACTS、description 非空。"""
    violations: list[str] = []
    phases = data.get("phases")
    if not isinstance(phases, dict):
        return violations
    for phase, spec in phases.items():
        if not isinstance(spec, dict):
            violations.append(f"{name}.phases.{phase} must be an object")
            continue
        if tuple(spec.get("branches") or ()) != tuple(
            init_mod.PHASE_BRANCHES.get(phase, ())  # type: ignore[attr-defined]
        ):
            violations.append(f"{name}.phases.{phase}.branches drift against init seed")
        if spec.get("artifact") != init_mod.PHASE_ARTIFACTS.get(phase, ("",))[0]:  # type: ignore[attr-defined]
            violations.append(f"{name}.phases.{phase}.artifact drift against init seed")
        if not str(spec.get("description") or "").strip():
            violations.append(f"{name}.phases.{phase}.description missing or empty")
    return violations


def _check_app_review_json_fields(name: str, data: dict, init_mod: object, audit_mod: object) -> list[str]:
    """review JSON 契约的形状校验：artifact_fields 三表头 ↔ init.REVIEW_SKELETON_FIELDS
    + 12 键 artifact_keys；observation_schema_version；authorization_basis ↔ audit。"""
    violations: list[str] = []
    fields = data.get("artifact_fields")
    if not isinstance(fields, dict):
        violations.append(f"{name}.artifact_fields missing")
    else:
        if tuple(fields.get("row_fields") or ()) != tuple(
            init_mod.REVIEW_SKELETON_FIELDS["row_fields"]  # type: ignore[attr-defined]
        ):
            violations.append(f"{name}.artifact_fields.row_fields drift against init seed")
        if tuple(fields.get("summary_fields") or ()) != tuple(
            init_mod.REVIEW_SKELETON_FIELDS["summary_fields"]  # type: ignore[attr-defined]
        ):
            violations.append(f"{name}.artifact_fields.summary_fields drift against init seed")
        if tuple(fields.get("artifact_keys") or ()) != APP_REVIEW_ARTIFACT_KEYS:
            violations.append(f"{name}.artifact_fields.artifact_keys drift (12-key review JSON 形状)")
    if data.get("observation_schema_version") != "1.0":
        violations.append(f"{name}.observation_schema_version drift")
    if set(data.get("authorization_basis_values") or ()) != set(
        audit_mod.AUTHORIZATION_BASIS_VALUES  # type: ignore[attr-defined]
    ):
        violations.append(f"{name}.authorization_basis_values drift against audit seed")
    return violations


def _check_app_csv_artifact_entries(
    name: str,
    phase: str,
    entries: object,
    init_mod: object,
    audit_mod: object,
    branch_artifacts: dict[str, str],
    enum_sources: dict[str, dict[str, tuple[str, ...]]],
) -> list[str]:
    """webview/ipc 式多 CSV 产物校验：产物路径 ↔ init.PHASE_ARTIFACTS（顺序敏感）、
    分支分组 ↔ audit branch→artifact 映射（1:1 无交集并集恰等）、csv_fields ↔
    init.REVIEW_CSV_ARTIFACTS、row_enums ↔ audit 行级枚举、required_non_empty
    ⊆ csv_fields。"""
    violations: list[str] = []
    expected_paths = tuple(
        init_mod.PHASE_ARTIFACTS.get(phase, ())  # type: ignore[attr-defined]
    )
    if not isinstance(entries, list):
        violations.append(f"{name}.phases.{phase}.artifacts must be a list")
        return violations
    actual_paths = tuple(
        entry.get("artifact") for entry in entries if isinstance(entry, dict)
    )
    if actual_paths != expected_paths:
        violations.append(
            f"{name}.phases.{phase}.artifacts paths drift against init seed"
        )
        return violations
    seen_branches: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("artifact")
        entry_branches = list(entry.get("branches") or [])
        seen_branches.extend(entry_branches)
        mapped = sorted(
            branch for branch, artifact in branch_artifacts.items() if artifact == rel
        )
        if sorted(entry_branches) != mapped:
            violations.append(
                f"{name}.phases.{phase}.artifacts[{rel}].branches drift against "
                "audit branch-to-artifact map"
            )
        csv_fields = tuple(entry.get("csv_fields") or ())
        if csv_fields != tuple(
            init_mod.REVIEW_CSV_ARTIFACTS.get(rel, ())  # type: ignore[attr-defined]
        ):
            violations.append(
                f"{name}.phases.{phase}.artifacts[{rel}].csv_fields drift against init seed"
            )
        row_enums = entry.get("row_enums")
        expected_enums = enum_sources.get(rel, {})
        if not isinstance(row_enums, dict) or set(row_enums) != set(expected_enums):
            violations.append(
                f"{name}.phases.{phase}.artifacts[{rel}].row_enums drift against audit seed"
            )
        else:
            for column, expected_values in expected_enums.items():
                if tuple(row_enums.get(column) or ()) != tuple(expected_values):
                    violations.append(
                        f"{name}.phases.{phase}.artifacts[{rel}].row_enums.{column} "
                        "drift against audit seed"
                    )
        requirements = entry.get("row_requirements")
        if not isinstance(requirements, dict) or not set(
            requirements.get("required_non_empty") or []
        ) <= set(csv_fields):
            violations.append(
                f"{name}.phases.{phase}.artifacts[{rel}].row_requirements."
                "required_non_empty must be a subset of csv_fields"
            )
    if len(seen_branches) != len(set(seen_branches)):
        violations.append(f"{name}.phases.{phase}.artifacts branches overlap")
    if set(seen_branches) != set(branch_artifacts):
        violations.append(f"{name}.phases.{phase}.artifacts branch union drift")
    return violations


def check_app_contracts(root: Path) -> list[str]:
    """APP 流 B4（W19 上半）：六个 app_* 契约 ↔ app init/audit 种子常量同源校验。

    分支与产物路径的唯一事实源为施工方案附录 B 种子；init（PHASE_BRANCHES/
    PHASE_ARTIFACTS/REVIEW_CSV_ARTIFACTS/REVIEW_SKELETON_FIELDS/
    RECONCILIATION_ENDPOINT_STATES）与 audit（行级枚举/判定子集/authorization_basis）
    自包含复制。引擎侧 src/authorized_assessment/app/ 常量同步留待 B5/B6 接入后
    由 tests/test_app_contract_sync.py 锁定。
    """
    violations: list[str] = []
    init_mod, err = _app_skill_module("init_app_engagement.py")
    if err:
        return [err]
    audit_mod, err = _app_skill_module("audit_app_engagement.py")
    if err:
        return violations + [err]
    assert init_mod is not None and audit_mod is not None

    loaded: dict[str, dict] = {}
    for cname in REQUIRED_APP_CONTRACTS:
        data, err = _load_json(root / "contracts" / cname)
        if err:
            violations.append(err)
            continue
        if not isinstance(data, dict):
            violations.append(f"{cname} must be an object")
            continue
        loaded[cname] = data
        violations += _check_app_common_shape(cname, data, root)

    # --- app_auth_schema：三 phase（5/5/4 分支），review JSON 形状，永不自动重放红线 ---
    auth = loaded.get("app_auth_schema.json")
    if auth is not None:
        phases = auth.get("phases")
        if not isinstance(phases, dict) or tuple(phases.keys()) != tuple(
            init_mod.AUTH_REVIEW_BRANCHES  # type: ignore[attr-defined]
        ):
            violations.append(
                "app_auth_schema.phases must match init AUTH_REVIEW_BRANCHES exactly"
            )
        violations += _check_app_phase_specs("app_auth_schema", auth, init_mod)
        violations += _check_app_review_json_fields(
            "app_auth_schema", auth, init_mod, audit_mod
        )
        red_lines = auth.get("red_lines") or []
        if not any("永不自动重放" in str(line) for line in red_lines):
            violations.append("app_auth_schema.red_lines must contain 永不自动重放 red line")

    # --- app_storage_package_schema：三 phase（7/5/4 分支），secret_candidate 与
    #     APP_NO_REPACKING_RULE 红线在场 ---
    storage = loaded.get("app_storage_package_schema.json")
    if storage is not None:
        expected = tuple(
            init_mod.HARDENING_REVIEW_BRANCHES  # type: ignore[attr-defined]
        ) + tuple(
            init_mod.STORAGE_PACKAGE_REVIEW_BRANCHES  # type: ignore[attr-defined]
        )
        phases = storage.get("phases")
        if not isinstance(phases, dict) or tuple(phases.keys()) != expected:
            violations.append(
                "app_storage_package_schema.phases must match init "
                "HARDENING+STORAGE_PACKAGE branch seeds exactly"
            )
        violations += _check_app_phase_specs("app_storage_package_schema", storage, init_mod)
        violations += _check_app_review_json_fields(
            "app_storage_package_schema", storage, init_mod, audit_mod
        )
        red_lines = storage.get("red_lines") or []
        joined = " ".join(str(line) for line in red_lines)
        if "secret_candidate" not in joined:
            violations.append(
                "app_storage_package_schema.red_lines must contain secret_candidate rule"
            )
        if "APP_NO_REPACKING_RULE" not in joined:
            violations.append(
                "app_storage_package_schema.red_lines must contain APP_NO_REPACKING_RULE"
            )

    # --- app_reconciliation_schema：五分支 + 十态行级枚举 + 判定子集 ---
    recon = loaded.get("app_reconciliation_schema.json")
    if recon is not None:
        phases = recon.get("phases")
        if not isinstance(phases, dict) or tuple(phases.keys()) != (
            "static_dynamic_reconciliation",
        ):
            violations.append(
                "app_reconciliation_schema.phases must be exactly static_dynamic_reconciliation"
            )
        else:
            spec = phases["static_dynamic_reconciliation"]
            if not isinstance(spec, dict):
                violations.append(
                    "app_reconciliation_schema.phases.static_dynamic_reconciliation "
                    "must be an object"
                )
            else:
                artifact = spec.get("artifact")
                if tuple(spec.get("branches") or ()) != tuple(
                    init_mod.PHASE_BRANCHES.get("static_dynamic_reconciliation", ())  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_reconciliation_schema.phases.static_dynamic_reconciliation"
                        ".branches drift against init seed"
                    )
                if artifact != init_mod.PHASE_ARTIFACTS.get(  # type: ignore[attr-defined]
                    "static_dynamic_reconciliation", ("",)
                )[0]:
                    violations.append(
                        "app_reconciliation_schema.phases.static_dynamic_reconciliation"
                        ".artifact drift against init seed"
                    )
                if spec.get("artifact_format") != "csv":
                    violations.append(
                        "app_reconciliation_schema.phases.static_dynamic_reconciliation"
                        ".artifact_format drift"
                    )
                if tuple(spec.get("csv_fields") or ()) != tuple(
                    init_mod.REVIEW_CSV_ARTIFACTS.get(artifact or "", ())  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_reconciliation_schema csv_fields drift against init seed"
                    )
                endpoint_states = tuple(spec.get("endpoint_states") or ())
                if endpoint_states != tuple(
                    init_mod.RECONCILIATION_ENDPOINT_STATES  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_reconciliation_schema.endpoint_states drift against init seed"
                    )
                if tuple(spec.get("judgment_states") or ()) != tuple(
                    audit_mod.RECONCILIATION_JUDGMENT_STATES  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_reconciliation_schema.judgment_states drift against audit seed"
                    )
                sub, sub_err = _load_json(
                    root / "contracts" / "coverage_substatus_schema.json"
                )
                if sub_err:
                    violations.append(sub_err)
                elif set(endpoint_states) & set(
                    (sub or {}).get("status_values") or []
                ) != {"needs_manual_validation"}:
                    violations.append(
                        "app_reconciliation_schema.endpoint_states overlap with "
                        "coverage_substatus_schema must be exactly needs_manual_validation"
                    )
            completion = recon.get("csv_phase_completion_invariant")
            if not isinstance(completion, dict) or not str(
                completion.get("description") or ""
            ).strip():
                violations.append(
                    "app_reconciliation_schema.csv_phase_completion_invariant missing"
                )

    # --- app_webview_schema：七分支 × 三 CSV（路径 artifacts/app/webview/） ---
    webview = loaded.get("app_webview_schema.json")
    if webview is not None:
        phases = webview.get("phases")
        if not isinstance(phases, dict) or tuple(phases.keys()) != ("webview_bridge_links",):
            violations.append(
                "app_webview_schema.phases must be exactly webview_bridge_links"
            )
        else:
            spec = phases["webview_bridge_links"]
            if not isinstance(spec, dict):
                violations.append("app_webview_schema.phases.webview_bridge_links must be an object")
            else:
                if tuple(spec.get("branches") or ()) != tuple(
                    init_mod.PHASE_BRANCHES.get("webview_bridge_links", ())  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_webview_schema.phases.webview_bridge_links.branches "
                        "drift against init seed"
                    )
                if spec.get("artifact_format") != "csv":
                    violations.append(
                        "app_webview_schema.phases.webview_bridge_links.artifact_format drift"
                    )
                if not str(spec.get("boundary_status_rule") or "").strip():
                    violations.append(
                        "app_webview_schema.phases.webview_bridge_links.boundary_status_rule "
                        "missing or empty"
                    )
                violations += _check_app_csv_artifact_entries(
                    "app_webview_schema",
                    "webview_bridge_links",
                    spec.get("artifacts"),
                    init_mod,
                    audit_mod,
                    audit_mod.WEBVIEW_BRANCH_ARTIFACTS,  # type: ignore[attr-defined]
                    {
                        "artifacts/app/webview/webview-origin-inventory.csv": {
                            "cookie_token_shared": audit_mod.WEBVIEW_COOKIE_TOKEN_SHARED_VALUES,  # type: ignore[attr-defined]
                        },
                        "artifacts/app/webview/bridge-method-inventory.csv": {
                            "capability": audit_mod.WEBVIEW_CAPABILITY_VALUES,  # type: ignore[attr-defined]
                        },
                        "artifacts/app/webview/deep-link-review-queue.csv": {
                            "scheme_type": audit_mod.WEBVIEW_SCHEME_TYPES,  # type: ignore[attr-defined]
                            "jump_target": audit_mod.WEBVIEW_JUMP_TARGETS,  # type: ignore[attr-defined]
                        },
                    },
                )
                entries = spec.get("artifacts")
                if isinstance(entries, list):
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        requirements = entry.get("row_requirements") or {}
                        if entry.get("artifact") == "artifacts/app/webview/bridge-method-inventory.csv":
                            if tuple(requirements.get("reason_required_capabilities") or ()) != tuple(
                                audit_mod.WEBVIEW_BRIDGE_REASON_CAPABILITIES  # type: ignore[attr-defined]
                            ):
                                violations.append(
                                    "app_webview_schema.reason_required_capabilities "
                                    "drift against audit seed"
                                )
                        if entry.get("artifact") == "artifacts/app/webview/deep-link-review-queue.csv":
                            if tuple(requirements.get("reason_required_jump_targets") or ()) != tuple(
                                audit_mod.WEBVIEW_REASON_JUMP_TARGETS  # type: ignore[attr-defined]
                            ):
                                violations.append(
                                    "app_webview_schema.reason_required_jump_targets "
                                    "drift against audit seed"
                                )

    # --- app_ipc_schema：七分支 × 两 CSV（artifacts/app/ipc/，App 特有） ---
    ipc = loaded.get("app_ipc_schema.json")
    if ipc is not None:
        phases = ipc.get("phases")
        if not isinstance(phases, dict) or tuple(phases.keys()) != ("ipc_component_boundary",):
            violations.append(
                "app_ipc_schema.phases must be exactly ipc_component_boundary"
            )
        else:
            spec = phases["ipc_component_boundary"]
            if not isinstance(spec, dict):
                violations.append("app_ipc_schema.phases.ipc_component_boundary must be an object")
            else:
                if tuple(spec.get("branches") or ()) != tuple(
                    init_mod.PHASE_BRANCHES.get("ipc_component_boundary", ())  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_ipc_schema.phases.ipc_component_boundary.branches "
                        "drift against init seed"
                    )
                if spec.get("artifact_format") != "csv":
                    violations.append(
                        "app_ipc_schema.phases.ipc_component_boundary.artifact_format drift"
                    )
                if not str(spec.get("boundary_status_rule") or "").strip():
                    violations.append(
                        "app_ipc_schema.phases.ipc_component_boundary.boundary_status_rule "
                        "missing or empty"
                    )
                violations += _check_app_csv_artifact_entries(
                    "app_ipc_schema",
                    "ipc_component_boundary",
                    spec.get("artifacts"),
                    init_mod,
                    audit_mod,
                    audit_mod.IPC_BRANCH_ARTIFACTS,  # type: ignore[attr-defined]
                    {
                        "artifacts/app/ipc/component-inventory.csv": {
                            "component_kind": audit_mod.IPC_COMPONENT_KINDS,  # type: ignore[attr-defined]
                            "exported": audit_mod.IPC_EXPORTED_VALUES,  # type: ignore[attr-defined]
                        },
                        "artifacts/app/ipc/deeplink-review-queue.csv": {
                            "scheme_type": audit_mod.WEBVIEW_SCHEME_TYPES,  # type: ignore[attr-defined]
                            "jump_target": audit_mod.WEBVIEW_JUMP_TARGETS,  # type: ignore[attr-defined]
                        },
                    },
                )
                entries = spec.get("artifacts")
                if isinstance(entries, list):
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        requirements = entry.get("row_requirements") or {}
                        if entry.get("artifact") == "artifacts/app/ipc/component-inventory.csv":
                            if tuple(requirements.get("reason_required_exported_values") or ()) != (
                                "true",
                            ):
                                violations.append(
                                    "app_ipc_schema.reason_required_exported_values "
                                    "drift against audit seed"
                                )
                        if entry.get("artifact") == "artifacts/app/ipc/deeplink-review-queue.csv":
                            if tuple(requirements.get("reason_required_jump_targets") or ()) != tuple(
                                audit_mod.WEBVIEW_REASON_JUMP_TARGETS  # type: ignore[attr-defined]
                            ):
                                violations.append(
                                    "app_ipc_schema.reason_required_jump_targets "
                                    "drift against audit seed"
                                )

    # --- app_cloud_schema：三 phase（3/3/2 分支），两 review JSON + 一 CSV ---
    cloud = loaded.get("app_cloud_schema.json")
    if cloud is not None:
        phases = cloud.get("phases")
        if not isinstance(phases, dict) or tuple(phases.keys()) != tuple(
            init_mod.CLOUD_REVIEW_BRANCHES  # type: ignore[attr-defined]
        ):
            violations.append(
                "app_cloud_schema.phases must match init CLOUD_REVIEW_BRANCHES exactly"
            )
        violations += _check_app_phase_specs("app_cloud_schema", cloud, init_mod)
        violations += _check_app_review_json_fields(
            "app_cloud_schema", cloud, init_mod, audit_mod
        )
        fields = cloud.get("artifact_fields")
        if isinstance(fields, dict) and tuple(fields.get("review_json_phases") or ()) != (
            "cloud_function_testing",
            "cloud_storage_acl_testing",
        ):
            violations.append(
                "app_cloud_schema.artifact_fields.review_json_phases drift"
            )
        if isinstance(phases, dict):
            for phase, expected_format in (
                ("cloud_function_testing", "review_json"),
                ("cloud_storage_acl_testing", "review_json"),
                ("third_party_sdk_platform_boundary", "csv"),
            ):
                spec = phases.get(phase)
                if isinstance(spec, dict) and spec.get("artifact_format") != expected_format:
                    violations.append(
                        f"app_cloud_schema.phases.{phase}.artifact_format drift"
                    )
            tp_spec = phases.get("third_party_sdk_platform_boundary")
            if isinstance(tp_spec, dict):
                if tuple(tp_spec.get("csv_fields") or ()) != tuple(
                    init_mod.REVIEW_CSV_ARTIFACTS.get(  # type: ignore[attr-defined]
                        "artifacts/app/cloud/third-party-boundary.csv", ()
                    )
                ):
                    violations.append(
                        "app_cloud_schema.third_party_sdk_platform_boundary.csv_fields "
                        "drift against init seed"
                    )
                if tuple(tp_spec.get("service_types") or ()) != tuple(
                    audit_mod.THIRD_PARTY_SERVICE_TYPES  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_cloud_schema.third_party_sdk_platform_boundary.service_types "
                        "drift against audit seed"
                    )
                if set(tp_spec.get("attribution_values") or []) != set(
                    audit_mod.THIRD_PARTY_ATTRIBUTION_VALUES  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_cloud_schema.third_party_sdk_platform_boundary."
                        "attribution_values drift against audit seed"
                    )
    return violations


_APP_ENGINE_MODULES: dict[str, object] = {}


def _app_engine_module(module_name: str) -> tuple[object | None, str | None]:
    """按真实仓库加载 src/authorized_assessment/app/ 引擎常量（实现常量来自
    SCRIPT_ROOT，契约数据来自 --root——同 _app_skill_module 模式）。进程内缓存。"""
    module = _APP_ENGINE_MODULES.get(module_name)
    if module is not None:
        return module, None
    try:
        import importlib

        module = importlib.import_module(f"authorized_assessment.app.{module_name}")
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return None, f"app engine module import failed ({module_name}): {exc}"
    _APP_ENGINE_MODULES[module_name] = module
    return module, None


def _check_app_engine_csv_entries(
    name: str,
    phase: str,
    spec: dict,
    engine_mod: object,
    artifacts_attr: str,
    csv_fields_attr: str,
    row_enums_attr: str,
    branch_artifacts_attr: str,
) -> list[str]:
    """webview/ipc 契约的多 CSV 产物 ↔ 引擎常量同步（路径顺序/表头/行级枚举/
    分支→产物映射；engine_mod 属性来自真实仓库）。"""
    violations: list[str] = []
    entries = spec.get("artifacts")
    if not isinstance(entries, list):
        violations.append(f"{name}.phases.{phase}.artifacts must be a list")
        return violations
    actual_paths = tuple(
        entry.get("artifact") for entry in entries if isinstance(entry, dict)
    )
    if actual_paths != tuple(getattr(engine_mod, artifacts_attr)):
        violations.append(f"{name}.phases.{phase}.artifacts paths drift against engine")
        return violations
    csv_fields = getattr(engine_mod, csv_fields_attr)
    row_enums = getattr(engine_mod, row_enums_attr)
    branch_artifacts = getattr(engine_mod, branch_artifacts_attr)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("artifact")
        if tuple(entry.get("csv_fields") or ()) != tuple(csv_fields.get(rel, ())):
            violations.append(
                f"{name}.phases.{phase}.artifacts[{rel}].csv_fields drift against engine"
            )
        expected_enums = row_enums.get(rel, {})
        enums = entry.get("row_enums")
        if not isinstance(enums, dict) or set(enums) != set(expected_enums) or any(
            tuple(enums.get(column) or ()) != tuple(values)
            for column, values in expected_enums.items()
        ):
            violations.append(
                f"{name}.phases.{phase}.artifacts[{rel}].row_enums drift against engine"
            )
        mapped = sorted(
            branch for branch, artifact in branch_artifacts.items() if artifact == rel
        )
        if sorted(entry.get("branches") or []) != mapped:
            violations.append(
                f"{name}.phases.{phase}.artifacts[{rel}].branches drift against engine "
                "branch-to-artifact map"
            )
    return violations


def check_app_engine_sync(root: Path) -> list[str]:
    """APP 流 B5+B6（W19）：契约 ↔ src/authorized_assessment/app/ 引擎常量同步
    校验。B5 覆盖四模块（hardening/static_extraction/webview/ipc）与共享骨架
    （app_review_common 12-key 形状/authorization_basis/coverage 六值）；B6 覆盖
    九模块（auth 三件 + local/crypto + reconciliation + cloud 三件）——至此全部
    app_* 契约↔引擎↔init 种子三处同源。引擎常量取自真实仓库（SCRIPT_ROOT），
    契约数据取 --root（篡改负例有效）。"""
    violations: list[str] = []
    arc_mod, err = _app_engine_module("app_review_common")
    if err:
        return [err]
    hir_mod, err = _app_engine_module("hardening_integrity_review")
    if err:
        return violations + [err]
    wbr_mod, err = _app_engine_module("webview_bridge_review")
    if err:
        return violations + [err]
    ipr_mod, err = _app_engine_module("ipc_component_review")
    if err:
        return violations + [err]
    sex_mod, err = _app_engine_module("static_extraction")
    if err:
        return violations + [err]

    # --- app_storage_package_schema ↔ hardening 引擎 + 共享骨架 ---
    storage, err = _load_json(root / "contracts" / "app_storage_package_schema.json")
    if err:
        violations.append(err)
    else:
        phase = hir_mod.HARDENING_PHASE  # type: ignore[attr-defined]
        spec = (storage.get("phases") or {}).get(phase)
        if not isinstance(spec, dict):
            violations.append(f"app_storage_package_schema.phases.{phase} missing")
        else:
            if tuple(spec.get("branches") or ()) != tuple(
                hir_mod.HARDENING_REVIEW_BRANCHES  # type: ignore[attr-defined]
            ):
                violations.append(
                    f"app_storage_package_schema.phases.{phase}.branches drift against engine"
                )
            if spec.get("artifact") != hir_mod.HARDENING_REVIEW_ARTIFACT:  # type: ignore[attr-defined]
                violations.append(
                    f"app_storage_package_schema.phases.{phase}.artifact drift against engine"
                )
        if storage.get("contract") != hir_mod.APP_STORAGE_PACKAGE_CONTRACT:  # type: ignore[attr-defined]
            violations.append("app_storage_package_schema.contract drift against engine")
        if storage.get("schema_version") != hir_mod.APP_STORAGE_PACKAGE_SCHEMA_VERSION:  # type: ignore[attr-defined]
            violations.append("app_storage_package_schema.schema_version drift against engine")
        # 只观察不绕过：加固特征分支永不升级（契约描述"加固 so 特征只记 signal"）。
        if "hardening_obfuscation_markers" in (
            hir_mod.HARDENING_UPGRADE_RULES  # type: ignore[attr-defined]
        ):
            violations.append(
                "hardening engine must never upgrade hardening_obfuscation_markers "
                "(packer signatures are signal only)"
            )
        fields = storage.get("artifact_fields")
        if isinstance(fields, dict):
            if tuple(fields.get("row_fields") or ()) != tuple(
                arc_mod.APP_REVIEW_ROW_FIELDS  # type: ignore[attr-defined]
            ):
                violations.append(
                    "app_storage_package_schema.artifact_fields.row_fields drift against engine"
                )
            if tuple(fields.get("summary_fields") or ()) != tuple(
                arc_mod.APP_REVIEW_SUMMARY_FIELDS  # type: ignore[attr-defined]
            ):
                violations.append(
                    "app_storage_package_schema.artifact_fields.summary_fields drift against engine"
                )
            if tuple(fields.get("artifact_keys") or ()) != tuple(
                arc_mod.APP_REVIEW_ARTIFACT_KEYS  # type: ignore[attr-defined]
            ):
                violations.append(
                    "app_storage_package_schema.artifact_fields.artifact_keys drift against engine"
                )
        if set(storage.get("authorization_basis_values") or []) != set(
            arc_mod.APP_AUTHORIZATION_BASIS_VALUES  # type: ignore[attr-defined]
        ):
            violations.append(
                "app_storage_package_schema.authorization_basis_values drift against engine"
            )

    # --- app_webview_schema ↔ webview 引擎（含 reason 判定子集） ---
    webview, err = _load_json(root / "contracts" / "app_webview_schema.json")
    if err:
        violations.append(err)
    else:
        spec = (webview.get("phases") or {}).get("webview_bridge_links")
        if not isinstance(spec, dict):
            violations.append("app_webview_schema.phases.webview_bridge_links missing")
        else:
            if tuple(spec.get("branches") or ()) != tuple(
                wbr_mod.WEBVIEW_REVIEW_BRANCHES  # type: ignore[attr-defined]
            ):
                violations.append(
                    "app_webview_schema.phases.webview_bridge_links.branches drift against engine"
                )
            violations += _check_app_engine_csv_entries(
                "app_webview_schema",
                "webview_bridge_links",
                spec,
                wbr_mod,
                "WEBVIEW_ARTIFACTS",
                "WEBVIEW_CSV_FIELDS",
                "WEBVIEW_ROW_ENUMS",
                "WEBVIEW_BRANCH_ARTIFACTS",
            )
            for entry in spec.get("artifacts") or []:
                if not isinstance(entry, dict):
                    continue
                requirements = entry.get("row_requirements") or {}
                if entry.get("artifact") == wbr_mod.WEBVIEW_BRIDGE_METHOD_CSV:  # type: ignore[attr-defined]
                    if tuple(requirements.get("reason_required_capabilities") or ()) != tuple(
                        wbr_mod.WEBVIEW_BRIDGE_REASON_CAPABILITIES  # type: ignore[attr-defined]
                    ):
                        violations.append(
                            "app_webview_schema.reason_required_capabilities drift against engine"
                        )
                if entry.get("artifact") == wbr_mod.WEBVIEW_DEEP_LINK_QUEUE_CSV:  # type: ignore[attr-defined]
                    if tuple(requirements.get("reason_required_jump_targets") or ()) != tuple(
                        wbr_mod.WEBVIEW_REASON_JUMP_TARGETS  # type: ignore[attr-defined]
                    ):
                        violations.append(
                            "app_webview_schema.reason_required_jump_targets drift against engine"
                        )

    # --- app_ipc_schema ↔ ipc 引擎（App 特有，含 exported 判定子集） ---
    ipc, err = _load_json(root / "contracts" / "app_ipc_schema.json")
    if err:
        violations.append(err)
    else:
        spec = (ipc.get("phases") or {}).get("ipc_component_boundary")
        if not isinstance(spec, dict):
            violations.append("app_ipc_schema.phases.ipc_component_boundary missing")
        else:
            if tuple(spec.get("branches") or ()) != tuple(
                ipr_mod.IPC_REVIEW_BRANCHES  # type: ignore[attr-defined]
            ):
                violations.append(
                    "app_ipc_schema.phases.ipc_component_boundary.branches drift against engine"
                )
            violations += _check_app_engine_csv_entries(
                "app_ipc_schema",
                "ipc_component_boundary",
                spec,
                ipr_mod,
                "IPC_ARTIFACTS",
                "IPC_CSV_FIELDS",
                "IPC_ROW_ENUMS",
                "IPC_BRANCH_ARTIFACTS",
            )
            for entry in spec.get("artifacts") or []:
                if not isinstance(entry, dict):
                    continue
                requirements = entry.get("row_requirements") or {}
                if entry.get("artifact") == ipr_mod.IPC_COMPONENT_INVENTORY_CSV:  # type: ignore[attr-defined]
                    if tuple(requirements.get("reason_required_exported_values") or ()) != tuple(
                        ipr_mod.IPC_REASON_EXPORTED_VALUES  # type: ignore[attr-defined]
                    ):
                        violations.append(
                            "app_ipc_schema.reason_required_exported_values drift against engine"
                        )
                if entry.get("artifact") == ipr_mod.IPC_DEEPLINK_QUEUE_CSV:  # type: ignore[attr-defined]
                    if tuple(requirements.get("reason_required_jump_targets") or ()) != tuple(
                        ipr_mod.IPC_REASON_JUMP_TARGETS  # type: ignore[attr-defined]
                    ):
                        violations.append(
                            "app_ipc_schema.reason_required_jump_targets drift against engine"
                        )

    # --- B6：app_auth_schema ↔ auth 三模块引擎（5/5/4 分支） ---
    auth, err = _load_json(root / "contracts" / "app_auth_schema.json")
    if err:
        violations.append(err)
    else:
        ple_mod, m_err = _app_engine_module("platform_login_exchange")
        stl_mod, m_err2 = _app_engine_module("session_token_lifecycle")
        srr_mod, m_err3 = _app_engine_module("signature_replay_review")
        if m_err or m_err2 or m_err3:
            violations.append(m_err or m_err2 or m_err3 or "app auth engine import failed")
        else:
            for mod, phase, branches_attr, artifact_attr in (
                (ple_mod, "platform_login_exchange", "PLATFORM_LOGIN_BRANCHES", "PLATFORM_LOGIN_REVIEW_ARTIFACT"),
                (stl_mod, "session_token_lifecycle", "SESSION_TOKEN_BRANCHES", "SESSION_TOKEN_REVIEW_ARTIFACT"),
                (srr_mod, "signature_replay", "SIGNATURE_REPLAY_BRANCHES", "SIGNATURE_REPLAY_REVIEW_ARTIFACT"),
            ):
                spec = (auth.get("phases") or {}).get(phase)
                if not isinstance(spec, dict):
                    violations.append(f"app_auth_schema.phases.{phase} missing")
                    continue
                if tuple(spec.get("branches") or ()) != tuple(getattr(mod, branches_attr)):
                    violations.append(
                        f"app_auth_schema.phases.{phase}.branches drift against engine"
                    )
                if spec.get("artifact") != getattr(mod, artifact_attr):
                    violations.append(
                        f"app_auth_schema.phases.{phase}.artifact drift against engine"
                    )
            if auth.get("contract") != ple_mod.APP_AUTH_CONTRACT:  # type: ignore[attr-defined]
                violations.append("app_auth_schema.contract drift against engine")
            if auth.get("schema_version") != ple_mod.APP_AUTH_SCHEMA_VERSION:  # type: ignore[attr-defined]
                violations.append("app_auth_schema.schema_version drift against engine")
            if tuple(auth.get("phases") or {}) != tuple(ple_mod.AUTH_PHASES):  # type: ignore[attr-defined]
                violations.append("app_auth_schema.phases must match engine AUTH_PHASES exactly")
            artifacts_map = {p: s.get("artifact") for p, s in (auth.get("phases") or {}).items() if isinstance(s, dict)}
            if artifacts_map != dict(ple_mod.AUTH_REVIEW_ARTIFACTS):  # type: ignore[attr-defined]
                violations.append("app_auth_schema artifact paths drift against engine AUTH_REVIEW_ARTIFACTS")
            fields = auth.get("artifact_fields")
            if isinstance(fields, dict):
                if tuple(fields.get("row_fields") or ()) != tuple(arc_mod.APP_REVIEW_ROW_FIELDS):  # type: ignore[attr-defined]
                    violations.append("app_auth_schema.artifact_fields.row_fields drift against engine")
                if tuple(fields.get("summary_fields") or ()) != tuple(arc_mod.APP_REVIEW_SUMMARY_FIELDS):  # type: ignore[attr-defined]
                    violations.append("app_auth_schema.artifact_fields.summary_fields drift against engine")
                if tuple(fields.get("artifact_keys") or ()) != tuple(arc_mod.APP_REVIEW_ARTIFACT_KEYS):  # type: ignore[attr-defined]
                    violations.append("app_auth_schema.artifact_fields.artifact_keys drift against engine")
            if set(auth.get("authorization_basis_values") or []) != set(
                arc_mod.APP_AUTHORIZATION_BASIS_VALUES  # type: ignore[attr-defined]
            ):
                violations.append("app_auth_schema.authorization_basis_values drift against engine")
            # 红线锚点：signature_replay 永不自动重放任何请求（含只读）。
            if not any("永不自动重放" in inv for inv in srr_mod.SIGNATURE_REPLAY_INVARIANTS):  # type: ignore[attr-defined]
                violations.append(
                    "signature_replay engine invariants must state 永不自动重放任何请求（含只读）"
                )
            if "永不自动重放" not in str(srr_mod.SIGNATURE_REPLAY_OFFLINE_RULE):  # type: ignore[attr-defined]
                violations.append("signature_replay engine offline rule must state 永不自动重放")

    # --- B6：app_storage_package_schema ↔ local/crypto 引擎（5/4 分支 + platform 列） ---
    storage_b6, err = _load_json(root / "contracts" / "app_storage_package_schema.json")
    if err:
        violations.append(err)
    else:
        lde_mod, m_err = _app_engine_module("local_data_exposure")
        csr_mod, m_err2 = _app_engine_module("crypto_secret_review")
        if m_err or m_err2:
            violations.append(m_err or m_err2 or "app storage engine import failed")
        else:
            for mod, phase, branches_attr, artifact_attr in (
                (lde_mod, "local_data_exposure", "LOCAL_DATA_BRANCHES", "LOCAL_DATA_REVIEW_ARTIFACT"),
                (csr_mod, "crypto_and_secret_handling", "CRYPTO_SECRET_BRANCHES", "CRYPTO_SECRET_REVIEW_ARTIFACT"),
            ):
                spec = (storage_b6.get("phases") or {}).get(phase)
                if not isinstance(spec, dict):
                    violations.append(f"app_storage_package_schema.phases.{phase} missing")
                    continue
                if tuple(spec.get("branches") or ()) != tuple(getattr(mod, branches_attr)):
                    violations.append(
                        f"app_storage_package_schema.phases.{phase}.branches drift against engine"
                    )
                if spec.get("artifact") != getattr(mod, artifact_attr):
                    violations.append(
                        f"app_storage_package_schema.phases.{phase}.artifact drift against engine"
                    )
            # 行内 platform 列 android/ios：常量单一来源 + 两模块共享同一筛选实现。
            if lde_mod.APP_PLATFORM_VALUES != ("android", "ios"):  # type: ignore[attr-defined]
                violations.append("local_data engine APP_PLATFORM_VALUES must be (android, ios)")
            if getattr(csr_mod, "screen_platform_tagged_observations", None) is not getattr(
                lde_mod, "screen_platform_tagged_observations", None
            ):
                violations.append(
                    "local_data/crypto platform-tagged screening must share a single "
                    "implementation (hosted in local_data_exposure)"
                )
            # secret_candidate 红线锚点。
            if "secret_candidate" not in str(csr_mod.SECRET_CANDIDATE_RED_LINE):  # type: ignore[attr-defined]
                violations.append(
                    "crypto engine must carry the secret_candidate red line (unproven secrets stay signal)"
                )

    # --- B6：app_reconciliation_schema ↔ 对账引擎（五分支 + 十态 + 判定子集） ---
    recon, err = _load_json(root / "contracts" / "app_reconciliation_schema.json")
    if err:
        violations.append(err)
    else:
        sdr_mod, m_err = _app_engine_module("static_dynamic_reconciliation")
        if m_err:
            violations.append(m_err)
        else:
            spec = (recon.get("phases") or {}).get("static_dynamic_reconciliation")
            if not isinstance(spec, dict):
                violations.append(
                    "app_reconciliation_schema.phases.static_dynamic_reconciliation missing"
                )
            else:
                if tuple(spec.get("branches") or ()) != tuple(sdr_mod.RECONCILIATION_BRANCHES):  # type: ignore[attr-defined]
                    violations.append(
                        "app_reconciliation_schema.branches drift against engine"
                    )
                if spec.get("artifact") != sdr_mod.RECONCILIATION_ARTIFACT:  # type: ignore[attr-defined]
                    violations.append(
                        "app_reconciliation_schema.artifact drift against engine"
                    )
                if tuple(spec.get("csv_fields") or ()) != tuple(sdr_mod.RECONCILIATION_CSV_FIELDS):  # type: ignore[attr-defined]
                    violations.append(
                        "app_reconciliation_schema csv_fields drift against engine"
                    )
                if tuple(spec.get("endpoint_states") or ()) != tuple(sdr_mod.RECONCILIATION_ENDPOINT_STATES):  # type: ignore[attr-defined]
                    violations.append(
                        "app_reconciliation_schema.endpoint_states drift against engine"
                    )
                if tuple(spec.get("judgment_states") or ()) != tuple(sdr_mod.RECONCILIATION_JUDGMENT_STATES):  # type: ignore[attr-defined]
                    violations.append(
                        "app_reconciliation_schema.judgment_states drift against engine"
                    )
            if recon.get("contract") != sdr_mod.APP_RECONCILIATION_CONTRACT:  # type: ignore[attr-defined]
                violations.append("app_reconciliation_schema.contract drift against engine")
            if recon.get("schema_version") != sdr_mod.APP_RECONCILIATION_SCHEMA_VERSION:  # type: ignore[attr-defined]
                violations.append("app_reconciliation_schema.schema_version drift against engine")
            # 红线锚点：对账永不发新请求。
            if "永不发新请求" not in str(sdr_mod.RECONCILIATION_NO_PROBE_RULE):  # type: ignore[attr-defined]
                violations.append(
                    "reconciliation engine must state 永不发新请求 (offline comparison only)"
                )

    # --- B6：app_cloud_schema ↔ cloud 三模块引擎（3/3/2 分支，两 review JSON + 一 CSV） ---
    cloud, err = _load_json(root / "contracts" / "app_cloud_schema.json")
    if err:
        violations.append(err)
    else:
        cfr_mod, m_err = _app_engine_module("cloud_function_review")
        cse_mod, m_err2 = _app_engine_module("cloud_storage_review")
        tpr_mod, m_err3 = _app_engine_module("third_party_boundary_review")
        if m_err or m_err2 or m_err3:
            violations.append(m_err or m_err2 or m_err3 or "app cloud engine import failed")
        else:
            for mod, phase, branches_attr, artifact_attr in (
                (cfr_mod, "cloud_function_testing", "CLOUD_FUNCTION_BRANCHES", "CLOUD_FUNCTION_REVIEW_ARTIFACT"),
                (cse_mod, "cloud_storage_acl_testing", "CLOUD_STORAGE_BRANCHES", "CLOUD_STORAGE_REVIEW_ARTIFACT"),
                (tpr_mod, "third_party_sdk_platform_boundary", "THIRD_PARTY_BRANCHES", "THIRD_PARTY_BOUNDARY_ARTIFACT"),
            ):
                spec = (cloud.get("phases") or {}).get(phase)
                if not isinstance(spec, dict):
                    violations.append(f"app_cloud_schema.phases.{phase} missing")
                    continue
                if tuple(spec.get("branches") or ()) != tuple(getattr(mod, branches_attr)):
                    violations.append(
                        f"app_cloud_schema.phases.{phase}.branches drift against engine"
                    )
                if spec.get("artifact") != getattr(mod, artifact_attr):
                    violations.append(
                        f"app_cloud_schema.phases.{phase}.artifact drift against engine"
                    )
            if cloud.get("contract") != cfr_mod.APP_CLOUD_CONTRACT:  # type: ignore[attr-defined]
                violations.append("app_cloud_schema.contract drift against engine")
            if cloud.get("schema_version") != cfr_mod.APP_CLOUD_SCHEMA_VERSION:  # type: ignore[attr-defined]
                violations.append("app_cloud_schema.schema_version drift against engine")
            if tuple(cloud.get("phases") or {}) != tuple(cfr_mod.APP_CLOUD_PHASES):  # type: ignore[attr-defined]
                violations.append("app_cloud_schema.phases must match engine APP_CLOUD_PHASES exactly")
            artifacts_map = {p: s.get("artifact") for p, s in (cloud.get("phases") or {}).items() if isinstance(s, dict)}
            if artifacts_map != dict(cfr_mod.APP_CLOUD_ARTIFACTS):  # type: ignore[attr-defined]
                violations.append("app_cloud_schema artifact paths drift against engine APP_CLOUD_ARTIFACTS")
            fields = cloud.get("artifact_fields")
            if isinstance(fields, dict) and tuple(fields.get("review_json_phases") or ()) != tuple(
                cfr_mod.APP_CLOUD_REVIEW_JSON_PHASES  # type: ignore[attr-defined]
            ):
                violations.append(
                    "app_cloud_schema.artifact_fields.review_json_phases drift against engine"
                )
            tp_spec = (cloud.get("phases") or {}).get("third_party_sdk_platform_boundary")
            if isinstance(tp_spec, dict):
                if tuple(tp_spec.get("csv_fields") or ()) != tuple(tpr_mod.THIRD_PARTY_CSV_FIELDS):  # type: ignore[attr-defined]
                    violations.append(
                        "app_cloud_schema.third_party_sdk_platform_boundary.csv_fields "
                        "drift against engine"
                    )
                if tuple(tp_spec.get("service_types") or ()) != tuple(tpr_mod.THIRD_PARTY_SERVICE_TYPES):  # type: ignore[attr-defined]
                    violations.append(
                        "app_cloud_schema.third_party_sdk_platform_boundary.service_types "
                        "drift against engine"
                    )
                if set(tp_spec.get("attribution_values") or []) != set(
                    tpr_mod.THIRD_PARTY_ATTRIBUTION_VALUES  # type: ignore[attr-defined]
                ):
                    violations.append(
                        "app_cloud_schema.third_party_sdk_platform_boundary."
                        "attribution_values drift against engine"
                    )

    # --- B6：九模块零网络红线（AST import 扫描；signature_replay 尤其不得含
    #     任何发请求代码路径） ---
    import ast as _ast

    for module_name in (
        "platform_login_exchange",
        "session_token_lifecycle",
        "signature_replay_review",
        "local_data_exposure",
        "crypto_secret_review",
        "static_dynamic_reconciliation",
        "cloud_function_review",
        "cloud_storage_review",
        "third_party_boundary_review",
    ):
        source = (SCRIPT_ROOT / "src" / "authorized_assessment" / "app" / f"{module_name}.py").read_text(
            encoding="utf-8"
        )
        forbidden: set[str] = set()
        for node in _ast.walk(_ast.parse(source)):
            roots: set[str] = set()
            if isinstance(node, _ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, _ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            forbidden |= roots & {"requests", "httpx", "urllib", "urllib3", "socket", "http", "ssl", "subprocess"}
        if forbidden:
            violations.append(
                f"{module_name} must not import network/subprocess modules: {sorted(forbidden)}"
            )

    # --- static_extraction ↔ init 种子与子进程纪律锚点 ---
    init_mod, init_err = _app_skill_module("init_app_engagement.py")
    if init_err:
        violations.append(init_err)
    else:
        if tuple(sex_mod.DECODING_LEDGER_FIELDS) != tuple(  # type: ignore[attr-defined]
            init_mod.DECODING_FIELDS  # type: ignore[attr-defined]
        ):
            violations.append(
                "static_extraction.DECODING_LEDGER_FIELDS drift against init seed"
            )
    if getattr(sex_mod, "DEFAULT_TIMEOUT_SECONDS", None) != 600:  # type: ignore[attr-defined]
        violations.append("static_extraction.DEFAULT_TIMEOUT_SECONDS must be 600 (§7.1)")
    if getattr(sex_mod, "ALLOWED_MANAGED_TOOL_PREFIX", "") != "tools/managed/app":  # type: ignore[attr-defined]
        violations.append("static_extraction.ALLOWED_MANAGED_TOOL_PREFIX drift (managed app tools only)")
    for module_name in ("hardening_integrity_review", "static_extraction"):
        engine, _err = _app_engine_module(module_name)
        doc = str(getattr(engine, "__doc__", "") or "")
        if "只观察不绕过" not in doc:
            violations.append(
                f"{module_name} docstring must state the observe-only red line (只观察不绕过)"
            )
    import re as _re

    static_source = (SCRIPT_ROOT / "src" / "authorized_assessment" / "app" / "static_extraction.py").read_text(
        encoding="utf-8"
    )
    if _re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", static_source):
        violations.append(
            "static_extraction must not hardcode absolute tool paths (resolve from registry/config)"
        )
    return violations


def check_state_model_drift(root: Path = SCRIPT_ROOT) -> list[str]:
    """契约 ↔ 实现常量交叉校验（实现模块来自仓库真实代码；契约读 --root 指向的根）。"""
    violations: list[str] = []
    workflow, err = _load_json(root / "contracts" / "workflow_schema.json")
    quality, err2 = _load_json(root / "contracts" / "run_quality_schema.json")
    if err or err2:
        return [err or err2 or "contract load failed"]

    try:
        import run_lifecycle
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return [f"run_lifecycle import failed: {exc}"]
    try:
        from authorized_assessment.quality import run_quality_gate
        from authorized_assessment.quality.run_quality_gate import GateThresholds
    except Exception as exc:  # noqa: BLE001
        return [f"quality gate import failed: {exc}"]

    assert isinstance(workflow, dict) and isinstance(quality, dict)

    report_states = workflow.get("report_lifecycle_states")
    if isinstance(report_states, list) and tuple(report_states) != run_lifecycle.REPORT_LIFECYCLE_STATES:
        violations.append(
            "report lifecycle drift between workflow_schema and run_lifecycle.REPORT_LIFECYCLE_STATES"
        )
    if "accepted_report" in run_lifecycle.MANUAL_STATES:
        violations.append("run_lifecycle.MANUAL_STATES still contains legacy accepted_report")
    conclusion_allowed = getattr(run_lifecycle, "CONCLUSION_ALLOWED_QUALITY", set())
    if not conclusion_allowed <= set(run_quality_gate.QUALITY_STATUS_STATES):
        violations.append(
            f"run_lifecycle.CONCLUSION_ALLOWED_QUALITY {sorted(conclusion_allowed)} not a subset of quality states"
        )

    schema_quality_states = quality.get("quality_status_states")
    if isinstance(schema_quality_states, list):
        if tuple(schema_quality_states) != run_quality_gate.QUALITY_STATUS_STATES:
            violations.append(
                "quality status states drift between run_quality_schema and quality gate module"
            )
        workflow_quality_states = workflow.get("quality_status_states")
        if isinstance(workflow_quality_states, list) and tuple(workflow_quality_states) != tuple(
            schema_quality_states
        ):
            violations.append(
                "quality status states drift between workflow_schema and run_quality_schema"
            )
    schema_reasons = quality.get("gate_reasons")
    if isinstance(schema_reasons, list) and tuple(schema_reasons) != run_quality_gate.GATE_REASONS:
        violations.append("gate reasons drift between run_quality_schema and quality gate module")

    thresholds = quality.get("gate_thresholds")
    if isinstance(thresholds, dict):
        defaults = GateThresholds().as_dict()
        for key, expected in defaults.items():
            if thresholds.get(key) != expected:
                violations.append(
                    f"gate threshold drift for {key}: schema={thresholds.get(key)!r} implementation={expected!r}"
                )

    try:
        import fh_review_dispatch
    except Exception as exc:  # noqa: BLE001
        violations.append(f"fh_review_dispatch import failed: {exc}")
        return violations
    verdict_enum = getattr(fh_review_dispatch, "VERDICT_ENUM", None)
    review_statuses = workflow.get("review_statuses")
    if isinstance(verdict_enum, list) and isinstance(review_statuses, list):
        unmapped = sorted(set(verdict_enum) - set(review_statuses))
        if unmapped:
            violations.append(
                f"fh verdict dispositions not covered by workflow_schema.review_statuses: {unmapped}"
            )
    verdict_required = getattr(fh_review_dispatch, "VERDICT_REQUIRED", ())
    if not verdict_required:
        violations.append("fh_review_dispatch.VERDICT_REQUIRED missing")

    # Batch 2：finding quality 8 状态三方交叉（finding_quality_schema ↔ 模块 ↔ evidence 契约）。
    finding_quality, err3 = _load_json(root / "contracts" / "finding_quality_schema.json")
    finding_evidence, err4 = _load_json(root / "contracts" / "finding_evidence_schema.json")
    if err3:
        violations.append(err3)
    if err4:
        violations.append(err4)
    if not err3 and not err4:
        try:
            from authorized_assessment.quality import finding_quality_gate
        except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
            violations.append(f"finding quality gate import failed: {exc}")
        else:
            assert isinstance(finding_quality, dict) and isinstance(finding_evidence, dict)
            schema_states = finding_quality.get("finding_status_states")
            if isinstance(schema_states, list) and tuple(schema_states) != finding_quality_gate.FINDING_STATUS_STATES:
                violations.append(
                    "finding status states drift between finding_quality_schema and finding quality gate module"
                )
            evidence_states = finding_evidence.get("finding_status_states")
            if isinstance(schema_states, list) and isinstance(evidence_states, list) and tuple(
                evidence_states
            ) != tuple(schema_states):
                violations.append(
                    "finding status states drift between finding_evidence_schema and finding_quality_schema"
                )

    # Batch 3：candidate identity 契约 ↔ canonical_keys 模块常量无漂移。
    candidate_identity, err5 = _load_json(root / "contracts" / "candidate_identity_schema.json")
    if err5:
        violations.append(err5)
    else:
        assert isinstance(candidate_identity, dict)
        try:
            from authorized_assessment.triage import canonical_keys
        except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
            violations.append(f"canonical_keys import failed: {exc}")
        else:
            schema_key_fields = candidate_identity.get("key_fields") or {}
            for kind, module_constant in (
                ("generic", canonical_keys.GENERIC_KEY_FIELDS),
                ("api", canonical_keys.API_KEY_FIELDS),
                ("miniapp", canonical_keys.MINIAPP_KEY_FIELDS),
            ):
                schema_fields = schema_key_fields.get(kind)
                if isinstance(schema_fields, list) and tuple(schema_fields) != tuple(module_constant):
                    violations.append(
                        "candidate identity key fields drift between candidate_identity_schema"
                        f".key_fields.{kind} and canonical_keys module"
                    )
            schema_merge = (candidate_identity.get("merge_keys") or {}).get("fields")
            if isinstance(schema_merge, list) and tuple(schema_merge) != tuple(
                canonical_keys.MERGE_KEY_FIELDS
            ):
                violations.append(
                    "merge key fields drift between candidate_identity_schema.merge_keys and canonical_keys module"
                )
            schema_cross_run = (candidate_identity.get("cross_run_retention") or {}).get("fields")
            if isinstance(schema_cross_run, list) and tuple(schema_cross_run) != tuple(
                canonical_keys.CROSS_RUN_RETENTION_FIELDS
            ):
                violations.append(
                    "cross-run retention fields drift between candidate_identity_schema and canonical_keys module"
                )
            for schema_key, module_constant in (
                ("http_methods", canonical_keys.HTTP_METHODS),
                ("input_locations", canonical_keys.INPUT_LOCATIONS),
                ("vulnerability_families", canonical_keys.VULNERABILITY_FAMILIES),
                ("parameter_scopes", canonical_keys.PARAMETER_SCOPES),
            ):
                schema_enum = candidate_identity.get(schema_key)
                if isinstance(schema_enum, list) and tuple(schema_enum) != tuple(module_constant):
                    violations.append(
                        f"candidate identity enum drift for {schema_key} between candidate_identity_schema "
                        f"and canonical_keys module"
                    )
            schema_source_kinds = candidate_identity.get("source_kinds") or {}
            if isinstance(schema_source_kinds, dict) and tuple(
                sorted(schema_source_kinds)
            ) != tuple(sorted(canonical_keys.SOURCE_KINDS)):
                violations.append(
                    "source kinds drift between candidate_identity_schema.source_kinds and canonical_keys module"
                )
            schema_quota = (candidate_identity.get("quota_rules") or {}).get(
                "max_per_system_and_family"
            )
            if schema_quota != canonical_keys.QUOTA_MAX_PER_SYSTEM_AND_FAMILY:
                violations.append(
                    f"quota drift: candidate_identity_schema.quota_rules.max_per_system_and_family="
                    f"{schema_quota!r} canonical_keys.QUOTA_MAX_PER_SYSTEM_AND_FAMILY="
                    f"{canonical_keys.QUOTA_MAX_PER_SYSTEM_AND_FAMILY!r}"
                )
    return violations


def check_report_policy_schema(root: Path) -> list[str]:
    """报告策略契约与独立报告配置的关键规则交叉校验。"""
    violations: list[str] = []
    contracts = root / "contracts"
    data, err = _load_json(contracts / "report_policy_schema.json")
    if err:
        return [err]
    if not isinstance(data, dict):
        return ["report_policy_schema must be an object"]
    policy_schema = data.get("properties", {}).get("policy", {})
    required = set(data.get("required") or ())
    expected = {"team_name", "attack_result_template", "auto_generate_attack_report", "screenshot_policy", "policy"}
    if required != expected:
        violations.append(f"report_policy_schema.required drift: {sorted(required)!r}")
    policy_required = set(policy_schema.get("required") or ())
    expected_policy_required = {
        "aggregation_key", "one_result_per_group", "data_scope_mode", "screenshot_mode",
        "include_header_metadata", "include_evidence_section", "include_evidence_file_list",
        "include_reproduction_commands", "preserve_all_commands", "max_problems_or_remediations",
        "include_member_urls", "include_raw_credentials",
    }
    if policy_required != expected_policy_required:
        violations.append(f"report_policy_schema.policy.required drift: {sorted(policy_required)!r}")
    policy_props = policy_schema.get("properties", {})
    for key, expected_value in {
        "include_header_metadata": False,
        "include_evidence_section": False,
        "include_evidence_file_list": False,
        "include_reproduction_commands": True,
        "preserve_all_commands": True,
    }.items():
        if policy_props.get(key, {}).get("const") != expected_value:
            violations.append(f"report_policy_schema {key} must be {expected_value!r}")
    if policy_schema.get("properties", {}).get("screenshot_mode", {}).get("const") != "manual_insert":
        violations.append("report_policy_schema requires manual_insert screenshot mode")
    max_schema = policy_schema.get("properties", {}).get("max_problems_or_remediations", {})
    if max_schema.get("maximum") != 2:
        violations.append("report_policy_schema max problems/remediations must be 2")
    config_path = root / "reporting_config.json"
    if not config_path.is_file():
        config_path = root / "config" / "reporting_config.json"
    if not config_path.is_file():
        return violations + ["reporting_config.json missing for report policy check"]
    try:
        reporting = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return violations + [f"reporting_config.json unparseable: {exc}"]
    if not isinstance(reporting, dict):
        return violations + ["reporting_config.json must be an object"]
    if reporting.get("screenshot_policy") != "manual_insert":
        violations.append("reporting_config.screenshot_policy must be manual_insert")
    actual_policy = reporting.get("policy")
    if not isinstance(actual_policy, dict):
        violations.append("reporting_config.policy missing")
    else:
        if actual_policy.get("aggregation_key") != ["asset_identity", "vulnerability_family"]:
            violations.append("report aggregation key drift")
        if actual_policy.get("one_result_per_group") is not True:
            violations.append("report one_result_per_group must be true")
        if actual_policy.get("max_problems_or_remediations") != 2:
            violations.append("report max_problems_or_remediations must be 2")
        if actual_policy.get("include_raw_credentials") is not False:
            violations.append("report include_raw_credentials must be false")
    return violations


def check_app_graph_contract(root: Path) -> list[str]:
    """APP 流 B9（W21）：app_graph_schema 契约结构校验 + 契约 ↔ app_graph 工厂
    ↔ init 种子三方同源。实现常量（orchestration.app_graph / init 脚本）来自真实
    仓库（SCRIPT_ROOT），契约数据来自 --root——篡改负例有效。"""
    violations: list[str] = []
    for cname in REQUIRED_APP_GRAPH_CONTRACTS:
        data, err = _load_json(root / "contracts" / cname)
        if err:
            violations.append(err)
            continue
        if not isinstance(data, dict):
            violations.append(f"{cname} must be an object")
            continue
        if data.get("$id") != "app_graph_schema":
            violations.append(f"{cname}.$id must be app_graph_schema")
        if data.get("properties", {}).get("workflow") != {"const": "app"}:
            violations.append(f"{cname}.properties.workflow must be const 'app'")
        node_defs = data.get("$defs", {}).get("node", {})
        if node_defs.get("properties", {}).get("cursor_file") != {"const": "phase_status.app.json"}:
            violations.append(
                f"{cname}.$defs.node.properties.cursor_file must be "
                "const phase_status.app.json"
            )
        for enum_field, defs_key in (("kind", "node"), ("kind", "edge")):
            enum_value = (
                data.get("$defs", {}).get(defs_key, {}).get("properties", {}).get(enum_field, {}).get("enum")
            )
            if not isinstance(enum_value, list) or not enum_value:
                violations.append(f"{cname}.$defs.{defs_key}.properties.{enum_field}.enum missing")
        safety = data.get("x-app-safety", {})
        if not isinstance(safety, dict):
            violations.append(f"{cname}.x-app-safety missing")
        else:
            if safety.get("status_file") != "phase_status.app.json":
                violations.append(f"{cname}.x-app-safety.status_file must be phase_status.app.json")
            forbidden = safety.get("forbidden_cursors")
            for cursor in ("phase_status.json", "phase_status.miniapp.json", "run_status.json"):
                if not isinstance(forbidden, list) or cursor not in forbidden:
                    violations.append(
                        f"{cname}.x-app-safety.forbidden_cursors missing {cursor}"
                    )
            if safety.get("approval_gates") != ["device_instrumentation", "app_hardened_unpack"]:
                violations.append(
                    f"{cname}.x-app-safety.approval_gates must be "
                    "[device_instrumentation, app_hardened_unpack]"
                )
            if safety.get("approval_gates_auto_advance") is not False:
                violations.append(
                    f"{cname}.x-app-safety.approval_gates_auto_advance must be false"
                )

    # --- 契约 ↔ 工厂 ↔ init 种子三方同源（实现来自 SCRIPT_ROOT，契约来自 --root）---
    try:
        from jsonschema import Draft202012Validator

        import authorized_assessment.orchestration.app_graph as app_graph_mod
    except Exception as exc:  # noqa: BLE001 - 校验器必须报告而非崩溃
        return violations + [f"app graph module import failed: {exc}"]
    init_mod, err = _app_skill_module("init_app_engagement.py")
    if err:
        return violations + [err]
    schema_data, err = _load_json(root / "contracts" / "app_graph_schema.json")
    if err or not isinstance(schema_data, dict):
        return violations + ([err] if err else ["app_graph_schema.json must be an object"])
    graph = app_graph_mod.build_app_graph(created_at="fixed")
    schema_errors = [
        f"app_graph_schema rejects factory output: {error.message}"
        for error in Draft202012Validator(schema_data).iter_errors(graph.to_dict())
    ]
    violations += schema_errors
    impl_errors = app_graph_mod.validate_app_graph(graph)
    if impl_errors:
        violations += [f"app_graph factory self-validation failed: {item}" for item in impl_errors]
    if tuple(app_graph_mod.APP_PHASES) != tuple(init_mod.PHASES):  # type: ignore[attr-defined]
        violations.append("app_graph.APP_PHASES drift against init PHASES seed")
    if dict(app_graph_mod.APP_BRANCHES) != dict(init_mod.PHASE_BRANCHES):  # type: ignore[attr-defined]
        violations.append("app_graph.APP_BRANCHES drift against init PHASE_BRANCHES seed")
    if tuple(app_graph_mod.APP_APPROVAL_GATES) != ("device_instrumentation", "app_hardened_unpack"):
        violations.append("app_graph.APP_APPROVAL_GATES must match the dual-key approval gates")
    return violations


def collect_violations(root: Path = SCRIPT_ROOT, *, include_reporting: bool = False) -> list[str]:
    contracts = root / "contracts"
    violations: list[str] = []
    violations += check_workflow_schema(contracts)
    violations += check_run_quality_schema(contracts)
    violations += check_rule_precedence(contracts)
    violations += check_context_snapshot_schema(contracts)
    violations += check_candidate_identity_schema(contracts)
    violations += check_tool_capability_schema(root)
    violations += check_injection_candidate_schema(root)
    violations += check_graphql_schema(root)
    violations += check_api_reconciliation_schema(root)
    violations += check_miniapp_auth_schema(root)
    violations += check_miniapp_storage_package_schema(root)
    violations += check_miniapp_reconciliation_schema(root)
    violations += check_miniapp_cloud_schema(root)
    violations += check_miniapp_webview_schema(root)
    violations += check_app_contracts(root)
    violations += check_app_engine_sync(root)
    violations += check_app_graph_contract(root)
    violations += check_orchestration_contracts(root)
    if include_reporting:
        violations += check_report_policy_schema(root)
    violations += check_state_model_drift(root)
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 run 契约与状态模型一致性（离线）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON 报告")
    parser.add_argument("--root", type=Path, default=SCRIPT_ROOT, help="项目根（默认仓库根）")
    parser.add_argument("--include-reporting", action="store_true", help="同时校验报告策略与独立报告配置")
    args = parser.parse_args(argv)

    violations = collect_violations(args.root.resolve(), include_reporting=args.include_reporting)
    if args.json:
        print(
            json.dumps(
                {"root": str(args.root), "violations": violations, "ok": not violations},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if violations:
            print(f"[!] {len(violations)} 项契约违例：")
            for item in violations:
                print(f"  - {item}")
        else:
            print("[+] run 契约校验通过：契约文件结构完整，状态模型与门控阈值无漂移")
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
