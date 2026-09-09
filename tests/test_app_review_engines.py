"""tests/test_app_review_engines.py —— APP 流 B6 评审引擎下半（W19 收尾）锁定
（施工方案 §5.3/§5.7，批次 B6：auth 三模块 + local/crypto + reconciliation +
cloud 三模块）。

锁定链（三方）：contracts/app_*.json（B4 契约）↔ src/authorized_assessment/app/
B6 引擎常量 ↔ .agents/skills/app/scripts/init_app_engagement.py 种子（附录 B，
自包含复制不 import 引擎）。另锁：confirm 升级门（candidate 必须满足分支升级
规则且 evidence_ref 非空）、红线 invariants 行为（永不自动重放/永不发新请求/
secret_candidate/platform 列/零网络 import）。

纯离线：只读仓库文件，不发任何网络请求。
"""
from __future__ import annotations

import ast
import csv
import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorized_assessment.app import cloud_function_review as cfr  # noqa: E402
from authorized_assessment.app import cloud_storage_review as cse  # noqa: E402
from authorized_assessment.app import crypto_secret_review as csr  # noqa: E402
from authorized_assessment.app import local_data_exposure as lde  # noqa: E402
from authorized_assessment.app import platform_login_exchange as ple  # noqa: E402
from authorized_assessment.app import session_token_lifecycle as stl  # noqa: E402
from authorized_assessment.app import signature_replay_review as srr  # noqa: E402
from authorized_assessment.app import static_dynamic_reconciliation as sdr  # noqa: E402
from authorized_assessment.app import third_party_boundary_review as tpr  # noqa: E402
from authorized_assessment.triage import injection_candidates as ic  # noqa: E402

INIT_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "init_app_engagement.py"
AUDIT_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "audit_app_engagement.py"
APP_PKG = ROOT / "src" / "authorized_assessment" / "app"

AUTH_CONTRACT = json.loads(
    (ROOT / "contracts" / "app_auth_schema.json").read_text(encoding="utf-8-sig")
)
STORAGE_CONTRACT = json.loads(
    (ROOT / "contracts" / "app_storage_package_schema.json").read_text(encoding="utf-8-sig")
)
RECON_CONTRACT = json.loads(
    (ROOT / "contracts" / "app_reconciliation_schema.json").read_text(encoding="utf-8-sig")
)
CLOUD_CONTRACT = json.loads(
    (ROOT / "contracts" / "app_cloud_schema.json").read_text(encoding="utf-8-sig")
)

# B6 九模块（网络 import 扫描 + 行为锁定对象）。
B6_MODULES = (
    "platform_login_exchange",
    "session_token_lifecycle",
    "signature_replay_review",
    "local_data_exposure",
    "crypto_secret_review",
    "static_dynamic_reconciliation",
    "cloud_function_review",
    "cloud_storage_review",
    "third_party_boundary_review",
)

# 域定义表：(模块, phase, 分支常量名, 产物常量名)。
REVIEW_JSON_MODULES = (
    (ple, "platform_login_exchange", "PLATFORM_LOGIN_BRANCHES", "PLATFORM_LOGIN_REVIEW_ARTIFACT"),
    (stl, "session_token_lifecycle", "SESSION_TOKEN_BRANCHES", "SESSION_TOKEN_REVIEW_ARTIFACT"),
    (srr, "signature_replay", "SIGNATURE_REPLAY_BRANCHES", "SIGNATURE_REPLAY_REVIEW_ARTIFACT"),
    (lde, "local_data_exposure", "LOCAL_DATA_BRANCHES", "LOCAL_DATA_REVIEW_ARTIFACT"),
    (csr, "crypto_and_secret_handling", "CRYPTO_SECRET_BRANCHES", "CRYPTO_SECRET_REVIEW_ARTIFACT"),
    (cfr, "cloud_function_testing", "CLOUD_FUNCTION_BRANCHES", "CLOUD_FUNCTION_REVIEW_ARTIFACT"),
    (cse, "cloud_storage_acl_testing", "CLOUD_STORAGE_BRANCHES", "CLOUD_STORAGE_REVIEW_ARTIFACT"),
)
CONTRACT_OF_PHASE = {
    "platform_login_exchange": AUTH_CONTRACT,
    "session_token_lifecycle": AUTH_CONTRACT,
    "signature_replay": AUTH_CONTRACT,
    "local_data_exposure": STORAGE_CONTRACT,
    "crypto_and_secret_handling": STORAGE_CONTRACT,
    "cloud_function_testing": CLOUD_CONTRACT,
    "cloud_storage_acl_testing": CLOUD_CONTRACT,
}


