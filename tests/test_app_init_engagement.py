"""Regression tests for init_app_engagement (plan §7.2/§5.8/appendix B, batch B2/W17).

锁定：§5.8 workspace 骨架齐全、零网络断言、resume 输入 hash 校验、33 phase 种子
与 12 组 substatuses 与方案附录 B 完全一致、identity/platform_identification 按
输入字段自动 complete。
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "init_app_engagement.py"
ROUTING_SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "phase_status_routing.py"

# 方案附录 B：33 阶段（顺序即种子顺序）。
APPENDIX_B_PHASES = (
    "authorization",
    "identity",
    "platform_identification",
    "material_acquisition",
    "initial_decoding",
    "preflight",
    "package_inventory",
    "package_unpack_decompile",
    "source_reconstruction",
    "package_integrity_hardening_review",
    "static_analysis",
    "endpoint_inventory",
    "host_classification",
    "dynamic_setup",
    "dynamic_mapping",
    "static_dynamic_reconciliation",
    "platform_login_exchange",
    "session_token_lifecycle",
    "signature_replay",
    "backend_web_api_testing",
    "access_control_testing",
    "input_file_testing",
    "business_logic_testing",
    "local_data_exposure",
    "crypto_and_secret_handling",
    "webview_bridge_links",
    "ipc_component_boundary",
    "cloud_function_testing",
    "cloud_storage_acl_testing",
    "third_party_sdk_platform_boundary",
    "candidate_validation",
    "reporting",
    "cleanup",
)

# 方案附录 B：12 组 substatuses（phase → 分支键）。
APPENDIX_B_SUBSTATUSES = {
    "package_integrity_hardening_review": (
        "package_version_inventory", "signing_integrity", "hardening_obfuscation_markers",
        "debug_switches", "debug_info_exposure", "update_endpoint_environment",
        "trusted_update_config",
    ),
    "static_dynamic_reconciliation": (
        "static_endpoint_base", "dynamic_endpoint_base", "match_status_classification",
        "hidden_flow_identification", "stale_entry_disposition",
    ),
    "platform_login_exchange": (
        "oauth_code_one_time", "oauth_code_expiry", "one_click_login_device_binding",
        "access_token_custody", "uid_authorization_basis",
    ),
    "session_token_lifecycle": (
        "token_rotation", "token_revocation_logout", "multi_device_login",
        "stale_token_new_api", "device_user_tenant_binding",
    ),
    "signature_replay": (
        "nonce_timestamp", "signature_canonicalization", "replay_window", "binding_scope",
    ),
    "local_data_exposure": (
        "token_persistence", "logout_cleanup", "local_cache_database",
        "logs_clipboard_screenshots", "temp_files",
    ),
    "crypto_and_secret_handling": (
        "hardcoded_secrets", "custom_crypto", "weak_random_key_derivation",
        "debug_config_env_keys",
    ),
    "webview_bridge_links": (
        "webview_allowed_domains", "postmessage_origin", "cookie_token_sharing_boundary",
        "bridge_method_exposure", "custom_scheme", "deep_link_sensitive_params",
        "external_app_browser_jump",
    ),
    "ipc_component_boundary": (
        "exported_activity", "exported_service", "exported_receiver", "exported_provider",
        "custom_scheme_deeplink", "universal_link", "ios_extension_boundary",
    ),
    "cloud_function_testing": (
        "anonymous_invocation", "function_parameter_role_validation", "cloud_env_id_mixing",
    ),
    "cloud_storage_acl_testing": (
        "cloud_database_rules", "object_storage_acl", "signed_url_binding",
    ),
    "third_party_sdk_platform_boundary": (
        "third_party_service_boundary", "platform_shared_asset_attribution",
    ),
}

# 方案附录 B：每 phase 的 artifacts 种子值。
APPENDIX_B_ARTIFACTS = {
    "authorization": ["engagement.json"],
    "identity": ["app.json"],
    "platform_identification": ["app.json"],
    "material_acquisition": [],
    "initial_decoding": ["artifacts/decoding-ledger.csv"],
    "preflight": [],
    "package_inventory": ["artifacts/app/package-inventory.csv"],
    "package_unpack_decompile": ["artifacts/app/unpacked"],
    "source_reconstruction": ["artifacts/source-map.csv"],
    "package_integrity_hardening_review": ["artifacts/app/package/hardening-review.json"],
    "static_analysis": [],
    "endpoint_inventory": ["endpoints.csv"],
    "host_classification": ["hosts.csv"],
    "dynamic_setup": [],
    "dynamic_mapping": [],
    "static_dynamic_reconciliation": ["artifacts/app/reconciliation/static-dynamic-endpoints.csv"],
    "platform_login_exchange": ["artifacts/app/auth/platform-login-review.json"],
    "session_token_lifecycle": ["artifacts/app/auth/session-lifecycle-review.json"],
    "signature_replay": ["artifacts/app/auth/signature-replay-review.json"],
    "backend_web_api_testing": [],
    "access_control_testing": [],
    "input_file_testing": [],
    "business_logic_testing": [],
    "local_data_exposure": ["artifacts/app/storage/local-data-review.json"],
    "crypto_and_secret_handling": ["artifacts/app/crypto/secret-review.json"],
    "webview_bridge_links": [
        "artifacts/app/webview/webview-origin-inventory.csv",
        "artifacts/app/webview/bridge-method-inventory.csv",
        "artifacts/app/webview/deep-link-review-queue.csv",
    ],
    "ipc_component_boundary": [
        "artifacts/app/ipc/component-inventory.csv",
        "artifacts/app/ipc/deeplink-review-queue.csv",
    ],
    "cloud_function_testing": ["artifacts/app/cloud/cloud-function-review.json"],
    "cloud_storage_acl_testing": ["artifacts/app/cloud/object-storage-review.json"],
    "third_party_sdk_platform_boundary": ["artifacts/app/cloud/third-party-boundary.csv"],
    "candidate_validation": [],
    "reporting": ["reports/final-report.md"],
    "cleanup": [],
}

# §5.8 workspace 骨架（init 必须落盘的文件与目录）。
SKELETON_FILES = (
    "engagement.json",
    "app.json",
    "phase_status.app.json",
    "scope.csv",
    "hosts.csv",
    "endpoints.csv",
    "materials.csv",
    "review_ledger.csv",
    "artifacts/decoding-ledger.csv",
    "artifacts/app/package-inventory.csv",
    "artifacts/source-map.csv",
    "artifacts/app/package/hardening-review.json",
    "artifacts/app/auth/platform-login-review.json",
    "artifacts/app/auth/session-lifecycle-review.json",
    "artifacts/app/auth/signature-replay-review.json",
    "artifacts/app/reconciliation/static-dynamic-endpoints.csv",
    "artifacts/app/storage/local-data-review.json",
    "artifacts/app/crypto/secret-review.json",
    "artifacts/app/webview/webview-origin-inventory.csv",
    "artifacts/app/webview/bridge-method-inventory.csv",
    "artifacts/app/webview/deep-link-review-queue.csv",
    "artifacts/app/ipc/component-inventory.csv",
    "artifacts/app/ipc/deeplink-review-queue.csv",
    "artifacts/app/cloud/cloud-function-review.json",
    "artifacts/app/cloud/object-storage-review.json",
    "artifacts/app/cloud/third-party-boundary.csv",
    "evidence/index.csv",
    "notes/target-model.md",
    "notes/operator_tasks.md",
    "notes/safety-controls.md",
    "reports/final-report.md",
)
SKELETON_DIRS = (
    "artifacts/app/unpacked",
    "evidence/raw",
    "evidence/redacted",
    "logs",
    "materials/original",
    "materials/working",
    "notes/phase-history",
    "sessions",
)

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


def load_init_module():
    spec = importlib.util.spec_from_file_location("app_init_engagement_test", INIT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_routing_module():
    spec = importlib.util.spec_from_file_location("app_routing_for_init_test", ROUTING_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def init_mod():
    return load_init_module()


def run_init(init_mod, tmp_path: Path, *extra: str) -> Path:
    out = tmp_path / "engagement"
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "com.example.smoke", "--output", str(out), *extra]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 0, f"init failed with exit code {code}"
    return out


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def phase_rows(root: Path) -> list[dict]:
    return load_json(root / "phase_status.app.json")["phases"]


def test_workspace_skeleton_complete(init_mod, tmp_path):
    root = run_init(init_mod, tmp_path)
    for relative in SKELETON_FILES:
        assert (root / relative).is_file(), f"missing skeleton file: {relative}"
    for relative in SKELETON_DIRS:
        assert (root / relative).is_dir(), f"missing skeleton dir: {relative}"
    for name in ("phase_status.json", "phase_status.miniapp.json"):
        assert not (root / name).exists(), f"init must not create foreign cursor {name}"


def test_cursor_stream_and_file_name(init_mod, tmp_path):
    root = run_init(init_mod, tmp_path)
    payload = load_json(root / "phase_status.app.json")
    assert payload["stream"] == "app"
    assert payload["status_file"] == "phase_status.app.json"
    assert payload["current_phase"] == "authorization"
    assert payload["next_phase"] == "identity"
    assert payload["last_completed_phase"] == ""


def test_seed_matches_appendix_b(init_mod, tmp_path):
    root = run_init(init_mod, tmp_path)
    rows = phase_rows(root)
    names = tuple(row["phase"] for row in rows)
    assert names == APPENDIX_B_PHASES
    assert len(rows) == 33
    substatus_phases = [name for name in names if name in APPENDIX_B_SUBSTATUSES]
    assert len(substatus_phases) == 12
    for row in rows:
        phase = row["phase"]
        assert row["required"] is True
        assert row["artifacts"] == APPENDIX_B_ARTIFACTS[phase], f"artifacts drift: {phase}"
        if phase in APPENDIX_B_SUBSTATUSES:
            assert tuple(row["substatuses"]) == APPENDIX_B_SUBSTATUSES[phase], phase
            assert set(row["substatuses"].values()) == {""}
        else:
            assert "substatuses" not in row, phase


def test_authorization_seeded_complete_and_identity_auto_complete(init_mod, tmp_path):
    root = run_init(
        init_mod, tmp_path, "--platform", "android", "--name", "Smoke",
        "--operator", "TestOp",
    )
    rows = {row["phase"]: row for row in phase_rows(root)}
    assert rows["authorization"]["status"] == "complete"
    assert rows["authorization"]["updated_at"] != ""
    assert rows["identity"]["status"] == "complete"
    assert rows["platform_identification"]["status"] == "complete"
    app_json = load_json(root / "app.json")
    assert app_json["identity_status"] == "confirmed"
    assert app_json["package_name"] == "com.example.smoke"


def test_identity_stays_pending_without_fields(init_mod, tmp_path):
    root = run_init(init_mod, tmp_path)
    rows = {row["phase"]: row for row in phase_rows(root)}
    assert rows["identity"]["status"] == "pending"
    # 输入只是包名：平台未识别（auto 且无包文件）→ platform_identification 也 pending。
    assert rows["platform_identification"]["status"] == "pending"
    assert load_json(root / "app.json")["identity_status"] == "pending"


def test_platform_autodetected_from_package_file(init_mod, tmp_path):
    apk = tmp_path / "demo.apk"
    apk.write_bytes(b"PK\x03\x04 placeholder apk bytes")
    out = tmp_path / "engagement"
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), str(apk), "--output", str(out), "--package", "com.example.demo"]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 0
    payload = load_json(out / "phase_status.app.json")
    rows = {row["phase"]: row for row in payload["phases"]}
    assert rows["platform_identification"]["status"] == "complete"
    assert load_json(out / "app.json")["platform"] == "android"
    with (out / "materials.csv").open(encoding="utf-8-sig", newline="") as handle:
        material_rows = list(csv.DictReader(handle))
    assert len(material_rows) == 1
    assert material_rows[0]["material_type"] == "package"
    assert material_rows[0]["sha256"]
    assert material_rows[0]["platform"] == "android"


def test_classify_input_eight_types(init_mod, tmp_path):
    apk = tmp_path / "a.apk"
    apk.write_bytes(b"x")
    ipa = tmp_path / "b.ipa"
    ipa.write_bytes(b"y")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "split.apk").write_bytes(b"z")
    unpacked = tmp_path / "unpacked"
    unpacked.mkdir()
    (unpacked / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    traffic = tmp_path / "cap.har"
    traffic.write_text('{"log": {"entries": [{"request": {}}]}}', encoding="utf-8")
    plain = tmp_path / "note.txt"
    plain.write_text("nothing interesting", encoding="utf-8")
    assert init_mod.classify_input(str(apk))[0] == "package"
    assert init_mod.classify_input(str(ipa))[0:2] == ("package", "ios")
    assert init_mod.classify_input(str(cache))[0] == "package_cache"
    assert init_mod.classify_input(str(unpacked))[0:2] == ("unpacked_source", "android")
    assert init_mod.classify_input(str(traffic))[0] == "traffic_export"
    assert init_mod.classify_input(str(plain))[0] == "file"
    assert init_mod.classify_input("com.example.app")[0] == "identifier"
    assert init_mod.classify_input("https://play.google.com/store/apps/details?id=com.example.app")[0] == "entry_url"
    assert init_mod.classify_input("Some App Name")[0] == "name"
    seen = {
        init_mod.classify_input(value)[0]
        for value in (
            str(apk), str(ipa), str(cache), str(unpacked), str(traffic), str(plain),
            "com.example.app", "https://play.google.com/store/apps?id=x", "Some App Name",
        )
    }
    assert seen == set(init_mod.INPUT_TYPES)


def test_zero_network_assertions(init_mod, tmp_path):
    root = run_init(init_mod, tmp_path)
    engagement = load_json(root / "engagement.json")
    assert engagement["network_accessed_by_initializer"] is False
    source = INIT_SCRIPT.read_text(encoding="utf-8")
    for token in NETWORK_IMPORT_TOKENS:
        assert token not in source, f"network-capable import present: {token}"


def test_resume_input_hash_mismatch_rejected(init_mod, tmp_path, capsys):
    root = run_init(init_mod, tmp_path)
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "com.other.app", "--output", str(root), "--resume"]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 3
    assert "does not match" in capsys.readouterr().err


def test_resume_same_input_reseeds_missing_skeleton(init_mod, tmp_path):
    root = run_init(init_mod, tmp_path)
    (root / "artifacts" / "app" / "crypto" / "secret-review.json").unlink()
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "com.example.smoke", "--output", str(root), "--resume"]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 0
    reseeded = load_json(root / "artifacts" / "app" / "crypto" / "secret-review.json")
    assert reseeded["phase"] == "crypto_and_secret_handling"
    assert set(reseeded["substatuses"]) == set(APPENDIX_B_SUBSTATUSES["crypto_and_secret_handling"])


def test_resume_refuses_workspace_without_app_cursor(init_mod, tmp_path, capsys):
    # xcx 工作区（无 app 游标）：--resume 必须 fail-closed，不得回落 wz/xcx 游标。
    xcx_ws = tmp_path / "xcx-engagement"
    xcx_ws.mkdir()
    (xcx_ws / "phase_status.miniapp.json").write_text(
        json.dumps({"stream": "miniapp_xcx", "phases": []}), encoding="utf-8"
    )
    (xcx_ws / "engagement.json").write_text(
        json.dumps({"input_sha256": hashlib.sha256(b"com.example.smoke").hexdigest()}),
        encoding="utf-8",
    )
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "com.example.smoke", "--output", str(xcx_ws), "--resume"]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 3
    assert "APP_PHASE_STATUS_MISSING" in capsys.readouterr().err


def test_review_skeletons_carry_branches(init_mod, tmp_path):
    root = run_init(init_mod, tmp_path)
    for phase, (rel_path, contract) in init_mod.REVIEW_JSON_ARTIFACTS.items():
        payload = load_json(root / rel_path)
        assert payload["phase"] == phase
        assert payload["contract"] == contract
        assert tuple(payload["substatuses"]) == APPENDIX_B_SUBSTATUSES[phase]
        assert payload["rows"] == [] and payload["summaries"] == []
        assert set(payload["substatuses"].values()) == {""}


def test_scope_root_seeds_hosts_and_scope(init_mod, tmp_path):
    root = run_init(init_mod, tmp_path, "--scope-root", "example.com")
    with (root / "hosts.csv").open(encoding="utf-8-sig", newline="") as handle:
        hosts = list(csv.DictReader(handle))
    assert [row["host"] for row in hosts] == ["example.com"]
    assert hosts[0]["domain_authorized"] == "true"
    with (root / "scope.csv").open(encoding="utf-8-sig", newline="") as handle:
        scope = list(csv.DictReader(handle))
    assert [row["asset"] for row in scope] == ["example.com"]
    assert scope[0]["scope_state"] == "in_scope"


def test_market_url_does_not_auto_authorize_platform_domain(init_mod, tmp_path):
    # 市场链接输入不得把平台/第三方域自动标为 in_scope（只认显式 --scope-root）。
    root = run_init(init_mod, tmp_path, "--name", "Smoke")
    with (root / "hosts.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == []
    with (root / "scope.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == []


def test_same_asset_parallel_guard(init_mod, tmp_path, capsys):
    first = tmp_path / "ws-a"
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "com.example.dupe", "--output", str(first), "--platform", "android"]
    try:
        assert init_mod.main() == 0
    finally:
        sys.argv = old_argv
    second = tmp_path / "ws-b"
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "com.example.dupe", "--output", str(second)]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 4
    err = capsys.readouterr().err
    assert "禁止平行新建" in err
    # --allow-parallel 放行。
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "com.example.dupe", "--output", str(second), "--allow-parallel"]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 0
