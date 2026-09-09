"""tests/test_app_contract_sync.py —— APP 流 B5 契约↔引擎↔种子三处同源锁定
（施工方案 §5.3/§5.7，批次 B5/W19 中段）。

锁定链（三方）：
  A. contracts/app_*.json（B4 契约，唯一事实源=附录 B 种子的契约化表达）
  B. src/authorized_assessment/app/*（B5 引擎常量）
  C. .agents/skills/app/scripts/{init,audit}_app_engagement.py（skill 种子，自包含
     复制，不 import 引擎——与 xcx 先例一致）

覆盖：hardening 七分支/产物路径/升级规则边界（obfuscation 永不升级）、webview 七
分支×三 CSV（表头/枚举/判定子集/分支→产物 1:1）、ipc 七分支×两 CSV（同上）、
12-key review JSON 骨架、authorization_basis、coverage 六值单一来源、
decoding-ledger 字段、引擎红线常量（只观察不绕过/APP_NO_REPACKING_RULE/
duplicate_execution=false）。

纯离线：只读仓库文件，不发任何网络请求。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorized_assessment.app import app_review_common as arc  # noqa: E402
from authorized_assessment.app import hardening_integrity_review as hir  # noqa: E402
from authorized_assessment.app import ipc_component_review as ipr  # noqa: E402
from authorized_assessment.app import static_extraction as sex  # noqa: E402
from authorized_assessment.app import webview_bridge_review as wbr  # noqa: E402
from authorized_assessment.triage import injection_candidates as ic  # noqa: E402

INIT_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "init_app_engagement.py"
AUDIT_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "audit_app_engagement.py"

STORAGE_CONTRACT = json.loads(
    (ROOT / "contracts" / "app_storage_package_schema.json").read_text(encoding="utf-8-sig")
)
WEBVIEW_CONTRACT = json.loads(
    (ROOT / "contracts" / "app_webview_schema.json").read_text(encoding="utf-8-sig")
)
IPC_CONTRACT = json.loads(
    (ROOT / "contracts" / "app_ipc_schema.json").read_text(encoding="utf-8-sig")
)
COVERAGE_CONTRACT = json.loads(
    (ROOT / "contracts" / "coverage_substatus_schema.json").read_text(encoding="utf-8-sig")
)


def _load_skill_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# hardening：契约 ↔ 引擎 ↔ init 种子
# ---------------------------------------------------------------------------

def test_hardening_branches_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_sync", INIT_SCRIPT)
    contract_spec = STORAGE_CONTRACT["phases"][hir.HARDENING_PHASE]
    assert tuple(contract_spec["branches"]) == hir.HARDENING_REVIEW_BRANCHES
    assert tuple(contract_spec["branches"]) == tuple(
        init_mod.HARDENING_REVIEW_BRANCHES[hir.HARDENING_PHASE]
    )
    assert len(hir.HARDENING_REVIEW_BRANCHES) == 7
    assert hir.HARDENING_REVIEW_BRANCHES == (
        "package_version_inventory",
        "signing_integrity",
        "hardening_obfuscation_markers",
        "debug_switches",
        "debug_info_exposure",
        "update_endpoint_environment",
        "trusted_update_config",
    )


def test_hardening_artifact_path_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_sync", INIT_SCRIPT)
    contract_spec = STORAGE_CONTRACT["phases"][hir.HARDENING_PHASE]
    assert contract_spec["artifact"] == hir.HARDENING_REVIEW_ARTIFACT
    assert contract_spec["artifact"] == init_mod.PHASE_ARTIFACTS[hir.HARDENING_PHASE][0]
    assert hir.HARDENING_REVIEW_ARTIFACT == "artifacts/app/package/hardening-review.json"


def test_hardening_contract_identity_matches_engine():
    assert hir.APP_STORAGE_PACKAGE_CONTRACT == STORAGE_CONTRACT["contract"] == "app_storage_package_schema"
    assert hir.APP_STORAGE_PACKAGE_SCHEMA_VERSION == STORAGE_CONTRACT["schema_version"] == "1.0"


def test_hardening_upgrade_rules_never_cross_branch_and_obfuscation_never_upgrades():
    # 确认形态与可升级分支一一对应、不跨分支；hardening_obfuscation_markers 无规则
    # （契约"加固 so 特征只记 signal"）。
    confirmed_kinds = set(hir.HARDENING_EVIDENCE_KINDS) - set(hir.HARDENING_INSUFFICIENT_KINDS)
    assert "hardening_obfuscation_markers" not in hir.HARDENING_UPGRADE_RULES
    assert confirmed_kinds == {
        kind
        for rule in hir.HARDENING_UPGRADE_RULES.values()
        for group in rule["required_any_groups"]
        for kind in group
    }
    for branch, rule in hir.HARDENING_UPGRADE_RULES.items():
        assert branch in hir.HARDENING_REVIEW_BRANCHES
        for group in rule["required_any_groups"]:
            for kind in group:
                assert kind in confirmed_kinds, f"{kind} 不在确认形态集合"
    # 证据形态映射为恒等映射且覆盖全部形态。
    assert set(hir.HARDENING_OBSERVATION_EVIDENCE_MAP) == set(hir.HARDENING_EVIDENCE_KINDS)
    assert set(hir.HARDENING_OBSERVATION_FIELD_DOCS) == set(hir.HARDENING_EVIDENCE_KINDS)
    # 契约红线在场（引擎常量与 red_lines 同源）。
    joined = " ".join(STORAGE_CONTRACT["red_lines"])
    assert "APP_NO_REPACKING_RULE" in joined
    assert "signal" in joined
    assert hir.APP_NO_REPACKING_RULE.startswith("不做重打包、篡改、脱壳、绕过 pinning 或设备攻击")
    assert "只观察不绕过" in hir.OBSERVE_ONLY_RULE
    assert any("只观察不绕过" in invariant for invariant in hir.HARDENING_INVARIANTS)


def test_hardening_engine_semantics_observe_only():
    # 形态/支持性观察永不升级（signal 不是漏洞）；确认形态才可升级 candidate。
    rows, summaries, violations = hir.screen_hardening_observations(
        [
            {
                "branch": "hardening_obfuscation_markers",
                "applicability": "applicable",
                "source": "lib/arm64-v8a/libjiagu.so",
                "evidence": {"packer_so_signature_observed": True},
                "evidence_ref": "artifacts/app/unpacked/demo/sources",
            },
            {
                "branch": "debug_switches",
                "applicability": "applicable",
                "source": "AndroidManifest.xml",
                "evidence": {"debuggable_marker_observed": True},
                "evidence_ref": "artifacts/app/apktool/demo/AndroidManifest.xml",
            },
            {
                "branch": "debug_switches",
                "applicability": "applicable",
                "source": "AndroidManifest.xml 复核",
                "evidence": {"debug_switch_active_confirmed": True},
                "evidence_ref": "artifacts/app/apktool/demo/AndroidManifest.xml",
                "precondition": "既有只读证据复核（apktool 解码产物），未做任何绕过或篡改",
                "reason": "发布包 debuggable=true 已确认",
            },
        ]
    )
    assert not violations
    by_branch = {row["branch"]: row for row in rows}
    assert by_branch["hardening_obfuscation_markers"]["status"] == "signal"
    debug_rows = [row for row in rows if row["branch"] == "debug_switches"]
    assert {row["status"] for row in debug_rows} == {"signal", "candidate"}
    substatuses = {summary["branch"]: summary["branch_status"] for summary in summaries}
    assert set(substatuses) == set(hir.HARDENING_REVIEW_BRANCHES)
    assert substatuses["debug_switches"] == "tested"
    artifact = hir.build_hardening_review_artifact(
        rows, summaries, violations,
        authorization_basis="operator_supplied_material",
        updated_at="2026-09-09T00:00:00+08:00",
    )
    assert not hir.validate_hardening_review_artifact(artifact)
    assert artifact["contract"] == "app_storage_package_schema"
    assert artifact["phase"] == hir.HARDENING_PHASE


# ---------------------------------------------------------------------------
# 共享骨架：契约 ↔ 引擎 ↔ init 种子
# ---------------------------------------------------------------------------

def test_review_json_skeleton_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_sync", INIT_SCRIPT)
    fields = STORAGE_CONTRACT["artifact_fields"]
    assert tuple(fields["row_fields"]) == arc.APP_REVIEW_ROW_FIELDS
    assert tuple(fields["summary_fields"]) == arc.APP_REVIEW_SUMMARY_FIELDS
    assert tuple(fields["artifact_keys"]) == arc.APP_REVIEW_ARTIFACT_KEYS
    assert tuple(init_mod.REVIEW_SKELETON_FIELDS["row_fields"]) == arc.APP_REVIEW_ROW_FIELDS
    assert tuple(init_mod.REVIEW_SKELETON_FIELDS["summary_fields"]) == arc.APP_REVIEW_SUMMARY_FIELDS
    assert len(arc.APP_REVIEW_ARTIFACT_KEYS) == 12


def test_coverage_and_finding_status_single_source():
    audit_mod = _load_skill_module("app_audit_seed_sync", AUDIT_SCRIPT)
    assert arc.COVERAGE_STATUS_VALUES == tuple(COVERAGE_CONTRACT["status_values"])
    assert len(arc.COVERAGE_STATUS_VALUES) == 6
    assert set(STORAGE_CONTRACT["coverage_substatus"]["status_values"]) == set(arc.COVERAGE_STATUS_VALUES)
    assert arc.FINDING_STATUS_VALUES == ic.CANDIDATE_STATUS_VALUES
    assert len(arc.FINDING_STATUS_VALUES) == 8
    assert audit_mod.COVERAGE_SUBSTATUSES == set(arc.COVERAGE_STATUS_VALUES)
    assert audit_mod.FINDING_STATUS_VALUES == set(arc.FINDING_STATUS_VALUES)


def test_authorization_basis_and_duplicate_execution_constants():
    audit_mod = _load_skill_module("app_audit_seed_sync", AUDIT_SCRIPT)
    assert arc.APP_AUTHORIZATION_BASIS_VALUES == ("operator_supplied_material", "local_traffic")
    assert set(STORAGE_CONTRACT["authorization_basis_values"]) == set(arc.APP_AUTHORIZATION_BASIS_VALUES)
    assert audit_mod.AUTHORIZATION_BASIS_VALUES == set(arc.APP_AUTHORIZATION_BASIS_VALUES)
    assert arc.DUPLICATE_EXECUTION is False
    assert arc.DUPLICATE_EXECUTION_NOTE == "duplicate_execution=false"


# ---------------------------------------------------------------------------
# webview：契约 ↔ 引擎 ↔ init/audit 种子（七分支 × 三 CSV）
# ---------------------------------------------------------------------------

def test_webview_branches_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_sync", INIT_SCRIPT)
    audit_mod = _load_skill_module("app_audit_seed_sync", AUDIT_SCRIPT)
    contract_spec = WEBVIEW_CONTRACT["phases"][wbr.WEBVIEW_PHASE]
    assert tuple(contract_spec["branches"]) == wbr.WEBVIEW_REVIEW_BRANCHES
    assert tuple(contract_spec["branches"]) == tuple(
        init_mod.PHASE_BRANCHES[wbr.WEBVIEW_PHASE]
    )
    assert tuple(contract_spec["branches"]) == tuple(
        audit_mod.WEBVIEW_REVIEW_BRANCHES[wbr.WEBVIEW_PHASE]
    )
    assert len(wbr.WEBVIEW_REVIEW_BRANCHES) == 7


def test_webview_artifacts_and_csv_fields_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_sync", INIT_SCRIPT)
    contract_spec = WEBVIEW_CONTRACT["phases"][wbr.WEBVIEW_PHASE]
    contract_entries = contract_spec["artifacts"]
    assert tuple(entry["artifact"] for entry in contract_entries) == wbr.WEBVIEW_ARTIFACTS
    assert tuple(init_mod.PHASE_ARTIFACTS[wbr.WEBVIEW_PHASE]) == wbr.WEBVIEW_ARTIFACTS
    for entry in contract_entries:
        rel = entry["artifact"]
        assert tuple(entry["csv_fields"]) == wbr.WEBVIEW_CSV_FIELDS[rel]
        assert tuple(init_mod.REVIEW_CSV_ARTIFACTS[rel]) == wbr.WEBVIEW_CSV_FIELDS[rel]
        assert sorted(entry["branches"]) == sorted(
            branch for branch, artifact in wbr.WEBVIEW_BRANCH_ARTIFACTS.items() if artifact == rel
        )
    # 分支→产物 1:1：并集恰为七分支、值集恰为三产物。
    assert set(wbr.WEBVIEW_BRANCH_ARTIFACTS) == set(wbr.WEBVIEW_REVIEW_BRANCHES)
    assert set(wbr.WEBVIEW_BRANCH_ARTIFACTS.values()) == set(wbr.WEBVIEW_ARTIFACTS)


def test_webview_row_enums_and_reason_subsets_match_contract_and_audit():
    audit_mod = _load_skill_module("app_audit_seed_sync", AUDIT_SCRIPT)
    contract_spec = WEBVIEW_CONTRACT["phases"][wbr.WEBVIEW_PHASE]
    for entry in contract_spec["artifacts"]:
        rel = entry["artifact"]
        row_enums = entry["row_enums"]
        assert set(row_enums) == set(wbr.WEBVIEW_ROW_ENUMS[rel])
        for column, values in wbr.WEBVIEW_ROW_ENUMS[rel].items():
            assert tuple(row_enums[column]) == values
    assert wbr.WEBVIEW_COOKIE_TOKEN_SHARED_VALUES == tuple(audit_mod.WEBVIEW_COOKIE_TOKEN_SHARED_VALUES)
    assert wbr.WEBVIEW_CAPABILITY_VALUES == tuple(audit_mod.WEBVIEW_CAPABILITY_VALUES)
    assert wbr.WEBVIEW_SCHEME_TYPES == tuple(audit_mod.WEBVIEW_SCHEME_TYPES)
    assert wbr.WEBVIEW_JUMP_TARGETS == tuple(audit_mod.WEBVIEW_JUMP_TARGETS)
    assert wbr.WEBVIEW_BRIDGE_REASON_CAPABILITIES == tuple(audit_mod.WEBVIEW_BRIDGE_REASON_CAPABILITIES)
    assert wbr.WEBVIEW_REASON_JUMP_TARGETS == tuple(audit_mod.WEBVIEW_REASON_JUMP_TARGETS)


def test_webview_row_validation_semantics():
    # 正例：共享边界行带 reason、capability 判定子集行带 reason、深链敏感参数行带 reason。
    assert wbr.validate_origin_row(
        {"webview_origin": "https://example.com", "cookie_token_shared": "auth_token",
         "reason": "授权流量观察到 token 注入", "boundary_status": "candidate"}
    ) == []
    assert wbr.validate_bridge_method_row(
        {"method_name": "getUserInfo", "exposed_scope": "public", "capability": "sensitive_token_access",
         "reason": "敏感 token 读取能力"}
    ) == []
    assert wbr.validate_deep_link_row(
        {"deep_link_pattern": "myapp://pay", "scheme_type": "custom_scheme",
         "jump_target": "in_app", "sensitive_params": "orderId,tenantId", "reason": "携带对象/租户 ID"}
    ) == []
    # 负例：缺必填、非法枚举、判定子集缺 reason、非法 boundary_status。
    assert wbr.validate_origin_row({"webview_origin": "", "cookie_token_shared": ""}) != []
    assert wbr.validate_origin_row(
        {"webview_origin": "https://example.com", "cookie_token_shared": "yes"}
    ) != []
    assert wbr.validate_origin_row(
        {"webview_origin": "https://example.com", "cookie_token_shared": "both"}
    ) != []  # 共享已观察到但缺 reason
    assert wbr.validate_bridge_method_row(
        {"method_name": "save", "exposed_scope": "public", "capability": "write_data"}
    ) != []
    assert wbr.validate_deep_link_row(
        {"deep_link_pattern": "myapp://x", "scheme_type": "custom_scheme",
         "jump_target": "external_app"}
    ) != []
    assert wbr.validate_origin_row(
        {"webview_origin": "https://example.com", "cookie_token_shared": "none",
         "boundary_status": "definitely_vulnerable"}
    ) != []


def test_webview_branch_tested_projection_and_invariants():
    rows_by_artifact = {
        wbr.WEBVIEW_ORIGIN_INVENTORY_CSV: [{"row_id": "WV-0001"}],
        wbr.WEBVIEW_BRIDGE_METHOD_CSV: [],
        wbr.WEBVIEW_DEEP_LINK_QUEUE_CSV: [{"row_id": "DL-0001"}],
    }
    projection = wbr.webview_branch_tested_projection(rows_by_artifact)
    assert projection["webview_allowed_domains"] is True
    assert projection["bridge_method_exposure"] is False
    assert projection["external_app_browser_jump"] is True
    assert wbr.WEBVIEW_REVIEW_CONTRACT == "app_webview_schema"
    assert any(wbr.DUPLICATE_EXECUTION_NOTE in invariant for invariant in wbr.WEBVIEW_INVARIANTS)


def test_webview_inventory_roundtrip(tmp_path):
    rows = wbr.assign_row_ids(
        [
            {"webview_origin": "https://example.com", "cookie_token_shared": "none",
             "source_material": "materials/working/demo"},
        ],
        "WV",
    )
    wbr.write_inventory_csv(
        tmp_path / wbr.WEBVIEW_ORIGIN_INVENTORY_CSV, wbr.WEBVIEW_ORIGIN_CSV_FIELDS, rows
    )
    rows_by_artifact, issues = wbr.validate_webview_inventory(tmp_path)
    # 其余两产物缺失 → 记 missing；origin 产物本身无行级违例。
    assert issues == [
        f"{Path(wbr.WEBVIEW_BRIDGE_METHOD_CSV).name}: file missing",
        f"{Path(wbr.WEBVIEW_DEEP_LINK_QUEUE_CSV).name}: file missing",
    ]
    assert len(rows_by_artifact[wbr.WEBVIEW_ORIGIN_INVENTORY_CSV]) == 1
    assert rows[0]["row_id"] == "WV-0001"


# ---------------------------------------------------------------------------
# ipc：契约 ↔ 引擎 ↔ init/audit 种子（七分支 × 两 CSV，App 特有）
# ---------------------------------------------------------------------------

def test_ipc_branches_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_sync", INIT_SCRIPT)
    audit_mod = _load_skill_module("app_audit_seed_sync", AUDIT_SCRIPT)
    contract_spec = IPC_CONTRACT["phases"][ipr.IPC_PHASE]
    assert tuple(contract_spec["branches"]) == ipr.IPC_REVIEW_BRANCHES
    assert tuple(contract_spec["branches"]) == tuple(init_mod.PHASE_BRANCHES[ipr.IPC_PHASE])
    assert tuple(contract_spec["branches"]) == tuple(audit_mod.IPC_REVIEW_BRANCHES[ipr.IPC_PHASE])
    assert len(ipr.IPC_REVIEW_BRANCHES) == 7


def test_ipc_artifacts_and_csv_fields_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_sync", INIT_SCRIPT)
    contract_spec = IPC_CONTRACT["phases"][ipr.IPC_PHASE]
    contract_entries = contract_spec["artifacts"]
    assert tuple(entry["artifact"] for entry in contract_entries) == ipr.IPC_ARTIFACTS
    assert tuple(init_mod.PHASE_ARTIFACTS[ipr.IPC_PHASE]) == ipr.IPC_ARTIFACTS
    for entry in contract_entries:
        rel = entry["artifact"]
        assert tuple(entry["csv_fields"]) == ipr.IPC_CSV_FIELDS[rel]
        assert tuple(init_mod.REVIEW_CSV_ARTIFACTS[rel]) == ipr.IPC_CSV_FIELDS[rel]
        assert sorted(entry["branches"]) == sorted(
            branch for branch, artifact in ipr.IPC_BRANCH_ARTIFACTS.items() if artifact == rel
        )
    assert set(ipr.IPC_BRANCH_ARTIFACTS) == set(ipr.IPC_REVIEW_BRANCHES)
    assert set(ipr.IPC_BRANCH_ARTIFACTS.values()) == set(ipr.IPC_ARTIFACTS)


def test_ipc_row_enums_match_contract_and_audit_and_deeplink_shares_webview_enums():
    audit_mod = _load_skill_module("app_audit_seed_sync", AUDIT_SCRIPT)
    contract_spec = IPC_CONTRACT["phases"][ipr.IPC_PHASE]
    for entry in contract_spec["artifacts"]:
        rel = entry["artifact"]
        row_enums = entry["row_enums"]
        assert set(row_enums) == set(ipr.IPC_ROW_ENUMS[rel])
        for column, values in ipr.IPC_ROW_ENUMS[rel].items():
            assert tuple(row_enums[column]) == values
    assert ipr.IPC_COMPONENT_KINDS == tuple(audit_mod.IPC_COMPONENT_KINDS)
    assert ipr.IPC_EXPORTED_VALUES == tuple(audit_mod.IPC_EXPORTED_VALUES)
    assert ipr.IPC_SCHEME_TYPES is wbr.WEBVIEW_SCHEME_TYPES  # 与 webview 深链同源（同一常量）
    assert ipr.IPC_JUMP_TARGETS is wbr.WEBVIEW_JUMP_TARGETS


def test_ipc_row_validation_semantics():
    assert ipr.validate_component_row(
        {"component_kind": "activity", "component_name": "com.demo.Main",
         "exported": "true", "reason": "launcher 入口，外部可达已评估"}
    ) == []
    assert ipr.validate_component_row(
        {"component_kind": "provider", "component_name": "com.demo.Data",
         "exported": "false"}
    ) == []
    assert ipr.validate_component_row(
        {"component_kind": "receiver", "component_name": "com.demo.Push",
         "exported": "true"}
    ) != []  # exported=true 缺 reason
    assert ipr.validate_component_row(
        {"component_kind": "widget", "component_name": "x", "exported": "true",
         "reason": "r"}
    ) != []  # 非法 component_kind
    assert ipr.validate_ipc_deeplink_row(
        {"deep_link_pattern": "myapp://item", "scheme_type": "custom_scheme",
         "jump_target": "in_app"}
    ) == []
    assert ipr.validate_ipc_deeplink_row(
        {"deep_link_pattern": "https://demo.com/link", "scheme_type": "https_link",
         "jump_target": "browser", "sensitive_params": "sessionId", "reason": "universal link 携带会话参数"}
    ) == []
    assert ipr.validate_ipc_deeplink_row(
        {"deep_link_pattern": "myapp://item", "scheme_type": "custom_scheme",
         "jump_target": "unknown"}
    ) != []  # 未确认跳转缺 reason
    assert ipr.IPC_REVIEW_CONTRACT == "app_ipc_schema"
    assert any(ipr.DUPLICATE_EXECUTION_NOTE in invariant for invariant in ipr.IPC_INVARIANTS)


def test_ipc_inventory_roundtrip(tmp_path):
    rows = ipr.assign_row_ids(
        [
            {"component_kind": "activity", "component_name": "com.demo.Main",
             "exported": "true", "reason": "launcher 入口", "source_material": "AndroidManifest.xml"},
        ],
        "IPC",
    )
    ipr.write_inventory_csv(
        tmp_path / ipr.IPC_COMPONENT_INVENTORY_CSV, ipr.IPC_COMPONENT_CSV_FIELDS, rows
    )
    rows_by_artifact, issues = ipr.validate_ipc_inventory(tmp_path)
    # component 产物无行级违例；deeplink 产物缺失记 missing。
    assert issues == [f"{Path(ipr.IPC_DEEPLINK_QUEUE_CSV).name}: file missing"]
    assert len(rows_by_artifact[ipr.IPC_COMPONENT_INVENTORY_CSV]) == 1
    assert rows[0]["row_id"] == "IPC-0001"


# ---------------------------------------------------------------------------
# static_extraction：decoding-ledger 字段与 init 种子同源
# ---------------------------------------------------------------------------

def test_decoding_ledger_fields_match_init_seed():
    init_mod = _load_skill_module("app_init_seed_sync", INIT_SCRIPT)
    assert sex.DECODING_LEDGER_FIELDS == tuple(init_mod.DECODING_FIELDS)
    assert sex.DECODING_LEDGER_CSV == init_mod.PHASE_ARTIFACTS["initial_decoding"][0]
    assert sex.DEFAULT_TIMEOUT_SECONDS == 600
    assert sex.MAX_CAPTURE_LINES > 0 and sex.MAX_CAPTURE_CHARS > 0
    assert sex.ALLOWED_MANAGED_TOOL_PREFIX == "tools/managed/app"


def test_module_readme_documents_reuse_boundary():
    readme = (ROOT / "src" / "authorized_assessment" / "app" / "README.md").read_text(encoding="utf-8")
    for anchor in (
        "复用边界",
        "app_review_common.py",
        "hardening_integrity_review.py",
        "static_extraction.py",
        "webview_bridge_review.py",
        "ipc_component_review.py",
        "只观察不绕过",
        "duplicate_execution=false",
    ):
        assert anchor in readme, f"README 缺少锚点 {anchor!r}"