def _load_skill_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 分支常量 ↔ 契约 ↔ init 种子三方同源（J-B6 验收第 2 项）
# ---------------------------------------------------------------------------

def test_review_json_branches_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_b6", INIT_SCRIPT)
    expected_counts = {
        "platform_login_exchange": 5,
        "session_token_lifecycle": 5,
        "signature_replay": 4,
        "local_data_exposure": 5,
        "crypto_and_secret_handling": 4,
        "cloud_function_testing": 3,
        "cloud_storage_acl_testing": 3,
    }
    for module, phase, branches_attr, _artifact_attr in REVIEW_JSON_MODULES:
        branches = getattr(module, branches_attr)
        contract_spec = CONTRACT_OF_PHASE[phase]["phases"][phase]
        assert tuple(contract_spec["branches"]) == branches, phase
        assert tuple(contract_spec["branches"]) == tuple(init_mod.PHASE_BRANCHES[phase]), phase
        assert len(branches) == expected_counts[phase], phase


def test_review_json_artifact_paths_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_b6", INIT_SCRIPT)
    for module, phase, _branches_attr, artifact_attr in REVIEW_JSON_MODULES:
        artifact = getattr(module, artifact_attr)
        contract_spec = CONTRACT_OF_PHASE[phase]["phases"][phase]
        assert contract_spec["artifact"] == artifact, phase
        assert contract_spec["artifact"] == init_mod.PHASE_ARTIFACTS[phase][0], phase
    # 三方产物路径字面锚点（附录 B 种子）。
    assert ple.PLATFORM_LOGIN_REVIEW_ARTIFACT == "artifacts/app/auth/platform-login-review.json"
    assert stl.SESSION_TOKEN_REVIEW_ARTIFACT == "artifacts/app/auth/session-lifecycle-review.json"
    assert srr.SIGNATURE_REPLAY_REVIEW_ARTIFACT == "artifacts/app/auth/signature-replay-review.json"
    assert lde.LOCAL_DATA_REVIEW_ARTIFACT == "artifacts/app/storage/local-data-review.json"
    assert csr.CRYPTO_SECRET_REVIEW_ARTIFACT == "artifacts/app/crypto/secret-review.json"
    assert cfr.CLOUD_FUNCTION_REVIEW_ARTIFACT == "artifacts/app/cloud/cloud-function-review.json"
    assert cse.CLOUD_STORAGE_REVIEW_ARTIFACT == "artifacts/app/cloud/object-storage-review.json"


def test_contract_identity_and_phase_maps():
    init_mod = _load_skill_module("app_init_seed_b6", INIT_SCRIPT)
    assert ple.APP_AUTH_CONTRACT == AUTH_CONTRACT["contract"] == "app_auth_schema"
    assert ple.APP_AUTH_SCHEMA_VERSION == AUTH_CONTRACT["schema_version"] == "1.0"
    assert tuple(ple.AUTH_PHASES) == tuple(AUTH_CONTRACT["phases"]) == tuple(init_mod.AUTH_REVIEW_BRANCHES)
    assert ple.AUTH_REVIEW_ARTIFACTS == {
        phase: spec["artifact"] for phase, spec in AUTH_CONTRACT["phases"].items()
    }
    assert cfr.APP_CLOUD_CONTRACT == CLOUD_CONTRACT["contract"] == "app_cloud_schema"
    assert cfr.APP_CLOUD_SCHEMA_VERSION == CLOUD_CONTRACT["schema_version"] == "1.0"
    assert tuple(cfr.APP_CLOUD_PHASES) == tuple(CLOUD_CONTRACT["phases"]) == tuple(init_mod.CLOUD_REVIEW_BRANCHES)
    assert cfr.APP_CLOUD_ARTIFACTS == {
        phase: spec["artifact"] for phase, spec in CLOUD_CONTRACT["phases"].items()
    }
    assert tuple(cfr.APP_CLOUD_REVIEW_JSON_PHASES) == tuple(
        CLOUD_CONTRACT["artifact_fields"]["review_json_phases"]
    )
    assert sdr.APP_RECONCILIATION_CONTRACT == RECON_CONTRACT["contract"] == "app_reconciliation_schema"
    assert sdr.APP_RECONCILIATION_SCHEMA_VERSION == RECON_CONTRACT["schema_version"] == "1.0"


