"""tests/test_app_audit_engagement.py —— APP 流只读审计器测试（batch B3/W18，方案 §7.3）。

覆盖：
  - 正例：最小可闭合工作区（流量导出材料 + 全 phase complete/not_applicable +
    12 组复核分支 proven + 清单 CSV 合法行）→ state=CLOSED、issues 空、CLI 退出码 0；
  - 负例（至少覆盖：分支未记录/缺 artifact/confirmed 缺证据/候选无 disposition）：
    review 分支未记录、review 产物缺失、台账 confirmed 缺证据（EVIDENCE_PENDING）、
    active 候选无 disposition（REVIEW_PENDING）、非法 substatus/未知分支、
    对账判定行缺 reason、ipc 行校验、not_applicable phase 缺 reason、
    缺 app 游标 fail-closed（绝不回落 wz/xcx 游标）；
  - 闭合不变量：state=CLOSED 要求 issues 为空（退出码非 0＝不可闭合；
    ISSUES_OUTSTANDING 收口 xcx 参照实现中违例不挡闭合的缺口）；
  - 报告闭合：confirmed 台账项要求 evidence 可解析 + 报告三件（非空 DOCX/
    final-report.md/evidence index）+ reporting phase 完成；
  - 只读性：audit() 前后工作区全部文件 hash 不变；零网络（源码无网络库调用）；
  - 常量同步：分支/产物路径/CSV 字段 ↔ init（B2 已落地）无漂移；coverage 六值
    枚举 ↔ contracts/coverage_substatus_schema.json；
  - 镜像字节一致性（canonical ↔ .claude/.opencode）。

skill 脚本自包含（不 import src 包），通过 importlib 按路径加载 canonical 脚本；
纯离线，不发任何网络请求。
"""
from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

INIT_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "init_app_engagement.py"
AUDIT_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "audit_app_engagement.py"
COVERAGE_CONTRACT_PATH = ROOT / "contracts" / "coverage_substatus_schema.json"

APP_CURSOR = "phase_status.app.json"
WZ_CURSOR = "phase_status.json"
XCX_CURSOR = "phase_status.miniapp.json"
EVIDENCE_NOTES = "notes/audit-evidence.md"

