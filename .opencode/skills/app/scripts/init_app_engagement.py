#!/usr/bin/env python3
"""Create or resume a portable mobile-app assessment workspace without network access.

APP 流（方案 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §7.2，批次 B2/W17）：
零网络初始化器——只读输入、算哈希、落 workspace 骨架与 phase_status.app.json 种子
（附录 B，33 phase + 12 组 substatuses，stream=app）。绝不发任何请求，绝不读写
runs/ 与 auth_sessions.local.json，也绝不触碰 wz/xcx 的游标文件。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from src.authorized_assessment.scope import classify_scope_entry, normalize_scope_host, registrable_parent

try:
    from phase_status_routing import APP_PHASE_STATUS_FILENAME, APP_STREAM, resolve_phase_status, route_metadata
except ImportError:
    import importlib.util

    _ROUTING_PATH = Path(__file__).with_name("phase_status_routing.py")
    _ROUTING_SPEC = importlib.util.spec_from_file_location("app_phase_status_routing", _ROUTING_PATH)
    if _ROUTING_SPEC is None or _ROUTING_SPEC.loader is None:
        raise
    _ROUTING_MODULE = importlib.util.module_from_spec(_ROUTING_SPEC)
    sys.modules[_ROUTING_SPEC.name] = _ROUTING_MODULE
    _ROUTING_SPEC.loader.exec_module(_ROUTING_MODULE)
    APP_PHASE_STATUS_FILENAME = _ROUTING_MODULE.APP_PHASE_STATUS_FILENAME
    APP_STREAM = _ROUTING_MODULE.APP_STREAM
    resolve_phase_status = _ROUTING_MODULE.resolve_phase_status
    route_metadata = _ROUTING_MODULE.route_metadata


os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PLATFORMS = ("auto", "android", "ios", "dual", "other")
PACKAGE_SUFFIXES = {".apk", ".xapk", ".apks", ".aab", ".ipa"}
TRAFFIC_SNIPPET_SUFFIXES = {".xml", ".txt", ".json", ".har"}
# Android/iOS 包名（反域名，≥2 个点段）；市场链接走 entry_url，普通名称走 name。
ANDROID_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*){2,}$")

# classify_input 识别的 8 类输入（方案 §7.2）：包文件 / 含包目录（设备缓存、split）
# / 已解包目录 / 流量导出 / 兜底本地文件或目录 / 包名标识 / URL / 纯名称。
INPUT_TYPES = (
    "package",
    "package_cache",
    "unpacked_source",
    "traffic_export",
    "file",
    "identifier",
    "entry_url",
    "name",
)

# 33 阶段（方案 §4 / 附录 B，顺序即种子顺序）。与 wz/xcx 的阶段集相互独立。
PHASES = (
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

# 12 组复核分支（coverage_substatus 种子键，值空串=未记录，完成时审计强制）。常量与
# contracts/app_*.json（B4 落地）同源，漂移由后续 test_app_contract_sync 锁定。
HARDENING_REVIEW_BRANCHES = {
    "package_integrity_hardening_review": (
        "package_version_inventory",
        "signing_integrity",
        "hardening_obfuscation_markers",
        "debug_switches",
        "debug_info_exposure",
        "update_endpoint_environment",
        "trusted_update_config",
    ),
}
AUTH_REVIEW_BRANCHES = {
    "platform_login_exchange": (
        "oauth_code_one_time",
        "oauth_code_expiry",
        "one_click_login_device_binding",
        "access_token_custody",
        "uid_authorization_basis",
    ),
    "session_token_lifecycle": (
        "token_rotation",
        "token_revocation_logout",
        "multi_device_login",
        "stale_token_new_api",
        "device_user_tenant_binding",
    ),
    "signature_replay": (
        "nonce_timestamp",
        "signature_canonicalization",
        "replay_window",
        "binding_scope",
    ),
}
STORAGE_PACKAGE_REVIEW_BRANCHES = {
    "local_data_exposure": (
        "token_persistence",
        "logout_cleanup",
        "local_cache_database",
        "logs_clipboard_screenshots",
        "temp_files",
    ),
    "crypto_and_secret_handling": (
        "hardcoded_secrets",
        "custom_crypto",
        "weak_random_key_derivation",
        "debug_config_env_keys",
    ),
}
RECONCILIATION_REVIEW_BRANCHES = {
    "static_dynamic_reconciliation": (
        "static_endpoint_base",
        "dynamic_endpoint_base",
        "match_status_classification",
        "hidden_flow_identification",
        "stale_entry_disposition",
    ),
}
WEBVIEW_REVIEW_BRANCHES = {
    "webview_bridge_links": (
        "webview_allowed_domains",
        "postmessage_origin",
        "cookie_token_sharing_boundary",
        "bridge_method_exposure",
        "custom_scheme",
        "deep_link_sensitive_params",
        "external_app_browser_jump",
    ),
}
IPC_REVIEW_BRANCHES = {
    "ipc_component_boundary": (
        "exported_activity",
        "exported_service",
        "exported_receiver",
        "exported_provider",
        "custom_scheme_deeplink",
        "universal_link",
        "ios_extension_boundary",
    ),
}
CLOUD_REVIEW_BRANCHES = {
    "cloud_function_testing": (
        "anonymous_invocation",
        "function_parameter_role_validation",
        "cloud_env_id_mixing",
    ),
    "cloud_storage_acl_testing": (
        "cloud_database_rules",
        "object_storage_acl",
        "signed_url_binding",
    ),
    "third_party_sdk_platform_boundary": (
        "third_party_service_boundary",
        "platform_shared_asset_attribution",
    ),
}
PHASE_BRANCHES: dict[str, tuple[str, ...]] = {
    **HARDENING_REVIEW_BRANCHES,
    **AUTH_REVIEW_BRANCHES,
    **STORAGE_PACKAGE_REVIEW_BRANCHES,
    **RECONCILIATION_REVIEW_BRANCHES,
    **WEBVIEW_REVIEW_BRANCHES,
    **IPC_REVIEW_BRANCHES,
    **CLOUD_REVIEW_BRANCHES,
}

# review JSON 产物（12-key 骨架，同 xcx 引擎形状）；契约名与 B4 的 contracts/app_*.json 对应。
REVIEW_JSON_ARTIFACTS = {
    "package_integrity_hardening_review": (
        "artifacts/app/package/hardening-review.json",
        "app_storage_package_schema",
    ),
    "platform_login_exchange": ("artifacts/app/auth/platform-login-review.json", "app_auth_schema"),
    "session_token_lifecycle": ("artifacts/app/auth/session-lifecycle-review.json", "app_auth_schema"),
    "signature_replay": ("artifacts/app/auth/signature-replay-review.json", "app_auth_schema"),
    "local_data_exposure": ("artifacts/app/storage/local-data-review.json", "app_storage_package_schema"),
    "crypto_and_secret_handling": ("artifacts/app/crypto/secret-review.json", "app_storage_package_schema"),
    "cloud_function_testing": ("artifacts/app/cloud/cloud-function-review.json", "app_cloud_schema"),
    "cloud_storage_acl_testing": ("artifacts/app/cloud/object-storage-review.json", "app_cloud_schema"),
}
REVIEW_SKELETON_FIELDS = {
    "row_fields": (
        "row_id", "branch", "status", "evidence_kinds", "source", "evidence_ref",
        "precondition", "reason",
    ),
    "summary_fields": (
        "branch", "branch_status", "applicability_counts", "status_counts",
        "tested_count", "reason", "source", "precondition",
    ),
}

# 清单 CSV 产物（仅种表头；tested 判据由各 phase 产出真实行）。
RECONCILIATION_CSV_FIELDS = (
    "endpoint_id", "host", "method", "path", "source_material",
    "static_evidence_ref", "dynamic_evidence_ref", "status", "reason", "notes",
)
RECONCILIATION_ENDPOINT_STATES = (
    "static_only",
    "dynamic_only",
    "both_seen",
    "feature_gated",
    "stale",
    "version_specific",
    "third_party",
    "platform_shared",
    "unreachable",
    "needs_manual_validation",
)
WEBVIEW_ORIGIN_CSV_FIELDS = (
    "row_id", "webview_origin", "business_purpose", "source_material",
    "source_location", "postmessage_target_origin", "cookie_token_shared",
    "boundary_status", "evidence_ref", "reason", "notes",
)
WEBVIEW_COOKIE_TOKEN_SHARED_VALUES = (
    "none", "session_cookie", "auth_token", "both", "unknown",
)
WEBVIEW_BRIDGE_CSV_FIELDS = (
    "row_id", "method_name", "exposed_scope", "capability", "source_material",
    "boundary_status", "evidence_ref", "reason", "notes",
)
WEBVIEW_DEEP_LINK_CSV_FIELDS = (
    "row_id", "deep_link_pattern", "scheme_type", "sensitive_params", "jump_target",
    "boundary_status", "evidence_ref", "reason", "notes",
)
# ipc_component_boundary（App 特有，方案 §4 第 27 行）：组件清单 + deeplink 复核队列两 CSV。
IPC_COMPONENT_CSV_FIELDS = (
    "row_id", "component_kind", "component_name", "exported", "permission",
    "intent_actions", "scheme", "authority", "source_material", "source_location",
    "boundary_status", "evidence_ref", "reason", "notes",
)
IPC_COMPONENT_KINDS = (
    "activity", "service", "receiver", "provider", "ios_extension", "other",
)
IPC_DEEPLINK_CSV_FIELDS = (
    "row_id", "deep_link_pattern", "scheme_type", "sensitive_params", "component_ref",
    "jump_target", "boundary_status", "evidence_ref", "reason", "notes",
)
THIRD_PARTY_CSV_FIELDS = (
    "row_id", "service_name", "service_type", "host", "attribution",
    "boundary_status", "evidence_ref", "reason", "notes",
)
REVIEW_CSV_ARTIFACTS = {
    "artifacts/app/reconciliation/static-dynamic-endpoints.csv": RECONCILIATION_CSV_FIELDS,
    "artifacts/app/webview/webview-origin-inventory.csv": WEBVIEW_ORIGIN_CSV_FIELDS,
    "artifacts/app/webview/bridge-method-inventory.csv": WEBVIEW_BRIDGE_CSV_FIELDS,
    "artifacts/app/webview/deep-link-review-queue.csv": WEBVIEW_DEEP_LINK_CSV_FIELDS,
    "artifacts/app/ipc/component-inventory.csv": IPC_COMPONENT_CSV_FIELDS,
    "artifacts/app/ipc/deeplink-review-queue.csv": IPC_DEEPLINK_CSV_FIELDS,
    "artifacts/app/cloud/third-party-boundary.csv": THIRD_PARTY_CSV_FIELDS,
}

# 附录 B：各 phase 的产物契约（种子即写入，与完成状态无关——artifacts 列表达
# "该阶段完成时应存在什么"，status 表达"是否已完成"）。
PHASE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "authorization": ("engagement.json",),
    "identity": ("app.json",),
    "platform_identification": ("app.json",),
    "material_acquisition": (),
    "initial_decoding": ("artifacts/decoding-ledger.csv",),
    "preflight": (),
    "package_inventory": ("artifacts/app/package-inventory.csv",),
    "package_unpack_decompile": ("artifacts/app/unpacked",),
    "source_reconstruction": ("artifacts/source-map.csv",),
    "package_integrity_hardening_review": ("artifacts/app/package/hardening-review.json",),
    "static_analysis": (),
    "endpoint_inventory": ("endpoints.csv",),
    "host_classification": ("hosts.csv",),
    "dynamic_setup": (),
    "dynamic_mapping": (),
    "static_dynamic_reconciliation": ("artifacts/app/reconciliation/static-dynamic-endpoints.csv",),
    "platform_login_exchange": ("artifacts/app/auth/platform-login-review.json",),
    "session_token_lifecycle": ("artifacts/app/auth/session-lifecycle-review.json",),
    "signature_replay": ("artifacts/app/auth/signature-replay-review.json",),
    "backend_web_api_testing": (),
    "access_control_testing": (),
    "input_file_testing": (),
    "business_logic_testing": (),
    "local_data_exposure": ("artifacts/app/storage/local-data-review.json",),
    "crypto_and_secret_handling": ("artifacts/app/crypto/secret-review.json",),
    "webview_bridge_links": (
        "artifacts/app/webview/webview-origin-inventory.csv",
        "artifacts/app/webview/bridge-method-inventory.csv",
        "artifacts/app/webview/deep-link-review-queue.csv",
    ),
    "ipc_component_boundary": (
        "artifacts/app/ipc/component-inventory.csv",
        "artifacts/app/ipc/deeplink-review-queue.csv",
    ),
    "cloud_function_testing": ("artifacts/app/cloud/cloud-function-review.json",),
    "cloud_storage_acl_testing": ("artifacts/app/cloud/object-storage-review.json",),
    "third_party_sdk_platform_boundary": ("artifacts/app/cloud/third-party-boundary.csv",),
    "candidate_validation": (),
    "reporting": ("reports/final-report.md",),
    "cleanup": (),
}

MATERIAL_FIELDS = (
    "material_id", "active", "material_type", "platform", "path_or_value", "size",
    "sha256", "provenance", "version", "analysis_status", "derived_from", "notes",
)

HOST_FIELDS = (
    "host_id", "active", "host", "service_type", "scope_state", "owner",
    "source_material", "source_location", "ownership_rationale", "permitted_actions",
    "confirmed_at", "matched_scope_anchor", "scope_match_kind", "domain_authorized", "scope_mode", "notes",
)

ENDPOINT_FIELDS = (
    "endpoint_id", "active", "host", "method", "path", "parameters", "content_type",
    "auth_required", "roles", "state_changing", "client_route", "source_material",
    "source_location", "test_status", "notes",
)

DECODING_FIELDS = (
    "decoding_id", "material_id", "input_type", "input_ref", "input_sha256", "tool",
    "tool_version", "mode", "status", "output_path", "recovered_clues", "notes",
)

LEDGER_FIELDS = (
    "item_id", "active", "priority", "category", "platform", "asset", "client_route",
    "endpoint", "parameter", "role", "candidate_type", "status", "confidence", "summary",
    "source", "validation_plan", "validation_result", "evidence_ref", "finding_id", "owner",
    "updated_at",
)

# scope.csv 与 wz 同构（域级授权资产登记）；APP 的 hosts.csv 语义与 xcx 一致。
SCOPE_FIELDS = (
    "asset_id", "asset", "asset_type", "scope_state", "source", "ownership_rationale",
    "permitted_actions", "confirmed_at", "matched_scope_anchor", "scope_match_kind",
    "domain_authorized", "scope_mode", "notes",
)

# package-inventory（§5.8 路径在 artifacts/app/ 下）：hardening_signal 列承载加固厂商
# 候选（附录 F 特征表命中只记 signal，不构成结论）。
PACKAGE_INVENTORY_FIELDS = (
    "package_id", "material_id", "package_path", "package_type", "subpackage",
    "size", "sha256", "hardening_signal", "extractor", "extractor_version",
    "extraction_status", "output_dir", "notes",
)

SOURCE_MAP_FIELDS = (
    "source_id", "material_id", "package_id", "source_path", "source_type",
    "recovered_from", "sha256", "parse_status", "notes",
)

EVIDENCE_INDEX_FIELDS = (
    "evidence_id", "finding_id", "captured_at", "sha256", "sensitivity",
    "raw_path", "redacted_path", "retention", "notes",
)

WORKSPACE_DIRECTORIES = (
    "artifacts",
    "artifacts/app/unpacked",
    "artifacts/app/package",
    "artifacts/app/auth",
    "artifacts/app/reconciliation",
    "artifacts/app/storage",
    "artifacts/app/crypto",
    "artifacts/app/webview",
    "artifacts/app/ipc",
    "artifacts/app/cloud",
    "evidence/raw",
    "evidence/redacted",
    "logs",
    "materials/original",
    "materials/working",
    "notes",
    "notes/phase-history",
    "reports",
    "sessions",
)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_manifest_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        try:
            relative = item.relative_to(path).as_posix()
            size = item.stat().st_size
        except OSError:
            continue
        digest.update(f"{relative}\0{size}\0{sha256_file(item)}\n".encode("utf-8", errors="replace"))
    return digest.hexdigest()


def _scan_directory(path: Path) -> tuple[list[str], bool, bool]:
    """单次遍历收集：包文件后缀、Android 源码标记、iOS 源码标记。"""
    package_suffixes: list[str] = []
    android_marker = False
    ios_marker = False
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        suffix = item.suffix.lower()
        name = item.name
        if suffix in PACKAGE_SUFFIXES:
            package_suffixes.append(suffix)
        elif name in {"AndroidManifest.xml", "apktool.yml", "resources.arsc", "Info.plist"}:
            android_marker = android_marker or name != "Info.plist"
            ios_marker = ios_marker or name == "Info.plist"
        elif suffix in {".dex", ".smali"}:
            android_marker = True
    return package_suffixes, android_marker, ios_marker


def _platform_from_package_suffixes(suffixes: Iterable[str]) -> str:
    platforms = {detect_platform_from_suffix(suffix) for suffix in suffixes}
    if {"android", "ios"} <= platforms:
        return "dual"
    if "android" in platforms:
        return "android"
    if "ios" in platforms:
        return "ios"
    return "unknown"


def detect_platform_from_suffix(suffix: str) -> str:
    return "ios" if suffix == ".ipa" else "android"


def classify_path(path: Path) -> tuple[str, str]:
    """把本地路径分到 8 类输入之一（目录类三类 + 文件类两类）。"""
    if path.is_dir():
        package_suffixes, android_marker, ios_marker = _scan_directory(path)
        if package_suffixes and not (android_marker or ios_marker):
            return "package_cache", _platform_from_package_suffixes(package_suffixes)
        if android_marker or ios_marker:
            if android_marker and ios_marker:
                return "unpacked_source", "dual"
            return "unpacked_source", "android" if android_marker else "ios"
        return "file", "unknown"
    suffix = path.suffix.lower()
    if suffix in PACKAGE_SUFFIXES:
        return "package", detect_platform_from_suffix(suffix)
    if suffix == ".har":
        return "traffic_export", "unknown"
    if suffix in TRAFFIC_SNIPPET_SUFFIXES:
        sample = path.read_text(encoding="utf-8-sig", errors="replace")[:65536].lower()
        if any(token in sample for token in ("http/1.", '"request"', "<request", "\thttps://", "\thttp://")):
            return "traffic_export", "unknown"
        return "file", "unknown"
    return "file", "unknown"


def classify_input(value: str) -> tuple[str, str, dict[str, str]]:
    """按存在性/后缀/内容识别 8 类输入；包文件与目录算 sha256。"""
    candidate = Path(value)
    if candidate.exists():
        material_type, platform = classify_path(candidate)
        size = str(candidate.stat().st_size) if candidate.is_file() else ""
        digest = sha256_file(candidate) if candidate.is_file() else directory_manifest_sha256(candidate)
        return material_type, platform, {
            "path_or_value": str(candidate.resolve()), "size": size, "sha256": digest,
        }
    stripped = value.strip()
    if ANDROID_PACKAGE_RE.fullmatch(stripped):
        return "identifier", "unknown", {"identifier": stripped, "path_or_value": stripped}
    if "://" in stripped:
        parsed = urlsplit(stripped)
        if parsed.scheme and parsed.netloc:
            return "entry_url", "unknown", {"path_or_value": stripped}
    return "name", "unknown", {"name": stripped, "path_or_value": stripped}


def write_csv_if_missing(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, str]]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_text_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def review_json_skeleton(phase: str, contract: str) -> dict:
    """12-key review JSON 骨架（同 xcx auth/storage/cloud 引擎形状）。"""
    return {
        "schema_version": "1.0",
        "contract": contract,
        "phase": phase,
        "observation_schema_version": "1.0",
        "row_fields": list(REVIEW_SKELETON_FIELDS["row_fields"]),
        "summary_fields": list(REVIEW_SKELETON_FIELDS["summary_fields"]),
        "substatuses": {branch: "" for branch in PHASE_BRANCHES[phase]},
        "rows": [],
        "summaries": [],
        "violations": [],
        "authorization_basis": "",
        "updated_at": "",
    }


def append_scope_root_rows(root: Path, scope_root: str, *, owner: str, authorization_ref: str, created: str) -> None:
    """幂等登记 --scope-root 显式授权根域：hosts.csv 锚点行（scope.csv 行由调用方种子）。"""
    hosts_path = root / "hosts.csv"
    if not hosts_path.is_file():
        return
    with hosts_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        existing_fields = list(reader.fieldnames or HOST_FIELDS)
    if any(normalize_scope_host(row.get("host")) == scope_root for row in rows):
        return
    fields = list(dict.fromkeys([*existing_fields, *HOST_FIELDS]))
    if fields != existing_fields:
        with hosts_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    row = {field: "" for field in HOST_FIELDS}
    row.update({
        "host_id": hashlib.sha256(scope_root.encode("utf-8")).hexdigest()[:16],
        "active": "true",
        "host": scope_root,
        "service_type": "backend",
        "scope_state": "in_scope",
        "owner": owner,
        "source_material": "explicit_scope_root",
        "source_location": "--scope-root",
        "ownership_rationale": authorization_ref,
        "permitted_actions": "read_only",
        "confirmed_at": created,
        "matched_scope_anchor": scope_root,
        "scope_match_kind": "domain_suffix",
        "domain_authorized": "true",
        "scope_mode": "explicit_domain",
        "notes": "域级授权根域；子域自动继承 scope，仍受 active_testing 授权门约束",
    })
    with hosts_path.open("a", encoding="utf-8-sig", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore").writerow(row)


def find_same_asset_engagements(output_root: Path, *, package_name: str, material_sha256: str, input_host: str) -> list[Path]:
    """同资产 APP 工作区发现：扫同级目录的 app.json（包名）、materials.csv（包哈希）
    与 scope.csv（host/注册父域覆盖）。命中即提示 --resume 续用，防平行新建丢台账。"""
    hits: list[Path] = []
    base = output_root.parent
    if not base.is_dir():
        return hits
    parent = registrable_parent(input_host) if input_host else ""
    wanted_package = package_name.strip().lower()
    for sibling in sorted(base.iterdir()):
        if sibling == output_root or not sibling.is_dir():
            continue
        app_json = sibling / "app.json"
        if app_json.is_file() and wanted_package:
            try:
                payload = json.loads(app_json.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if str(payload.get("package_name", "")).strip().lower() == wanted_package:
                hits.append(sibling)
                continue
        materials = sibling / "materials.csv"
        if materials.is_file() and material_sha256:
            try:
                with materials.open(encoding="utf-8-sig", newline="") as handle:
                    if any((row.get("sha256") or "").strip() == material_sha256 for row in csv.DictReader(handle)):
                        hits.append(sibling)
                        continue
            except OSError:
                pass
        scope_csv = sibling / "scope.csv"
        if scope_csv.is_file() and input_host:
            try:
                with scope_csv.open(encoding="utf-8-sig", newline="") as handle:
                    for row in csv.DictReader(handle):
                        asset = (row.get("asset") or "").strip().lower().lstrip("*.")
                        if not asset:
                            continue
                        if input_host == asset or input_host.endswith("." + asset) or (parent and asset == parent):
                            hits.append(sibling)
                            break
            except OSError:
                continue
    return hits


def _ensure_substatus_keys(phase_path: Path) -> None:
    """resume 补种：既有 app 游标行缺 substatuses 键时补空串（幂等；不动 status/reason）。"""
    try:
        payload = json.loads(phase_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("phases"), list):
        return
    changed = False
    for row in payload["phases"]:
        if not isinstance(row, dict):
            continue
        phase = str(row.get("phase", "")).strip()
        if phase not in PHASE_BRANCHES:
            continue
        substatuses = row.get("substatuses")
        if not isinstance(substatuses, dict):
            row["substatuses"] = {name: "" for name in PHASE_BRANCHES[phase]}
            changed = True
            continue
        for name in PHASE_BRANCHES[phase]:
            if name not in substatuses:
                substatuses[name] = ""
                changed = True
    if not changed:
        return
    phase_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a mobile-app assessment workspace (zero network).")
    parser.add_argument("input", help="APK/IPA/XAPK file, package name, market link, unpacked dir, traffic export, or name.")
    parser.add_argument("--output", required=True, help="Engagement workspace directory.")
    parser.add_argument("--platform", choices=PLATFORMS, default="auto")
    parser.add_argument("--name", default="", help="Confirmed or candidate app name.")
    parser.add_argument("--package", default="", help="Package name / bundle identifier (com.example.app).")
    parser.add_argument("--operator", default="", help="Operating entity.")
    parser.add_argument("--version", default="", help="Observed app version.")
    parser.add_argument(
        "--authorization-ref",
        default="",
        help="Optional authorization evidence note; user-supplied input is accepted by default.",
    )
    parser.add_argument("--window", default="", help="Authorized testing window.")
    parser.add_argument("--rules", default="", help="Rules-of-engagement reference.")
    parser.add_argument("--rate", default="", help="Approved request-rate note.")
    parser.add_argument("--scope-root", default="", help="Explicit authorized domain root for automatic child-host inheritance")
    parser.add_argument("--resume", action="store_true", help="Resume the same workspace.")
    parser.add_argument(
        "--allow-parallel",
        action="store_true",
        help="Allow creating a parallel workspace for the same asset (default: refuse and suggest --resume).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        input_type, detected_platform, details = classify_input(args.input)
    except OSError as exc:
        print(f"ERROR: Cannot inspect input: {exc}", file=sys.stderr)
        return 2
    if not details.get("path_or_value", "").strip():
        print("ERROR: Input is empty.", file=sys.stderr)
        return 2

    if args.platform != "auto":
        platform = args.platform
        platform_identified = True
    else:
        platform = detected_platform if detected_platform != "unknown" else "other"
        platform_identified = detected_platform != "unknown"
    # 域级授权锚点只认显式 --scope-root：app 输入常是应用市场链接（play.google.com
    # 等平台/第三方域），从输入 URL 自动推导锚点会把第三方域误标 in_scope。未给
    # --scope-root 时 hosts/scope 全部留空，归属确认交给 host_classification 阶段。
    if args.scope_root:
        scope_root = normalize_scope_host(args.scope_root)
        if not scope_root or classify_scope_entry(scope_root, domain_authorized=True).scope_state != "in_scope":
            print("ERROR: --scope-root must be a valid registrable domain.", file=sys.stderr)
            return 2
    else:
        scope_root = ""
    inferred_name = details.get("name", "")
    inferred_package = details.get("identifier", "")
    name = args.name.strip() or inferred_name
    package_name = args.package.strip() or inferred_package
    operator = args.operator.strip()
    identity_confirmed = bool(name and package_name and operator and platform_identified)
    root = Path(args.output).resolve()
    engagement_path = root / "engagement.json"
    if root.exists() and not args.resume:
        print(f"ERROR: Output already exists; use --resume for the same engagement: {root}", file=sys.stderr)
        return 3
    if args.resume and engagement_path.is_file():
        existing = json.loads(engagement_path.read_text(encoding="utf-8-sig"))
        old_hash = existing.get("input_sha256")
        new_hash = hashlib.sha256(args.input.encode("utf-8")).hexdigest()
        if old_hash and old_hash != new_hash:
            print("ERROR: Resume input does not match the existing engagement.", file=sys.stderr)
            return 3
    if not args.resume:
        input_host_for_assets = normalize_scope_host(urlsplit(details.get("path_or_value", "")).hostname or "")
        prior = find_same_asset_engagements(
            root,
            package_name=package_name,
            material_sha256=details.get("sha256", ""),
            input_host=input_host_for_assets,
        )
        if prior and not args.allow_parallel:
            print("ERROR: 同一资产已有 APP 工作区，禁止平行新建（会丢失既有台账/target-model）：", file=sys.stderr)
            for path in prior:
                print(f"  -> {path}", file=sys.stderr)
            print(f"改用：{Path(sys.argv[0]).name} <input> --output {prior[0]} --resume；"
                  f"确需平行工作区加 --allow-parallel", file=sys.stderr)
            return 4

    for relative in WORKSPACE_DIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)

    created = now()
    authorization_ref = args.authorization_ref.strip() or "user_supplied_initial_target"
    if not engagement_path.exists():
        engagement = {
            "workspace_version": 1,
            "created_at": created,
            "input_type": input_type,
            "input_sha256": hashlib.sha256(args.input.encode("utf-8")).hexdigest(),
            "authorization": {
                "status": "target_received",
                "reference": authorization_ref,
                "basis": "user_supplied_initial_target",
                "target_received": True,
                "initial_target_recorded": True,
                "authorization_evidence_recorded": bool(args.authorization_ref.strip()),
                "active_testing_authorized": False,
                "high_risk_action_approved": False,
                "window": args.window.strip(),
                "rules_reference": args.rules.strip(),
                "rate_note": args.rate.strip(),
            },
            "safety_controls": {
                "default_automation": "read_only",
                "write_actions": "operator_approval_required",
                "device_changes": "approval_gated (device_instrumentation)",
                "hardened_shell_unpack": "approval_gated (app_hardened_unpack)",
                "rate_limit": args.rate.strip() or "low_rate_no_disruption_required",
                "service_impact_policy": "stop_on_degradation",
            },
            "network_accessed_by_initializer": False,
        }
        engagement_path.write_text(
            json.dumps(engagement, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    app_json_path = root / "app.json"
    if not app_json_path.exists():
        app_json = {
            "platform": platform,
            "name": name,
            "package_name": package_name,
            "version": args.version.strip(),
            "signing": "",
            "operator": operator,
            "identity_status": "confirmed" if identity_confirmed else "pending",
            "identity_evidence": "",
            "updated_at": created,
        }
        app_json_path.write_text(
            json.dumps(app_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    material_rows: list[dict[str, str]] = []
    if input_type not in {"name", "identifier"}:
        material_identity = "|".join(
            (input_type, details.get("path_or_value", ""), details.get("sha256", ""))
        )
        material_rows.append(
            {
                "material_id": hashlib.sha256(material_identity.encode("utf-8")).hexdigest()[:16],
                "active": "true",
                "material_type": input_type,
                "platform": platform,
                "path_or_value": details.get("path_or_value", ""),
                "size": details.get("size", ""),
                "sha256": details.get("sha256", ""),
                "provenance": "operator_supplied",
                "version": args.version.strip(),
                "analysis_status": "pending",
                "derived_from": "",
                "notes": "",
            }
        )
    write_csv_if_missing(root / "materials.csv", MATERIAL_FIELDS, material_rows)
    write_csv_if_missing(root / "hosts.csv", HOST_FIELDS, [])
    if scope_root:
        append_scope_root_rows(
            root, scope_root, owner=operator, authorization_ref=authorization_ref, created=created
        )
        scope_rows = [
            {
                "asset_id": hashlib.sha256(scope_root.encode("utf-8")).hexdigest()[:16],
                "asset": scope_root,
                "asset_type": "host",
                "scope_state": "in_scope",
                "source": "explicit_scope_root",
                "ownership_rationale": authorization_ref,
                "permitted_actions": "read_only",
                "confirmed_at": created,
                "matched_scope_anchor": scope_root,
                "scope_match_kind": "domain_suffix",
                "domain_authorized": "true",
                "scope_mode": "explicit_domain",
                "notes": "域级授权根域；子域可自动继承 scope，仍受 active_testing 授权门约束",
            }
        ]
    else:
        scope_rows = []
    write_csv_if_missing(root / "scope.csv", SCOPE_FIELDS, scope_rows)
    write_csv_if_missing(root / "endpoints.csv", ENDPOINT_FIELDS, [])
    write_csv_if_missing(root / "artifacts" / "decoding-ledger.csv", DECODING_FIELDS, [])
    write_csv_if_missing(root / "review_ledger.csv", LEDGER_FIELDS, [])
    write_csv_if_missing(
        root / "artifacts" / "app" / "package-inventory.csv",
        PACKAGE_INVENTORY_FIELDS,
        [],
    )
    write_csv_if_missing(
        root / "artifacts" / "source-map.csv",
        SOURCE_MAP_FIELDS,
        [],
    )
    write_csv_if_missing(
        root / "evidence" / "index.csv",
        EVIDENCE_INDEX_FIELDS,
        [],
    )

    phase_route = resolve_phase_status(root, for_write=not args.resume)
    if phase_route.error:
        print(f"ERROR: {phase_route.error}", file=sys.stderr)
        return 3
    phase_path = phase_route.path
    assert phase_path is not None
    if not phase_path.exists():
        phases = []
        for phase in PHASES:
            status = "pending"
            reason = ""
            if phase == "authorization":
                status, reason = "complete", authorization_ref
            elif phase == "identity" and identity_confirmed:
                status, reason = "complete", "Identity fields supplied"
            elif phase == "platform_identification" and platform_identified:
                status, reason = "complete", f"Platform classified as {platform}"
            phase_row = {
                "phase": phase, "required": True, "status": status, "reason": reason,
                "artifacts": list(PHASE_ARTIFACTS[phase]),
                "updated_at": created if status == "complete" else "",
            }
            if phase in PHASE_BRANCHES:
                phase_row["substatuses"] = {name: "" for name in PHASE_BRANCHES[phase]}
            phases.append(phase_row)
        phase_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "stream": APP_STREAM,
                "status_file": APP_PHASE_STATUS_FILENAME,
                "current_phase": "authorization",
                "next_phase": "identity",
                "last_completed_phase": "",
                "updated_at": created,
                "phases": phases,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        _ensure_substatus_keys(phase_path)

    # review JSON/CSV 产物骨架：write_if_missing 幂等（resume 补种同路径执行）；
    # substatuses 空串=未记录，审计在 phase 完成时强制；CSV 产物仅种表头。
    for _review_phase, (_rel_artifact, _contract) in REVIEW_JSON_ARTIFACTS.items():
        write_text_if_missing(
            root / _rel_artifact,
            json.dumps(review_json_skeleton(_review_phase, _contract), ensure_ascii=False, indent=2) + "\n",
        )
    for _rel_csv, _csv_fields in REVIEW_CSV_ARTIFACTS.items():
        write_csv_if_missing(root / _rel_csv, _csv_fields, [])

    write_text_if_missing(root / "notes" / "target-model.md", "# Target model\n\n## Host map\n\n## Technology stack\n\n## Entrypoints\n\n## Authentication topology\n\n## Attack-surface decisions\n\n## Excluded and untested areas\n")
    write_text_if_missing(
        root / "notes" / "operator_tasks.md",
        "# Operator tasks\n\n"
        "- [ ] Confirm authorization evidence, testing window, and scope before active testing.\n"
        "- [ ] Designate the test device (and its constraints) before any dynamic phase; device changes stay approval-gated.\n"
        "- [ ] Supply unpacked material for hardened-shell packages (unpacking is approval-gated; never automatic).\n",
    )
    write_text_if_missing(
        root / "notes" / "safety-controls.md",
        "# Safety controls\n\n"
        "- Default automation: read-only\n"
        "- Write or state-changing actions: operator approval required before execution\n"
        "- Device changes (root/jailbreak, user CA install, frida-server, repackaging): approval-gated (device_instrumentation)\n"
        "- Hardened-shell unpacking: blocked by default (app_hardened_unpack); operator-supplied unpacked material only\n"
        f"- Rate profile: {args.rate.strip() or 'low_rate_no_disruption_required'}\n"
        "- Stop policy: stop on service degradation, error spikes, or normal-user impact risk\n",
    )
    write_text_if_missing(
        root / "reports" / "final-report.md",
        "# Final report\n\n"
        "## Executive summary\n\n"
        "## App identity, scope, and rules\n\n"
        "## Client and package analysis coverage\n\n"
        "## Backend host and API classification\n\n"
        "## Confirmed findings\n\n"
        "## Rejected candidates and false positives\n\n"
        "## Blocked, approval-gated, and not-applicable areas\n\n"
        "## Cleanup and residual risk\n\n"
        "## Evidence index\n\n",
    )
    write_text_if_missing(root / "reports" / ".gitkeep", "")
    print(f"workspace={root}")
    print(f"phase_status_file={phase_path.name}")
    print(f"stream={phase_route.stream}")
    print(f"input_type={input_type}")
    print(f"platform={platform}")
    print(f"identity={'confirmed' if identity_confirmed else 'pending'}")
    print("authorization=target_received (active testing not authorized)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