def test_reconciliation_branches_states_csv_fields_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_b6", INIT_SCRIPT)
    audit_mod = _load_skill_module("app_audit_seed_b6", AUDIT_SCRIPT)
    spec = RECON_CONTRACT["phases"][sdr.RECONCILIATION_PHASE]
    assert tuple(spec["branches"]) == sdr.RECONCILIATION_BRANCHES
    assert tuple(spec["branches"]) == tuple(init_mod.PHASE_BRANCHES[sdr.RECONCILIATION_PHASE])
    assert len(sdr.RECONCILIATION_BRANCHES) == 5
    assert spec["artifact"] == sdr.RECONCILIATION_ARTIFACT == (
        "artifacts/app/reconciliation/static-dynamic-endpoints.csv"
    )
    assert spec["artifact"] == init_mod.PHASE_ARTIFACTS[sdr.RECONCILIATION_PHASE][0]
    assert tuple(spec["csv_fields"]) == sdr.RECONCILIATION_CSV_FIELDS == tuple(init_mod.RECONCILIATION_CSV_FIELDS)
    assert tuple(spec["endpoint_states"]) == sdr.RECONCILIATION_ENDPOINT_STATES == tuple(
        init_mod.RECONCILIATION_ENDPOINT_STATES
    ) == tuple(audit_mod.RECONCILIATION_ENDPOINT_STATES)
    assert tuple(spec["judgment_states"]) == sdr.RECONCILIATION_JUDGMENT_STATES == tuple(
        audit_mod.RECONCILIATION_JUDGMENT_STATES
    )
    assert len(sdr.RECONCILIATION_ENDPOINT_STATES) == 10
    assert set(sdr.RECONCILIATION_JUDGMENT_STATES) < set(sdr.RECONCILIATION_ENDPOINT_STATES)


def test_third_party_phase_branches_csv_enums_three_way_sync():
    init_mod = _load_skill_module("app_init_seed_b6", INIT_SCRIPT)
    audit_mod = _load_skill_module("app_audit_seed_b6", AUDIT_SCRIPT)
    spec = CLOUD_CONTRACT["phases"][tpr.THIRD_PARTY_PHASE]
    assert tpr.THIRD_PARTY_PHASE == "third_party_sdk_platform_boundary"
    assert tuple(spec["branches"]) == tpr.THIRD_PARTY_BRANCHES
    assert tuple(spec["branches"]) == tuple(init_mod.PHASE_BRANCHES[tpr.THIRD_PARTY_PHASE])
    assert len(tpr.THIRD_PARTY_BRANCHES) == 2
    assert spec["artifact"] == tpr.THIRD_PARTY_BOUNDARY_ARTIFACT == (
        "artifacts/app/cloud/third-party-boundary.csv"
    )
    assert spec["artifact"] == init_mod.PHASE_ARTIFACTS[tpr.THIRD_PARTY_PHASE][0]
    assert tuple(spec["csv_fields"]) == tpr.THIRD_PARTY_CSV_FIELDS == tuple(
        init_mod.REVIEW_CSV_ARTIFACTS[tpr.THIRD_PARTY_BOUNDARY_ARTIFACT]
    )
    assert tuple(spec["service_types"]) == tpr.THIRD_PARTY_SERVICE_TYPES == tuple(
        audit_mod.THIRD_PARTY_SERVICE_TYPES
    )
    assert tuple(spec["attribution_values"]) == tpr.THIRD_PARTY_ATTRIBUTION_VALUES
    assert set(tpr.THIRD_PARTY_ATTRIBUTION_VALUES) == set(audit_mod.THIRD_PARTY_ATTRIBUTION_VALUES)


# ---------------------------------------------------------------------------
# confirm 升级门：确认形态与分支一一对应、不跨分支、evidence_ref 强制
# ---------------------------------------------------------------------------