NETWORK_IMPORT_TOKENS = (
    "import requests",
    "import socket",
    "import http.client",
    "from requests",
    "from socket",
    "from http.client",
    "urllib.request",
    "import urllib3",
    "import httpx",
    "import aiohttp",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def init_mod():
    return _load_module("app_init_for_audit_test", INIT_SCRIPT)


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module("app_audit_engagement_test", AUDIT_SCRIPT)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def rewrite_csv(path: Path, rows: list[dict]) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        fields = list(csv.DictReader(handle).fieldnames or [])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def append_csv_row(path: Path, row: dict) -> None:
    rewrite_csv(path, [*read_csv_rows(path), row])


def run_init(init_mod, tmp_path: Path) -> Path:
    """流量导出输入（analyzable 且非 package 材料：包三阶段可合法 not_applicable）。"""
    har = tmp_path / "capture.har"
    har.write_text('{"log": {"entries": [{"request": {}}]}}', encoding="utf-8")
    out = tmp_path / "engagement"
    old_argv = sys.argv
    sys.argv = [
        str(INIT_SCRIPT), str(har), "--output", str(out),
        "--platform", "android", "--name", "Smoke",
        "--package", "com.example.smoke", "--operator", "TestOp",
    ]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 0, f"init failed with exit code {code}"
    return out


def phase_payload(root: Path) -> dict:
    return load_json(root / APP_CURSOR)


def update_phase(root: Path, phase: str, **fields) -> None:
    payload = phase_payload(root)
    row = next(r for r in payload["phases"] if r["phase"] == phase)
    row.update(fields)
    write_json(root / APP_CURSOR, payload)


def set_substatus(root: Path, phase: str, branch: str, value: str) -> None:
    payload = phase_payload(root)
    row = next(r for r in payload["phases"] if r["phase"] == phase)
    row["substatuses"][branch] = value
    write_json(root / APP_CURSOR, payload)


def make_closable(init_mod, tmp_path: Path) -> Path:
    """init 产物 → 最小可闭合工作区：授权确认、材料 analyzed、全 phase 闭合、
    12 组复核分支全 tested（JSON 产物 summaries 证据可解析 + 清单 CSV 合法行）。"""
    root = run_init(init_mod, tmp_path)
    engagement = load_json(root / "engagement.json")
    engagement["authorization"]["status"] = "confirmed"
    engagement["authorization"]["authorization_evidence_recorded"] = True
    engagement["authorization"]["active_testing_authorized"] = True
    write_json(root / "engagement.json", engagement)
    app_json = load_json(root / "app.json")
    app_json["identity_status"] = "confirmed"
    write_json(root / "app.json", app_json)
    (root / EVIDENCE_NOTES).write_text("# audit evidence\n", encoding="utf-8")
    rewrite_csv(
        root / "materials.csv",
        [dict(row, analysis_status="analyzed") for row in read_csv_rows(root / "materials.csv")],
    )

    payload = phase_payload(root)
    for row in payload["phases"]:
        name = row["phase"]
        if name == "authorization":
            continue
        if name in ("package_inventory", "package_unpack_decompile", "source_reconstruction"):
            row.update(status="not_applicable", reason="no package material (traffic-export-only engagement)")
        elif name == "reporting":
            row.update(status="not_applicable", reason="no reportable findings")
        else:
            row.update(status="complete", reason="")
        if name in init_mod.PHASE_BRANCHES:
            row["substatuses"] = {branch: "tested" for branch in init_mod.PHASE_BRANCHES[name]}
    write_json(root / APP_CURSOR, payload)

    for phase, (rel_artifact, _contract) in init_mod.REVIEW_JSON_ARTIFACTS.items():
        artifact = load_json(root / rel_artifact)
        artifact["authorization_basis"] = "operator_supplied_material"
        artifact["summaries"] = [
            {
                "branch": branch,
                "branch_status": "tested",
                "reason": "observed",
                "evidence_ref": EVIDENCE_NOTES,
                "precondition": "operator-supplied material only",
            }
            for branch in init_mod.PHASE_BRANCHES[phase]
        ]
        write_json(root / rel_artifact, artifact)

    rewrite_csv(root / "artifacts" / "app" / "reconciliation" / "static-dynamic-endpoints.csv", [{
        "endpoint_id": "e1", "host": "api.example.com", "method": "GET", "path": "/v1/ping",
        "source_material": "m1", "static_evidence_ref": EVIDENCE_NOTES,
        "dynamic_evidence_ref": EVIDENCE_NOTES, "status": "both_seen", "reason": "", "notes": "",
    }])
    rewrite_csv(root / "artifacts" / "app" / "webview" / "webview-origin-inventory.csv", [{
        "row_id": "w1", "webview_origin": "https://app.example.com", "business_purpose": "main",
        "source_material": "m1", "source_location": "manifest", "postmessage_target_origin": "",
        "cookie_token_shared": "none", "boundary_status": "", "evidence_ref": EVIDENCE_NOTES,
        "reason": "", "notes": "",
    }])
    rewrite_csv(root / "artifacts" / "app" / "webview" / "bridge-method-inventory.csv", [{
        "row_id": "b1", "method_name": "getUserInfo", "exposed_scope": "public",
        "capability": "navigation", "source_material": "m1", "boundary_status": "",
        "evidence_ref": EVIDENCE_NOTES, "reason": "", "notes": "",
    }])
    rewrite_csv(root / "artifacts" / "app" / "webview" / "deep-link-review-queue.csv", [{
        "row_id": "d1", "deep_link_pattern": "myscheme://home", "scheme_type": "custom_scheme",
        "sensitive_params": "", "jump_target": "in_app", "boundary_status": "",
        "evidence_ref": EVIDENCE_NOTES, "reason": "", "notes": "",
    }])
    rewrite_csv(root / "artifacts" / "app" / "ipc" / "component-inventory.csv", [{
        "row_id": "c1", "component_kind": "activity", "component_name": ".MainActivity",
        "exported": "false", "permission": "", "intent_actions": "", "scheme": "",
        "authority": "", "source_material": "m1", "source_location": "manifest",
        "boundary_status": "", "evidence_ref": EVIDENCE_NOTES, "reason": "", "notes": "",
    }])
    rewrite_csv(root / "artifacts" / "app" / "ipc" / "deeplink-review-queue.csv", [{
        "row_id": "i1", "deep_link_pattern": "myscheme://home", "scheme_type": "custom_scheme",
        "sensitive_params": "", "component_ref": "c1", "jump_target": "in_app",
        "boundary_status": "", "evidence_ref": EVIDENCE_NOTES, "reason": "", "notes": "",
    }])
    rewrite_csv(root / "artifacts" / "app" / "cloud" / "third-party-boundary.csv", [{
        "row_id": "t1", "service_name": "example-sdk", "service_type": "sdk",
        "host": "sdk.example.com", "attribution": "out_of_scope", "boundary_status": "",
        "evidence_ref": EVIDENCE_NOTES, "reason": "", "notes": "",
    }])
    return root


def run_audit_cli(audit_mod, root: Path, *extra: str) -> tuple[int, str]:
    buffer = io.StringIO()
    old_argv = sys.argv
    sys.argv = [str(AUDIT_SCRIPT), str(root), *extra]
    try:
        with contextlib.redirect_stdout(buffer):
            code = audit_mod.main()
    finally:
        sys.argv = old_argv
    return code, buffer.getvalue()


# ---------------------------------------------------------------------------
# 正例：最小可闭合工作区
# ---------------------------------------------------------------------------

def test_minimal_closable_workspace_closes(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    result = audit_mod.audit(root)
    assert result["state"] == "CLOSED"
    assert result["issues"] == []
    assert result["phase_status_file"] == APP_CURSOR
    assert result["stream"] == "app"
    assert result["reporting_not_applicable"] is True


def test_closable_workspace_cli_exit_zero_with_json(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    code, output = run_audit_cli(audit_mod, root, "--json")
    assert code == 0
    payload = json.loads(output)
    assert payload["state"] == "CLOSED"
    assert payload["issues"] == []


# ---------------------------------------------------------------------------
# 负例 1：分支未记录（phase complete 但分支 substatus 空串）
# ---------------------------------------------------------------------------

def test_unrecorded_branch_blocks_closure(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    set_substatus(root, "platform_login_exchange", "oauth_code_one_time", "")
    result = audit_mod.audit(root)
    assert any(
        "no recorded substatus" in issue and "oauth_code_one_time" in issue
        for issue in result["issues"]
    )
    # 闭合不变量：存在审计违例就不得 CLOSED（退出码非 0＝不可闭合）。
    assert result["state"] == "ISSUES_OUTSTANDING"
    code, _ = run_audit_cli(audit_mod, root, "--json")
    assert code == 1


def test_unproven_branch_value_blocks_closure(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    set_substatus(root, "signature_replay", "replay_window", "blocked")
    result = audit_mod.audit(root)
    assert any(
        "only complete with proven tested/not_applicable" in issue and "replay_window" in issue
        for issue in result["issues"]
    )
    assert result["state"] != "CLOSED"


# ---------------------------------------------------------------------------
# 负例 2：缺 artifact（phase complete + tested 但产物被删）
# ---------------------------------------------------------------------------

def test_missing_review_artifact_blocks_closure(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    (root / "artifacts" / "app" / "package" / "hardening-review.json").unlink()
    result = audit_mod.audit(root)
    assert any("missing or invalid" in issue for issue in result["issues"])
    assert result["state"] != "CLOSED"


def test_tested_csv_branch_without_rows_blocks_closure(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    rewrite_csv(root / "artifacts" / "app" / "ipc" / "component-inventory.csv", [])
    result = audit_mod.audit(root)
    assert any(
        "requires at least one recorded row" in issue and "exported_activity" in issue
        for issue in result["issues"]
    )
    assert result["state"] != "CLOSED"


# ---------------------------------------------------------------------------
# 负例 3：confirmed 缺证据 + 报告闭合
# ---------------------------------------------------------------------------

def test_confirmed_ledger_item_without_evidence_blocks_closure(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    append_csv_row(root / "review_ledger.csv", {
        "item_id": "L1", "active": "true", "status": "confirmed",
        "evidence_ref": "notes/missing-proof.md", "summary": "confirmed finding",
    })
    result = audit_mod.audit(root)
    assert result["missing_evidence_items"] == ["L1"]
    assert result["state"] == "EVIDENCE_PENDING"


def test_confirmed_finding_requires_report_then_closes(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    append_csv_row(root / "review_ledger.csv", {
        "item_id": "L1", "active": "true", "status": "confirmed",
        "evidence_ref": EVIDENCE_NOTES, "summary": "confirmed finding",
    })
    result = audit_mod.audit(root)
    assert result["reportable_results"] == ["L1"]
    assert result["state"] == "REPORT_PENDING"
    update_phase(root, "reporting", status="complete", reason="")
    (root / "reports" / "攻防成果报告_demo.docx").write_bytes(b"PK\x03\x04 fake docx")
    result = audit_mod.audit(root)
    assert result["state"] == "CLOSED"
    assert result["issues"] == []


# ---------------------------------------------------------------------------
# 负例 4：active 候选无 disposition
# ---------------------------------------------------------------------------

def test_active_candidate_without_disposition_blocks_closure(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    append_csv_row(root / "review_ledger.csv", {
        "item_id": "L1", "active": "true", "status": "candidate",
        "summary": "pending candidate",
    })
    result = audit_mod.audit(root)
    assert result["open_review_items"] == ["L1"]
    assert result["state"] == "REVIEW_PENDING"


# ---------------------------------------------------------------------------
# 其余负例：枚举/未知分支/判定行 reason/phase reason/游标 fail-closed
# ---------------------------------------------------------------------------

def test_invalid_substatus_and_unknown_branch_rejected(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    set_substatus(root, "session_token_lifecycle", "token_rotation", "complete")
    set_substatus(root, "session_token_lifecycle", "bogus_branch", "tested")
    result = audit_mod.audit(root)
    assert any("invalid substatus 'complete'" in issue for issue in result["issues"])
    assert any("unknown review branch 'bogus_branch'" in issue for issue in result["issues"])
    assert result["state"] != "CLOSED"


def test_reconciliation_judgment_row_requires_reason(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    rewrite_csv(root / "artifacts" / "app" / "reconciliation" / "static-dynamic-endpoints.csv", [{
        "endpoint_id": "e2", "host": "old.example.com", "method": "GET", "path": "/v1/legacy",
        "source_material": "m1", "static_evidence_ref": EVIDENCE_NOTES,
        "dynamic_evidence_ref": "", "status": "stale", "reason": "", "notes": "",
    }])
    result = audit_mod.audit(root)
    assert any(
        "status 'stale' requires a non-empty reason" in issue for issue in result["issues"]
    )
    assert result["state"] != "CLOSED"


def test_ipc_component_rows_enforced(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    rewrite_csv(root / "artifacts" / "app" / "ipc" / "component-inventory.csv", [{
        "row_id": "c2", "component_kind": "widget", "component_name": ".Exporter",
        "exported": "true", "permission": "", "intent_actions": "", "scheme": "",
        "authority": "", "source_material": "m1", "source_location": "manifest",
        "boundary_status": "", "evidence_ref": EVIDENCE_NOTES, "reason": "", "notes": "",
    }])
    result = audit_mod.audit(root)
    text = "\n".join(result["issues"])
    assert "invalid component_kind 'widget'" in text
    assert "exported component requires a non-empty reason" in text
    assert result["state"] != "CLOSED"


def test_webview_origin_row_enums_enforced(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    rewrite_csv(root / "artifacts" / "app" / "webview" / "webview-origin-inventory.csv", [{
        "row_id": "w2", "webview_origin": "https://pay.example.com", "business_purpose": "pay",
        "source_material": "m1", "source_location": "manifest", "postmessage_target_origin": "",
        "cookie_token_shared": "auth_token", "boundary_status": "", "evidence_ref": EVIDENCE_NOTES,
        "reason": "", "notes": "",
    }])
    result = audit_mod.audit(root)
    assert any(
        "cookie_token_shared 'auth_token' requires a non-empty reason" in issue
        for issue in result["issues"]
    )
    assert result["state"] != "CLOSED"


def test_not_applicable_phase_requires_reason(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    update_phase(root, "dynamic_setup", status="not_applicable", reason="")
    result = audit_mod.audit(root)
    assert any(
        "not_applicable requires a reason" in issue and "dynamic_setup" in issue
        for issue in result["issues"]
    )
    assert result["state"] != "CLOSED"


def test_missing_app_cursor_fails_closed(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    (root / APP_CURSOR).rename(tmp_path / APP_CURSOR)
    # 共址 wz/xcx 游标在场也绝不回落：fail-closed。
    (root / WZ_CURSOR).write_text(json.dumps({"stream": "wz", "phases": []}), encoding="utf-8")
    (root / XCX_CURSOR).write_text(json.dumps({"stream": "miniapp_xcx", "phases": []}), encoding="utf-8")
    result = audit_mod.audit(root)
    assert str(result["phase_status_route_error"] or "").startswith("APP_PHASE_STATUS_MISSING")
    assert result["phase_status_file"] is None
    assert result["state"] != "CLOSED"


def test_fresh_workspace_reports_pending_state(init_mod, audit_mod, tmp_path):
    root = run_init(init_mod, tmp_path)
    code, output = run_audit_cli(audit_mod, root, "--json")
    assert code == 1
    payload = json.loads(output)
    assert payload["state"] == "AUTHORIZATION_PENDING"
    assert payload["phase_status_file"] == APP_CURSOR
    assert payload["stream"] == "app"
    assert any("authorization" in issue for issue in payload["issues"])


def test_relaxed_device_gate_blocks_closure(init_mod, audit_mod, tmp_path):
    # APP 特有红线：safety_controls 不得把设备/脱壳审批门放松为可直接执行。
    root = make_closable(init_mod, tmp_path)
    engagement = load_json(root / "engagement.json")
    engagement["safety_controls"]["device_changes"] = "allowed"
    write_json(root / "engagement.json", engagement)
    result = audit_mod.audit(root)
    assert result["state"] == "SAFETY_CONTROLS_PENDING"
    assert any("safety controls" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# 只读性 + 零网络
# ---------------------------------------------------------------------------

def test_audit_is_read_only(init_mod, audit_mod, tmp_path):
    root = make_closable(init_mod, tmp_path)
    set_substatus(root, "crypto_and_secret_handling", "hardcoded_secrets", "")

    def snapshot() -> dict[str, str]:
        return {
            item.relative_to(root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
            for item in sorted(root.rglob("*"))
            if item.is_file()
        }

    before = snapshot()
    audit_mod.audit(root)
    assert snapshot() == before


def test_audit_source_has_no_network_calls():
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")
    for token in NETWORK_IMPORT_TOKENS:
        assert token not in source, f"network-capable import present: {token}"


# ---------------------------------------------------------------------------
# 常量同步：audit ↔ init（B2 落地）↔ coverage 契约
# ---------------------------------------------------------------------------

def test_branch_constants_match_init(init_mod, audit_mod):
    assert audit_mod.AUTH_REVIEW_BRANCHES == init_mod.AUTH_REVIEW_BRANCHES
    # init 把 hardening 七分支单独放在 HARDENING_REVIEW_BRANCHES；audit 按产物契约
    # （app_storage_package_schema）与 local/crypto 并归同一 dict。
    assert audit_mod.STORAGE_PACKAGE_REVIEW_BRANCHES == {
        **init_mod.HARDENING_REVIEW_BRANCHES,
        **init_mod.STORAGE_PACKAGE_REVIEW_BRANCHES,
    }
    assert audit_mod.RECONCILIATION_REVIEW_BRANCHES == init_mod.RECONCILIATION_REVIEW_BRANCHES
    assert audit_mod.WEBVIEW_REVIEW_BRANCHES == init_mod.WEBVIEW_REVIEW_BRANCHES
    assert audit_mod.IPC_REVIEW_BRANCHES == init_mod.IPC_REVIEW_BRANCHES
    assert audit_mod.CLOUD_REVIEW_BRANCHES == init_mod.CLOUD_REVIEW_BRANCHES
    # 12 组复核分支全覆盖（与 init PHASE_BRANCHES 同集）。
    audited = {
        *audit_mod.AUTH_REVIEW_BRANCHES,
        *audit_mod.STORAGE_PACKAGE_REVIEW_BRANCHES,
        *audit_mod.RECONCILIATION_REVIEW_BRANCHES,
        *audit_mod.WEBVIEW_REVIEW_BRANCHES,
        *audit_mod.IPC_REVIEW_BRANCHES,
        *audit_mod.CLOUD_REVIEW_BRANCHES,
    }
    assert audited == set(init_mod.PHASE_BRANCHES)


def test_artifact_paths_match_init(init_mod, audit_mod):
    expected_json = {phase: rel for phase, (rel, _c) in init_mod.REVIEW_JSON_ARTIFACTS.items()}
    assert audit_mod.AUTH_REVIEW_ARTIFACTS == {
        phase: expected_json[phase] for phase in audit_mod.AUTH_REVIEW_BRANCHES
    }
    assert audit_mod.STORAGE_PACKAGE_REVIEW_ARTIFACTS == {
        phase: expected_json[phase] for phase in audit_mod.STORAGE_PACKAGE_REVIEW_BRANCHES
    }
    cloud_json = {
        phase: audit_mod.CLOUD_REVIEW_ARTIFACTS[phase]
        for phase in audit_mod.CLOUD_REVIEW_BRANCHES
        if not audit_mod.CLOUD_REVIEW_ARTIFACTS[phase].endswith(".csv")
    }
    assert cloud_json == {
        phase: rel for phase, rel in expected_json.items() if phase in cloud_json
    }
    csv_paths = (
        set(audit_mod.RECONCILIATION_REVIEW_ARTIFACTS.values())
        | set(audit_mod.WEBVIEW_BRANCH_ARTIFACTS.values())
        | set(audit_mod.IPC_BRANCH_ARTIFACTS.values())
        | {
            audit_mod.CLOUD_REVIEW_ARTIFACTS[phase]
            for phase in audit_mod.CLOUD_REVIEW_BRANCHES
            if audit_mod.CLOUD_REVIEW_ARTIFACTS[phase].endswith(".csv")
        }
    )
    assert csv_paths == set(init_mod.REVIEW_CSV_ARTIFACTS)


def test_review_contract_names_match_init(init_mod):
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")
    for _phase, (_rel, contract) in init_mod.REVIEW_JSON_ARTIFACTS.items():
        assert f'"{contract}"' in source, f"audit must bind contract {contract}"


def test_csv_field_constants_match_init(init_mod, audit_mod):
    assert audit_mod.RECONCILIATION_CSV_FIELDS == init_mod.RECONCILIATION_CSV_FIELDS
    assert audit_mod.RECONCILIATION_ENDPOINT_STATES == init_mod.RECONCILIATION_ENDPOINT_STATES
    assert audit_mod.WEBVIEW_ORIGIN_CSV_FIELDS == init_mod.WEBVIEW_ORIGIN_CSV_FIELDS
    assert audit_mod.WEBVIEW_BRIDGE_CSV_FIELDS == init_mod.WEBVIEW_BRIDGE_CSV_FIELDS
    assert audit_mod.WEBVIEW_DEEP_LINK_CSV_FIELDS == init_mod.WEBVIEW_DEEP_LINK_CSV_FIELDS
    assert audit_mod.IPC_COMPONENT_CSV_FIELDS == init_mod.IPC_COMPONENT_CSV_FIELDS
    assert audit_mod.IPC_COMPONENT_KINDS == init_mod.IPC_COMPONENT_KINDS
    assert audit_mod.IPC_DEEPLINK_CSV_FIELDS == init_mod.IPC_DEEPLINK_CSV_FIELDS
    assert audit_mod.THIRD_PARTY_CSV_FIELDS == init_mod.THIRD_PARTY_CSV_FIELDS


def test_core_phases_are_init_phases_minus_closure_triple(init_mod, audit_mod):
    assert audit_mod.CORE_PHASES == set(init_mod.PHASES) - {
        "candidate_validation", "reporting", "cleanup"
    }


def test_coverage_substatus_enum_matches_shared_contract(audit_mod):
    contract = json.loads(COVERAGE_CONTRACT_PATH.read_text(encoding="utf-8-sig"))
    assert set(audit_mod.COVERAGE_SUBSTATUSES) == set(contract["status_values"])
    assert audit_mod.PROVEN_SUBSTATUSES == {"tested", "not_applicable"}


# ---------------------------------------------------------------------------
# 镜像字节一致性（canonical ↔ .claude/.opencode）
# ---------------------------------------------------------------------------

def test_audit_script_mirrors_are_byte_identical():
    relative = Path("scripts") / "audit_app_engagement.py"
    canonical = ROOT / ".agents" / "skills" / "app" / relative
    for mirror_name in (".claude", ".opencode"):
        mirror = ROOT / mirror_name / "skills" / "app" / relative
        assert mirror.is_file(), f"missing mirror: {mirror_name}/skills/app/{relative.as_posix()}"
        assert mirror.read_bytes() == canonical.read_bytes(), (
            f"mirror drift: {mirror_name}/skills/app/{relative.as_posix()}"
        )
