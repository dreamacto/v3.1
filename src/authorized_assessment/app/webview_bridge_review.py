"""APP WebView/Bridge/Deep Link 清单引擎（施工方案 §5.3，批次 B5/W19 中段；
契约 contracts/app_webview_schema.json；克隆 xcx webview CSV 模式——行级校验语义
与 app audit 脚本 _check_webview_origin_row/_check_bridge_method_row/
_check_deep_link_row 同源，引擎侧供复核会话构建/落盘前自检清单）。

七复核分支 × 三个固定 CSV 产物（artifacts/app/webview/，分支→产物 1:1）：
- webview-origin-inventory.csv：webview_allowed_domains / postmessage_origin /
  cookie_token_sharing_boundary；
- bridge-method-inventory.csv：bridge_method_exposure；
- deep-link-review-queue.csv：custom_scheme / deep_link_sensitive_params /
  external_app_browser_jump。

升级边界（契约 boundary_status_rule）：boundary_status 可空；非空须 ∈ finding
8 状态——只有能造成跨域数据读取、越权、敏感 token 暴露或外部控制时才升级，
仅形态观察（域名/scheme 存在性）永不升级。判定子集行（共享 cookie/token、四影响面
capability、外部跳转/敏感参数深链）需非空 reason（静默省略禁止）。

红线（契约 red_lines 同源）：Cookie/token 共享边界分析只做离线材料与授权流量，
不自动注入 cookie/token、不重放深链；深链验证不自动拉起外部 App/浏览器；origin
清单只记录授权材料/既有只读证据中观察到的域名，不对未在 scope 内的 origin 发起
请求。本引擎纯离线：duplicate_execution=false。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from authorized_assessment.app.app_review_common import (
    DUPLICATE_EXECUTION_NOTE,
    FINDING_STATUS_VALUES,
)

WEBVIEW_PHASE = "webview_bridge_links"
WEBVIEW_REVIEW_CONTRACT = "app_webview_schema"
WEBVIEW_SCHEMA_VERSION = "1.0"

# 七分支（契约 phases.webview_bridge_links.branches、init/audit 种子三方同源）。
WEBVIEW_REVIEW_BRANCHES: tuple[str, ...] = (
    "webview_allowed_domains",
    "postmessage_origin",
    "cookie_token_sharing_boundary",
    "bridge_method_exposure",
    "custom_scheme",
    "deep_link_sensitive_params",
    "external_app_browser_jump",
)

# 三产物（路径相对 engagement 工作区根；契约 artifacts[].artifact、init
# PHASE_ARTIFACTS 顺序同源）。
WEBVIEW_ORIGIN_INVENTORY_CSV = "artifacts/app/webview/webview-origin-inventory.csv"
WEBVIEW_BRIDGE_METHOD_CSV = "artifacts/app/webview/bridge-method-inventory.csv"
WEBVIEW_DEEP_LINK_QUEUE_CSV = "artifacts/app/webview/deep-link-review-queue.csv"
WEBVIEW_ARTIFACTS: tuple[str, ...] = (
    WEBVIEW_ORIGIN_INVENTORY_CSV,
    WEBVIEW_BRIDGE_METHOD_CSV,
    WEBVIEW_DEEP_LINK_QUEUE_CSV,
)
WEBVIEW_BRANCH_ARTIFACTS: dict[str, str] = {
    "webview_allowed_domains": WEBVIEW_ORIGIN_INVENTORY_CSV,
    "postmessage_origin": WEBVIEW_ORIGIN_INVENTORY_CSV,
    "cookie_token_sharing_boundary": WEBVIEW_ORIGIN_INVENTORY_CSV,
    "bridge_method_exposure": WEBVIEW_BRIDGE_METHOD_CSV,
    "custom_scheme": WEBVIEW_DEEP_LINK_QUEUE_CSV,
    "deep_link_sensitive_params": WEBVIEW_DEEP_LINK_QUEUE_CSV,
    "external_app_browser_jump": WEBVIEW_DEEP_LINK_QUEUE_CSV,
}

# CSV 表头（契约 csv_fields、init REVIEW_CSV_ARTIFACTS 同源）。
WEBVIEW_ORIGIN_CSV_FIELDS: tuple[str, ...] = (
    "row_id", "webview_origin", "business_purpose", "source_material",
    "source_location", "postmessage_target_origin", "cookie_token_shared",
    "boundary_status", "evidence_ref", "reason", "notes",
)
WEBVIEW_BRIDGE_CSV_FIELDS: tuple[str, ...] = (
    "row_id", "method_name", "exposed_scope", "capability", "source_material",
    "boundary_status", "evidence_ref", "reason", "notes",
)
WEBVIEW_DEEP_LINK_CSV_FIELDS: tuple[str, ...] = (
    "row_id", "deep_link_pattern", "scheme_type", "sensitive_params", "jump_target",
    "boundary_status", "evidence_ref", "reason", "notes",
)
WEBVIEW_CSV_FIELDS: dict[str, tuple[str, ...]] = {
    WEBVIEW_ORIGIN_INVENTORY_CSV: WEBVIEW_ORIGIN_CSV_FIELDS,
    WEBVIEW_BRIDGE_METHOD_CSV: WEBVIEW_BRIDGE_CSV_FIELDS,
    WEBVIEW_DEEP_LINK_QUEUE_CSV: WEBVIEW_DEEP_LINK_CSV_FIELDS,
}

# 行级枚举（契约 row_enums、audit 种子同源）。
WEBVIEW_COOKIE_TOKEN_SHARED_VALUES: tuple[str, ...] = (
    "none", "session_cookie", "auth_token", "both", "unknown",
)
WEBVIEW_CAPABILITY_VALUES: tuple[str, ...] = (
    "navigation", "read_data", "write_data", "sensitive_token_access",
    "file_access", "payment", "other",
)
WEBVIEW_SCHEME_TYPES: tuple[str, ...] = ("custom_scheme", "https_link", "other")
WEBVIEW_JUMP_TARGETS: tuple[str, ...] = ("in_app", "external_app", "browser", "unknown")

# 判定子集（reason 必填；audit 同源）。
WEBVIEW_BRIDGE_REASON_CAPABILITIES: tuple[str, ...] = (
    "write_data", "sensitive_token_access", "file_access", "payment",
)
WEBVIEW_REASON_JUMP_TARGETS: tuple[str, ...] = ("external_app", "browser", "unknown")

WEBVIEW_ROW_ENUMS: dict[str, dict[str, tuple[str, ...]]] = {
    WEBVIEW_ORIGIN_INVENTORY_CSV: {
        "cookie_token_shared": WEBVIEW_COOKIE_TOKEN_SHARED_VALUES,
    },
    WEBVIEW_BRIDGE_METHOD_CSV: {
        "capability": WEBVIEW_CAPABILITY_VALUES,
    },
    WEBVIEW_DEEP_LINK_QUEUE_CSV: {
        "scheme_type": WEBVIEW_SCHEME_TYPES,
        "jump_target": WEBVIEW_JUMP_TARGETS,
    },
}

WEBVIEW_INVARIANTS: tuple[str, ...] = (
    "分支→产物 1:1：三产物 branches 无交集且并集恰为七分支",
    "tested 分支要求其所属产物 ≥1 数据行；not_applicable 需 phase 行 reason 非空",
    "boundary_status 可空、非空须 ∈ finding 8 状态；仅形态观察永不升级",
    "不自动注入 cookie/token、不重放深链、不拉起外部 App/浏览器；"
    + DUPLICATE_EXECUTION_NOTE,
)


# ---------------------------------------------------------------------------
# CSV 读写（表头精确匹配 init 种子）
# ---------------------------------------------------------------------------

def read_inventory_csv(path: Path, expected_fields: Sequence[str]) -> tuple[list[dict], list[str]]:
    """读取清单 CSV：表头必须与 expected_fields 逐一相同（空 CSV 也校验表头）；
    返回 (rows, issues)。"""
    csv_path = Path(path)
    if not csv_path.is_file():
        return [], [f"{csv_path.name}: file missing"]
    issues: list[str] = []
    try:
        with csv_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            first = next(csv.reader(handle), None)
    except OSError:
        return [], [f"{csv_path.name}: unreadable"]
    header = tuple(item.strip() for item in first) if first is not None else ()
    if header != tuple(expected_fields):
        issues.append(
            f"{csv_path.name}: header must be exactly {list(expected_fields)} (got {list(header)})"
        )
    rows: list[dict] = []
    with csv_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        rows = [dict(item) for item in csv.DictReader(handle)]
    return rows, issues


def write_inventory_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> Path:
    """写清单 CSV（表头 = fields；父目录自动创建）。"""
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "") or "") for field in fields})
    return csv_path


def assign_row_ids(rows: Iterable[dict], prefix: str) -> list[dict]:
    """为清单行分配 row_id（<prefix>-0001 起，确定性）。"""
    assigned: list[dict] = []
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        if not str(item.get("row_id") or "").strip():
            item["row_id"] = f"{prefix}-{index:04d}"
        assigned.append(item)
    return assigned


def _check_boundary_status(row: Mapping[str, object], label: str) -> list[str]:
    issues: list[str] = []
    boundary_status = str(row.get("boundary_status", "")).strip()
    if boundary_status and boundary_status not in FINDING_STATUS_VALUES:
        issues.append(
            f"{label}: invalid boundary_status {boundary_status!r} "
            f"(allowed: {list(FINDING_STATUS_VALUES)})"
        )
    return issues


# ---------------------------------------------------------------------------
# 行级校验（与 app audit 行校验同源语义）
# ---------------------------------------------------------------------------

def validate_origin_row(row: Mapping[str, object], label: str = "webview_origin_row") -> list[str]:
    """origin 清单行校验：webview_origin/cookie_token_shared 非空 + 共享枚举
    （判定值非 none 需非空 reason）+ boundary_status 规则。"""
    issues: list[str] = []
    if not str(row.get("webview_origin", "")).strip():
        issues.append(f"{label}: empty webview_origin")
    cookie_token_shared = str(row.get("cookie_token_shared", "")).strip()
    if not cookie_token_shared:
        issues.append(f"{label}: empty cookie_token_shared")
    elif cookie_token_shared not in WEBVIEW_COOKIE_TOKEN_SHARED_VALUES:
        issues.append(
            f"{label}: invalid cookie_token_shared {cookie_token_shared!r} "
            f"(allowed: {list(WEBVIEW_COOKIE_TOKEN_SHARED_VALUES)})"
        )
    elif cookie_token_shared != "none" and not str(row.get("reason", "")).strip():
        issues.append(
            f"{label}: cookie_token_shared {cookie_token_shared!r} requires a non-empty "
            "reason (silent omission is forbidden)"
        )
    issues += _check_boundary_status(row, label)
    return issues


def validate_bridge_method_row(row: Mapping[str, object], label: str = "bridge_method_row") -> list[str]:
    """bridge 方法行校验：method_name/exposed_scope/capability 非空 + capability
    枚举（四影响面判定子集命中需非空 reason）+ boundary_status 规则。"""
    issues: list[str] = []
    if not str(row.get("method_name", "")).strip():
        issues.append(f"{label}: empty method_name")
    if not str(row.get("exposed_scope", "")).strip():
        issues.append(f"{label}: empty exposed_scope")
    capability = str(row.get("capability", "")).strip()
    if not capability:
        issues.append(f"{label}: empty capability")
    elif capability not in WEBVIEW_CAPABILITY_VALUES:
        issues.append(
            f"{label}: invalid capability {capability!r} "
            f"(allowed: {list(WEBVIEW_CAPABILITY_VALUES)})"
        )
    elif capability in WEBVIEW_BRIDGE_REASON_CAPABILITIES and not str(
        row.get("reason", "")).strip():
        issues.append(
            f"{label}: capability {capability!r} requires a non-empty reason "
            "(silent omission is forbidden)"
        )
    issues += _check_boundary_status(row, label)
    return issues


def validate_deep_link_row(row: Mapping[str, object], label: str = "deep_link_row") -> list[str]:
    """深链行校验：deep_link_pattern/scheme_type/jump_target 非空 + 枚举（携带
    敏感参数或外部/未确认跳转的行需非空 reason）+ boundary_status 规则。"""
    issues: list[str] = []
    if not str(row.get("deep_link_pattern", "")).strip():
        issues.append(f"{label}: empty deep_link_pattern")
    scheme_type = str(row.get("scheme_type", "")).strip()
    if not scheme_type:
        issues.append(f"{label}: empty scheme_type")
    elif scheme_type not in WEBVIEW_SCHEME_TYPES:
        issues.append(
            f"{label}: invalid scheme_type {scheme_type!r} "
            f"(allowed: {list(WEBVIEW_SCHEME_TYPES)})"
        )
    jump_target = str(row.get("jump_target", "")).strip()
    if not jump_target:
        issues.append(f"{label}: empty jump_target")
    elif jump_target not in WEBVIEW_JUMP_TARGETS:
        issues.append(
            f"{label}: invalid jump_target {jump_target!r} "
            f"(allowed: {list(WEBVIEW_JUMP_TARGETS)})"
        )
    sensitive_params = str(row.get("sensitive_params", "")).strip()
    if (
        (sensitive_params or jump_target in WEBVIEW_REASON_JUMP_TARGETS)
        and not str(row.get("reason", "")).strip()
    ):
        issues.append(
            f"{label}: deep link with sensitive params or external/unconfirmed jump "
            "requires a non-empty reason (silent omission is forbidden)"
        )
    issues += _check_boundary_status(row, label)
    return issues


WEBVIEW_ROW_VALIDATORS: dict[str, object] = {
    WEBVIEW_ORIGIN_INVENTORY_CSV: validate_origin_row,
    WEBVIEW_BRIDGE_METHOD_CSV: validate_bridge_method_row,
    WEBVIEW_DEEP_LINK_QUEUE_CSV: validate_deep_link_row,
}


def validate_webview_inventory(workspace: Path) -> tuple[dict[str, list[dict]], list[str]]:
    """校验工作区内三份 webview 清单 CSV（表头精确匹配 + 逐行校验）。
    返回 (rows_by_artifact, issues)。"""
    rows_by_artifact: dict[str, list[dict]] = {}
    issues: list[str] = []
    for artifact_rel, fields in WEBVIEW_CSV_FIELDS.items():
        rows, artifact_issues = read_inventory_csv(Path(workspace) / artifact_rel, fields)
        rows_by_artifact[artifact_rel] = rows
        issues.extend(artifact_issues)
        validator = WEBVIEW_ROW_VALIDATORS[artifact_rel]
        for index, row in enumerate(rows, start=1):
            issues.extend(
                validator(row, label=f"{artifact_rel}:row {index}")
            )
    return rows_by_artifact, issues


def webview_branch_tested_projection(
    rows_by_artifact: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, bool]:
    """完成语义投影：分支 tested 当且仅当其所属产物 ≥1 数据行（契约
    分支→产物 1:1；audit _csv_completion_issues 同源判据）。"""
    return {
        branch: bool(rows_by_artifact.get(artifact_rel))
        for branch, artifact_rel in WEBVIEW_BRANCH_ARTIFACTS.items()
    }