UPGRADE_DOMAINS = (
    (ple.PLATFORM_LOGIN_BRANCHES, ple.PLATFORM_LOGIN_EVIDENCE_KINDS,
     ple.PLATFORM_LOGIN_INSUFFICIENT_KINDS, ple.PLATFORM_LOGIN_UPGRADE_RULES),
    (stl.SESSION_TOKEN_BRANCHES, stl.SESSION_TOKEN_EVIDENCE_KINDS,
     stl.SESSION_TOKEN_INSUFFICIENT_KINDS, stl.SESSION_TOKEN_UPGRADE_RULES),
    (srr.SIGNATURE_REPLAY_BRANCHES, srr.SIGNATURE_REPLAY_EVIDENCE_KINDS,
     srr.SIGNATURE_REPLAY_INSUFFICIENT_KINDS, srr.SIGNATURE_REPLAY_UPGRADE_RULES),
    (lde.LOCAL_DATA_BRANCHES, lde.LOCAL_DATA_EVIDENCE_KINDS,
     lde.LOCAL_DATA_INSUFFICIENT_KINDS, lde.LOCAL_DATA_UPGRADE_RULES),
    (csr.CRYPTO_SECRET_BRANCHES, csr.CRYPTO_SECRET_EVIDENCE_KINDS,
     csr.CRYPTO_SECRET_INSUFFICIENT_KINDS, csr.CRYPTO_SECRET_UPGRADE_RULES),
    (cfr.CLOUD_FUNCTION_BRANCHES, cfr.CLOUD_FUNCTION_EVIDENCE_KINDS,
     cfr.CLOUD_FUNCTION_INSUFFICIENT_KINDS, cfr.CLOUD_FUNCTION_UPGRADE_RULES),
    (cse.CLOUD_STORAGE_BRANCHES, cse.CLOUD_STORAGE_EVIDENCE_KINDS,
     cse.CLOUD_STORAGE_INSUFFICIENT_KINDS, cse.CLOUD_STORAGE_UPGRADE_RULES),
    (tpr.THIRD_PARTY_BRANCHES, tpr.THIRD_PARTY_EVIDENCE_KINDS,
     tpr.THIRD_PARTY_INSUFFICIENT_KINDS, tpr.THIRD_PARTY_UPGRADE_RULES),
)


def test_upgrade_rules_cover_all_branches_one_to_one_no_cross_branch():
    for branches, kinds, insufficient, rules in UPGRADE_DOMAINS:
        confirmed = sorted(set(kinds) - set(insufficient))
        assert sorted(rules) == sorted(branches)
        used = {
            kind
            for rule in rules.values()
            for group in rule["required_any_groups"]
            for kind in group
        }
        assert used == set(confirmed), "确认形态必须与可升级分支一一对应、不跨分支"
        for branch, rule in rules.items():
            for group in rule["required_any_groups"]:
                for kind in group:
                    assert kind not in insufficient
        # token_survives_logout_confirmed 同时门 token_persistence/logout_cleanup、
        # cloud_env 双形态任一满足等均为设计内共享；跨域锁定到此为止，形态级排他
        # 不作断言。


def test_observation_maps_and_docs_cover_all_kinds():
    domain_maps = (
        (ple.PLATFORM_LOGIN_EVIDENCE_KINDS, ple.PLATFORM_LOGIN_OBSERVATION_EVIDENCE_MAP,
         ple.PLATFORM_LOGIN_OBSERVATION_FIELD_DOCS),
        (stl.SESSION_TOKEN_EVIDENCE_KINDS, stl.SESSION_TOKEN_OBSERVATION_EVIDENCE_MAP,
         stl.SESSION_TOKEN_OBSERVATION_FIELD_DOCS),
        (srr.SIGNATURE_REPLAY_EVIDENCE_KINDS, srr.SIGNATURE_REPLAY_OBSERVATION_EVIDENCE_MAP,
         srr.SIGNATURE_REPLAY_OBSERVATION_FIELD_DOCS),
        (lde.LOCAL_DATA_EVIDENCE_KINDS, lde.LOCAL_DATA_OBSERVATION_EVIDENCE_MAP,
         lde.LOCAL_DATA_OBSERVATION_FIELD_DOCS),
        (csr.CRYPTO_SECRET_EVIDENCE_KINDS, csr.CRYPTO_SECRET_OBSERVATION_EVIDENCE_MAP,
         csr.CRYPTO_SECRET_OBSERVATION_FIELD_DOCS),
        (cfr.CLOUD_FUNCTION_EVIDENCE_KINDS, cfr.CLOUD_FUNCTION_OBSERVATION_EVIDENCE_MAP,
         cfr.CLOUD_FUNCTION_OBSERVATION_FIELD_DOCS),
        (cse.CLOUD_STORAGE_EVIDENCE_KINDS, cse.CLOUD_STORAGE_OBSERVATION_EVIDENCE_MAP,
         cse.CLOUD_STORAGE_OBSERVATION_FIELD_DOCS),
        (tpr.THIRD_PARTY_EVIDENCE_KINDS, tpr.THIRD_PARTY_OBSERVATION_EVIDENCE_MAP,
         tpr.THIRD_PARTY_OBSERVATION_FIELD_DOCS),
    )
    for kinds, evidence_map, docs in domain_maps:
        assert set(evidence_map) == set(kinds)
        assert set(evidence_map.values()) == set(kinds)  # 恒等映射
        assert set(docs) == set(kinds)


def test_candidate_requires_confirmed_kind_and_evidence_ref():
    # 形态观察永不升级（signal）；candidate 缺 evidence_ref = 违例；缺确认形态的
    # 越级 candidate = 违例（confirm 升级门）。
    rows, _summaries, violations = ple.screen_platform_login_observations(
        [
            {
                "branch": "oauth_code_one_time",
                "applicability": "applicable",
                "source": "materials/working/demo.har",
                "evidence": {"oauth_code_reuse_accepted_observed": True},
                "evidence_ref": "evidence/raw/demo.har:L12",
            },
            {
                "branch": "oauth_code_one_time",
                "applicability": "applicable",
                "source": "materials/working/demo.har 复核",
                "evidence": {"oauth_code_replay_confirmed": True},
                "precondition": "既有只读证据复核，未重放授权码",
                "reason": "同一授权码二次兑换出有效会话",
            },
        ]
    )
    assert rows[0]["status"] == "signal"
    assert rows[1]["status"] == "candidate"
    assert any("evidence_ref" in v for v in violations)
    # 越级：无确认形态却声明 candidate → validate 拒绝。
    bogus = {
        "row_id": "X-0001",
        "branch": "oauth_code_one_time",
        "status": "candidate",
        "evidence_kinds": ["oauth_code_reuse_accepted_observed"],
        "source": "materials/working/demo.har",
        "evidence_ref": "evidence/raw/demo.har:L12",
        "precondition": "",
        "reason": "",
    }
    assert ple.validate_platform_login_candidate(bogus) != []
    assert stl.validate_session_token_candidate(
        {**bogus, "branch": "token_rotation", "evidence_kinds": ["rotation_marker_observed"]}
    ) != []


def test_status_hint_respected_and_na_requires_reason():
    rows, _s, violations = srr.screen_signature_replay_observations(
        [
            {
                "branch": "replay_window",
                "applicability": "applicable",
                "source": "traffic",
                "evidence": {"replay_accepted_observed": True},
                "evidence_ref": "evidence/raw/t.har:L3",
                "status_hint": "needs_manual_validation",
            },
            {
                "branch": "nonce_timestamp",
                "applicability": "not_applicable",
                "source": "traffic",
                "reason": "",
            },
        ],
        all_branches=False,
    )
    assert rows[0]["status"] == "needs_manual_validation"
    assert any("not_applicable 但 reason 为空" in v for v in violations)


def test_screening_happy_path_build_and_validate_artifacts():
    # 七个 review JSON 域：screen → summaries 覆盖全分支 → build → validate=0。
    happy = [
        (ple.screen_platform_login_observations, ple.build_platform_login_review_artifact,
         ple.validate_platform_login_review_artifact),
        (stl.screen_session_token_observations, stl.build_session_token_review_artifact,
         stl.validate_session_token_review_artifact),
        (srr.screen_signature_replay_observations, srr.build_signature_replay_review_artifact,
         srr.validate_signature_replay_review_artifact),
        (lde.screen_local_data_observations, lde.build_local_data_review_artifact,
         lde.validate_local_data_review_artifact),
        (csr.screen_crypto_secret_observations, csr.build_crypto_secret_review_artifact,
         csr.validate_crypto_secret_review_artifact),
        (cfr.screen_cloud_function_observations, cfr.build_cloud_function_review_artifact,
         cfr.validate_cloud_function_review_artifact),
        (cse.screen_cloud_storage_observations, cse.build_cloud_storage_review_artifact,
         cse.validate_cloud_storage_review_artifact),
    ]
    for screen, build, validate in happy:
        rows, summaries, violations = screen([])
        assert not violations
        # 空筛选：全分支无观察无 not_applicable 记录 → 聚合 inconclusive（不是
        # not_applicable——审计不得把空串/无记录当作 not_applicable，同契约不变量）。
        assert all(summary["branch_status"] == "inconclusive" for summary in summaries)
        artifact = build(
            rows, summaries, violations,
            authorization_basis="operator_supplied_material",
            updated_at="2026-09-09T00:00:00+08:00",
        )
        assert not validate(artifact)
        assert len(artifact["rows_fields" if False else "row_fields"]) == 8
        assert len(artifact) == 12  # 12 键 review JSON 形状
    # CSV 形状 phase 混用 review JSON 构建 → ValueError（契约 artifact_format 区分）。
    import pytest

    with pytest.raises(ValueError):
        cfr.build_app_cloud_review_artifact(
            "third_party_sdk_platform_boundary", [], [], [],
            "operator_supplied_material", "t",
        )
    assert cfr.validate_app_cloud_review_artifact(
        {}, "third_party_sdk_platform_boundary", cfr.CLOUD_FUNCTION_BRANCHES,
        cfr.CLOUD_FUNCTION_EVIDENCE_KINDS, cfr.CLOUD_FUNCTION_INSUFFICIENT_KINDS,
        cfr.CLOUD_FUNCTION_UPGRADE_RULES,
    ) != []


# ---------------------------------------------------------------------------
# 红线 invariants 行为锁定
# ---------------------------------------------------------------------------

def test_signature_replay_never_replays_invariants_and_no_network_code():
    # invariants 写明永不自动重放任何请求（含只读）。
    assert any("永不自动重放任何请求（含只读）" in inv for inv in srr.SIGNATURE_REPLAY_INVARIANTS)
    assert "永不自动重放" in srr.SIGNATURE_REPLAY_OFFLINE_RULE
    # 确认语义来自既有只读证据复核，不是实际重放。
    joined_docs = " ".join(srr.SIGNATURE_REPLAY_OBSERVATION_FIELD_DOCS.values())
    assert "本模块不实际重放" in joined_docs
    # 契约红线同源在场。
    assert any("永不自动重放" in str(line) for line in AUTH_CONTRACT["red_lines"])


def test_b6_modules_have_no_network_imports():
    # 九模块 AST 扫描：禁止 requests/httpx/urllib/socket/http.client/ssl/subprocess
    # import（零网络；signature_replay 尤其不得含任何发请求代码路径）。
    forbidden = {"requests", "httpx", "urllib", "urllib3", "socket", "http", "ssl", "subprocess"}
    for module_name in B6_MODULES:
        source = (APP_PKG / f"{module_name}.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            roots: set[str] = set()
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            bad = roots & forbidden
            assert not bad, f"{module_name} 不得引入网络/子进程模块：{bad}"


def test_local_and_crypto_platform_column_semantics():
    # platform ∈ {android, ios}；缺失/非法记违例；行扩展键不破坏 12 键 artifact 形状。
    rows, _s, violations = lde.screen_local_data_observations(
        [
            {
                "branch": "token_persistence", "applicability": "applicable",
                "source": "指定测试设备观察", "platform": "android",
                "evidence": {"token_storage_key_observed": True},
                "evidence_ref": "evidence/raw/device.txt:L1",
            },
            {
                "branch": "logout_cleanup", "applicability": "applicable",
                "source": "指定测试设备观察", "platform": "harmony",
                "evidence": {"residual_data_after_logout_observed": True},
                "evidence_ref": "evidence/raw/device.txt:L2",
            },
            {
                "branch": "local_cache_database", "applicability": "applicable",
                "source": "ios 快照", "evidence": {"cache_directory_clue_observed": True},
                "evidence_ref": "evidence/raw/ios.png",
            },
        ]
    )
    assert [row["platform"] for row in rows] == ["android", "harmony", ""]
    assert sum(1 for v in violations if "platform 非法/缺失" in v) == 2
    assert rows[0]["platform"] == "android"
    assert lde.APP_PLATFORM_VALUES == ("android", "ios")
    assert lde.validate_local_data_candidate({**rows[0], "platform": "ios"}) == []
    assert any(
        "platform" in v for v in lde.validate_local_data_candidate({**rows[0], "platform": ""})
    )
    artifact = lde.build_local_data_review_artifact(
        rows, _s, [], authorization_basis="operator_supplied_material", updated_at="t"
    )
    assert len(artifact) == 12  # 12 键 artifact 形状不因行扩展键破坏
    assert len(artifact["row_fields"]) == 8  # platform 是行扩展键，row_fields 仍为契约 8 字段
    assert "platform" in artifact["rows"][0]
    # crypto 复用同一 platform 助手（storage 两 phase 同款形状）。
    rows2, _s2, violations2 = csr.screen_crypto_secret_observations(
        [
            {
                "branch": "hardcoded_secrets", "applicability": "applicable",
                "source": "jadx 产物", "platform": "ios",
                "evidence": {"secret_like_string_observed": True},
                "evidence_ref": "artifacts/app/unpacked/demo/sources/X.java:L9",
            }
        ]
    )
    assert not violations2
    assert rows2[0]["platform"] == "ios" and rows2[0]["status"] == "signal"


def test_crypto_secret_candidate_red_line():
    # secret_candidate 红线：未证实密钥字符串只记 signal，永不升级；确认有效性
    # （secret_reachable_confirmed）才可 candidate。
    assert "secret_candidate" in csr.SECRET_CANDIDATE_RED_LINE
    assert "signal" in csr.SECRET_CANDIDATE_RED_LINE
    assert any("secret_candidate" in inv for inv in csr.CRYPTO_SECRET_INVARIANTS)
    rows, _s, violations = csr.screen_crypto_secret_observations(
        [
            {
                "branch": "hardcoded_secrets", "applicability": "applicable",
                "source": "jadx 产物", "platform": "android",
                "evidence": {"secret_like_string_observed": True},
                "evidence_ref": "artifacts/app/unpacked/demo/sources/Config.java:L4",
                "reason": "疑似 AK 常量（secret_candidate 线索）",
            },
            {
                "branch": "hardcoded_secrets", "applicability": "applicable",
                "source": "既有流量复核", "platform": "android",
                "evidence": {"secret_reachable_confirmed": True},
                "evidence_ref": "evidence/raw/demo.har:L77",
                "precondition": "既有只读证据复核，未主动验证密钥",
            },
        ]
    )
    assert not violations
    assert rows[0]["status"] == "signal"
    assert rows[1]["status"] == "candidate"
    # 契约红线在场。
    assert any("secret_candidate" in str(line) for line in STORAGE_CONTRACT["red_lines"])
    # 不做 key 有效性探测、不发请求。
    assert "不做 key 有效性探测" in csr.SECRET_CANDIDATE_RED_LINE


def test_reconciliation_deterministic_ten_state_classification():
    # 十态确定性分类真值表：判定资格修饰优先于出现位置；无证据兜底 manual。
    truth = [
        ({"static_seen": True}, "static_only"),
        ({"dynamic_seen": True}, "dynamic_only"),
        ({"static_seen": True, "dynamic_seen": True}, "both_seen"),
        ({"static_seen": True, "feature_gated_hint": True}, "feature_gated"),
        ({"dynamic_seen": True, "stale_hint": True}, "stale"),
        ({"static_seen": True, "version_hint": True}, "version_specific"),
        ({"dynamic_seen": True, "third_party_hint": True}, "third_party"),
        ({"static_seen": True, "platform_shared_hint": True}, "platform_shared"),
        ({"static_seen": True, "unreachable_hint": True}, "unreachable"),
        ({"dynamic_seen": True, "needs_manual_hint": True}, "needs_manual_validation"),
        ({}, "needs_manual_validation"),
    ]
    for evidence, expected in truth:
        assert sdr.classify_endpoint_status(evidence) == expected, evidence
        assert sdr.classify_endpoint_status(evidence) == sdr.classify_endpoint_status(evidence)
    # 修饰优先级全序（高 > 低，覆盖出现位置）。
    precedence = {
        "needs_manual_hint": "needs_manual_validation",
        "unreachable_hint": "unreachable",
        "stale_hint": "stale",
        "feature_gated_hint": "feature_gated",
        "version_hint": "version_specific",
        "third_party_hint": "third_party",
        "platform_shared_hint": "platform_shared",
    }
    keys = list(precedence)
    for i in range(len(keys) - 1):
        winner = {keys[i]: True, keys[i + 1]: True, "static_seen": True, "dynamic_seen": True}
        assert sdr.classify_endpoint_status(winner) == precedence[keys[i]]
    # 红线：永不发新请求。
    assert "永不发新请求" in sdr.RECONCILIATION_NO_PROBE_RULE
    assert any("永不发新请求" in inv for inv in sdr.RECONCILIATION_INVARIANTS)


def test_reconciliation_rows_validation_and_csv_roundtrip():
    row = sdr.build_reconciliation_row(
        {
            "endpoint_id": "EP-0001",
            "host": "api.demo.com",
            "method": "GET",
            "path": "/v1/user",
            "source_material": "jadx 产物",
            "static_evidence_ref": "artifacts/app/unpacked/demo/sources/U.java:L5",
            "dynamic_evidence_ref": "",
            "evidence": {"static_seen": True},
        }
    )
    assert row["status"] == "static_only"
    assert sdr.validate_reconciliation_rows([row]) == []
    # 判定行（stale/unreachable/needs_manual_validation）reason 非空强制。
    stale_row = sdr.build_reconciliation_row(
        {"endpoint_id": "EP-0002", "host": "api.demo.com", "method": "GET", "path": "/v1/old",
         "evidence": {"stale_hint": True}}
    )
    assert stale_row["status"] == "stale"
    violations = sdr.validate_reconciliation_rows([stale_row])
    assert any("需要非空 reason" in v for v in violations)
    stale_row["reason"] = "旧版本端点，客户端已无调用点"
    assert sdr.validate_reconciliation_rows([stale_row]) == []
    # 非法状态值拒绝。
    assert sdr.validate_reconciliation_rows(
        [{"endpoint_id": "EP-0003", "status": "verified_vulnerable", "reason": "x"}]
    ) != []
    # CSV 渲染表头精确等于契约 csv_fields（顺序敏感）。
    text = sdr.render_reconciliation_csv([stale_row])
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    assert header == list(sdr.RECONCILIATION_CSV_FIELDS)


def test_third_party_boundary_screening_and_csv_roundtrip():
    rows, summaries, violations = tpr.screen_third_party_boundary_observations(
        [
            {
                "branch": "third_party_service_boundary", "applicability": "applicable",
                "source": "manifest+sdk 配置", "service_name": "demo-maps",
                "service_type": "map", "host": "maps.third.example",
                "attribution": "third_party",
                "evidence": {"third_party_endpoint_observed": True},
            },
            {
                "branch": "platform_shared_asset_attribution", "applicability": "applicable",
                "source": "hosts.csv 对账", "service_name": "vendor-cdn",
                "service_type": "sdk", "host": "cdn.vendor.example",
                "attribution": "platform_shared",
                "evidence": {"platform_shared_asset_misattributed_confirmed": True},
                "evidence_ref": "hosts.csv:cdn.vendor.example",
                "precondition": "既有只读证据复核",
                "reason": "平台共享资产被记录为 in_scope",
            },
        ]
    )
    assert not violations, violations
    assert rows[0]["boundary_status"] == "signal"
    assert rows[1]["boundary_status"] == "candidate"
    assert rows[0]["row_id"] == "tp-0001" and rows[1]["row_id"] == "tp-0002"
    substatuses = {s["branch"]: s["branch_status"] for s in summaries}
    assert substatuses == {
        "third_party_service_boundary": "inconclusive",  # signal-only，无定论状态
        "platform_shared_asset_attribution": "tested",  # candidate ∈ 定论状态
    }
    # precondition 不写入 CSV（9 列契约形状），candidate 需 evidence_ref。
    text = tpr.render_third_party_boundary_csv(rows)
    header = next(csv.reader(io.StringIO(text)))
    assert header == list(tpr.THIRD_PARTY_CSV_FIELDS)
    assert "precondition" not in text.splitlines()[1]
    # 待确认归属行缺 reason → 违例。
    assert any(
        "需要非空 reason" in v
        for v in tpr.validate_third_party_boundary_rows(
            [{"service_type": "map", "attribution": "unclassified",
              "boundary_status": "signal"}]
        )
    )
    # 红线常量在场。
    assert "不触发真实支付" in tpr.THIRD_PARTY_NO_PAYMENT_RULE


def test_auth_red_line_constants_match_contract():
    joined = " ".join(AUTH_CONTRACT["red_lines"])
    assert ple.APP_NO_CREDENTIAL_CREATION_RULE in joined
    assert "运营商一键登录 token" in joined
    assert ple.APP_DEVICE_IDENTITY_CREDENTIAL_RULE.startswith(
        "运营商一键登录 token、device-id、Android ID/IDFA/IDFV"
    )
    assert ple.UID_NOT_AUTHORIZATION_RULE.startswith("uid/手机号/公开设备标识不是授权依据")
    assert "不自动登录、不申请或续期凭证" in stl.TOKEN_REVIEW_MATERIAL_RULE
    assert "写操作归审批门" in stl.NO_TOKEN_WRITE_REPLAY_RULE
