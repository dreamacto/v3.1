"""APP IPC 组件边界清单引擎（施工方案 §5.3，批次 B5/W19 中段；契约
contracts/app_ipc_schema.json；App 特有，xcx 无对应物，结构模板克隆 webview 引擎，
行级校验语义与 app audit 脚本 _check_ipc_component_row/_check_ipc_deeplink_row
同源）。

七复核分支 × 两个固定 CSV 产物（artifacts/app/ipc/，分支→产物 1:1）：
- component-inventory.csv：exported_activity / exported_service / exported_receiver /
  exported_provider / ios_extension_boundary；
- deeplink-review-queue.csv：custom_scheme_deeplink / universal_link。

升级边界（契约 boundary_status_rule）：boundary_status 可空；非空须 ∈ finding
8 状态——只有能造成越权、敏感数据暴露或外部控制时才升级，仅 exported/scheme
存在性观察永不升级。exported=true 的行需非空 reason（外部可达攻击面必须留痕，
静默 exported 不得充数）。

红线（契约 red_lines 同源）：静态清单离线完成（manifest 深解析/解包源码/授权
材料/既有只读证据——manifest 行可由 static_extraction.manifest_ipc_component_rows
生成）；实际触发任何组件的 intent/deeplink（尤其写组件）= device_instrumentation
审批门；deeplink 验证不自动拉起外部 App/浏览器，不向未确认归属的 provider/
authority 发请求。本引擎纯离线：duplicate_execution=false。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from authorized_assessment.app.app_review_common import (
    DUPLICATE_EXECUTION_NOTE,
    FINDING_STATUS_VALUES,
)
from authorized_assessment.app.webview_bridge_review import read_inventory_csv
from authorized_assessment.app.webview_bridge_review import (
    WEBVIEW_JUMP_TARGETS as _WEBVIEW_JUMP_TARGETS,
)
from authorized_assessment.app.webview_bridge_review import (
    WEBVIEW_SCHEME_TYPES as _WEBVIEW_SCHEME_TYPES,
)

# 共享 CSV 助手（单一实现于 webview 引擎；ipc 引擎复用，assign_row_ids/
# write_inventory_csv 经本命名空间再导出供 ipc 复核会话调用）。
from authorized_assessment.app.webview_bridge_review import (  # noqa: F401
    assign_row_ids,
    write_inventory_csv,
)

IPC_PHASE = "ipc_component_boundary"
IPC_REVIEW_CONTRACT = "app_ipc_schema"
IPC_SCHEMA_VERSION = "1.0"

# 七分支（契约 phases.ipc_component_boundary.branches、init/audit 种子三方同源）。
IPC_REVIEW_BRANCHES: tuple[str, ...] = (
    "exported_activity",
    "exported_service",
    "exported_receiver",
    "exported_provider",
    "custom_scheme_deeplink",
    "universal_link",
    "ios_extension_boundary",
)

# 两产物（路径相对 engagement 工作区根；契约 artifacts[].artifact、init
# PHASE_ARTIFACTS 顺序同源）。
IPC_COMPONENT_INVENTORY_CSV = "artifacts/app/ipc/component-inventory.csv"
IPC_DEEPLINK_QUEUE_CSV = "artifacts/app/ipc/deeplink-review-queue.csv"
IPC_ARTIFACTS: tuple[str, ...] = (
    IPC_COMPONENT_INVENTORY_CSV,
    IPC_DEEPLINK_QUEUE_CSV,
)
IPC_BRANCH_ARTIFACTS: dict[str, str] = {
    "exported_activity": IPC_COMPONENT_INVENTORY_CSV,
    "exported_service": IPC_COMPONENT_INVENTORY_CSV,
    "exported_receiver": IPC_COMPONENT_INVENTORY_CSV,
    "exported_provider": IPC_COMPONENT_INVENTORY_CSV,
    "ios_extension_boundary": IPC_COMPONENT_INVENTORY_CSV,
    "custom_scheme_deeplink": IPC_DEEPLINK_QUEUE_CSV,
    "universal_link": IPC_DEEPLINK_QUEUE_CSV,
}

# CSV 表头（契约 csv_fields、init REVIEW_CSV_ARTIFACTS 同源）。
IPC_COMPONENT_CSV_FIELDS: tuple[str, ...] = (
    "row_id", "component_kind", "component_name", "exported", "permission",
    "intent_actions", "scheme", "authority", "source_material", "source_location",
    "boundary_status", "evidence_ref", "reason", "notes",
)
IPC_DEEPLINK_CSV_FIELDS: tuple[str, ...] = (
    "row_id", "deep_link_pattern", "scheme_type", "sensitive_params", "component_ref",
    "jump_target", "boundary_status", "evidence_ref", "reason", "notes",
)
IPC_CSV_FIELDS: dict[str, tuple[str, ...]] = {
    IPC_COMPONENT_INVENTORY_CSV: IPC_COMPONENT_CSV_FIELDS,
    IPC_DEEPLINK_QUEUE_CSV: IPC_DEEPLINK_CSV_FIELDS,
}

# 行级枚举（契约 row_enums、audit 种子同源；deeplink 队列 scheme_type/jump_target
# 与 webview 深链队列同源——同一常量再导出，避免两份字面量漂移）。
IPC_COMPONENT_KINDS: tuple[str, ...] = (
    "activity", "service", "receiver", "provider", "ios_extension", "other",
)
IPC_EXPORTED_VALUES: tuple[str, ...] = ("true", "false", "unknown")
IPC_SCHEME_TYPES: tuple[str, ...] = _WEBVIEW_SCHEME_TYPES
IPC_JUMP_TARGETS: tuple[str, ...] = _WEBVIEW_JUMP_TARGETS
IPC_REASON_JUMP_TARGETS: tuple[str, ...] = ("external_app", "browser", "unknown")
# exported 判定子集（reason 必填；契约 reason_required_exported_values 同源）。
IPC_REASON_EXPORTED_VALUES: tuple[str, ...] = ("true",)

IPC_ROW_ENUMS: dict[str, dict[str, tuple[str, ...]]] = {
    IPC_COMPONENT_INVENTORY_CSV: {
        "component_kind": IPC_COMPONENT_KINDS,
        "exported": IPC_EXPORTED_VALUES,
    },
    IPC_DEEPLINK_QUEUE_CSV: {
        "scheme_type": IPC_SCHEME_TYPES,
        "jump_target": IPC_JUMP_TARGETS,
    },
}

IPC_INVARIANTS: tuple[str, ...] = (
    "分支→产物 1:1：两产物 branches 无交集且并集恰为七分支",
    "tested 分支要求其所属产物 ≥1 数据行；not_applicable 需 phase 行 reason 非空",
    "exported=true 行需非空 reason（外部可达攻击面必须留痕）",
    "实际触发 intent/deeplink = device_instrumentation 审批门；本引擎只做静态清单，"
    + DUPLICATE_EXECUTION_NOTE,
)


# ---------------------------------------------------------------------------
# 行级校验（与 app audit 行校验同源语义）
# ---------------------------------------------------------------------------

def validate_component_row(row: Mapping[str, object], label: str = "ipc_component_row") -> list[str]:
    """组件清单行校验：component_kind/component_name/exported 非空 + 枚举；
    exported=true 需非空 reason；boundary_status 可空、非空须 ∈ finding 8 状态。"""
    issues: list[str] = []
    component_kind = str(row.get("component_kind", "")).strip()
    if not component_kind:
        issues.append(f"{label}: empty component_kind")
    elif component_kind not in IPC_COMPONENT_KINDS:
        issues.append(
            f"{label}: invalid component_kind {component_kind!r} "
            f"(allowed: {list(IPC_COMPONENT_KINDS)})"
        )
    if not str(row.get("component_name", "")).strip():
        issues.append(f"{label}: empty component_name")
    exported = str(row.get("exported", "")).strip()
    if not exported:
        issues.append(f"{label}: empty exported")
    elif exported not in IPC_EXPORTED_VALUES:
        issues.append(
            f"{label}: invalid exported {exported!r} "
            f"(allowed: {list(IPC_EXPORTED_VALUES)})"
        )
    elif exported == "true" and not str(row.get("reason", "")).strip():
        issues.append(
            f"{label}: exported component requires a non-empty reason "
            "(silent omission is forbidden)"
        )
    boundary_status = str(row.get("boundary_status", "")).strip()
    if boundary_status and boundary_status not in FINDING_STATUS_VALUES:
        issues.append(
            f"{label}: invalid boundary_status {boundary_status!r} "
            f"(allowed: {list(FINDING_STATUS_VALUES)})"
        )
    return issues


def validate_ipc_deeplink_row(row: Mapping[str, object], label: str = "ipc_deeplink_row") -> list[str]:
    """deeplink 队列行校验：deep_link_pattern/scheme_type/jump_target 非空 + 枚举
    （与 webview 深链队列同源）；携带敏感参数或外部/未确认跳转的行需非空
    reason；component_ref 可空。"""
    issues: list[str] = []
    if not str(row.get("deep_link_pattern", "")).strip():
        issues.append(f"{label}: empty deep_link_pattern")
    scheme_type = str(row.get("scheme_type", "")).strip()
    if not scheme_type:
        issues.append(f"{label}: empty scheme_type")
    elif scheme_type not in IPC_SCHEME_TYPES:
        issues.append(
            f"{label}: invalid scheme_type {scheme_type!r} "
            f"(allowed: {list(IPC_SCHEME_TYPES)})"
        )
    jump_target = str(row.get("jump_target", "")).strip()
    if not jump_target:
        issues.append(f"{label}: empty jump_target")
    elif jump_target not in IPC_JUMP_TARGETS:
        issues.append(
            f"{label}: invalid jump_target {jump_target!r} "
            f"(allowed: {list(IPC_JUMP_TARGETS)})"
        )
    sensitive_params = str(row.get("sensitive_params", "")).strip()
    if (
        (sensitive_params or jump_target in IPC_REASON_JUMP_TARGETS)
        and not str(row.get("reason", "")).strip()
    ):
        issues.append(
            f"{label}: deep link with sensitive params or external/unconfirmed jump "
            "requires a non-empty reason (silent omission is forbidden)"
        )
    boundary_status = str(row.get("boundary_status", "")).strip()
    if boundary_status and boundary_status not in FINDING_STATUS_VALUES:
        issues.append(
            f"{label}: invalid boundary_status {boundary_status!r} "
            f"(allowed: {list(FINDING_STATUS_VALUES)})"
        )
    return issues


IPC_ROW_VALIDATORS: dict[str, object] = {
    IPC_COMPONENT_INVENTORY_CSV: validate_component_row,
    IPC_DEEPLINK_QUEUE_CSV: validate_ipc_deeplink_row,
}


def validate_ipc_inventory(workspace: Path) -> tuple[dict[str, list[dict]], list[str]]:
    """校验工作区内两份 ipc 清单 CSV（表头精确匹配 + 逐行校验）。
    返回 (rows_by_artifact, issues)。"""
    rows_by_artifact: dict[str, list[dict]] = {}
    issues: list[str] = []
    for artifact_rel, fields in IPC_CSV_FIELDS.items():
        rows, artifact_issues = read_inventory_csv(Path(workspace) / artifact_rel, fields)
        rows_by_artifact[artifact_rel] = rows
        issues.extend(artifact_issues)
        validator = IPC_ROW_VALIDATORS[artifact_rel]
        for index, row in enumerate(rows, start=1):
            issues.extend(validator(row, label=f"{artifact_rel}:row {index}"))
    return rows_by_artifact, issues


def ipc_branch_tested_projection(
    rows_by_artifact: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, bool]:
    """完成语义投影：分支 tested 当且仅当其所属产物 ≥1 数据行（audit
    _csv_completion_issues 同源判据）。"""
    return {
        branch: bool(rows_by_artifact.get(artifact_rel))
        for branch, artifact_rel in IPC_BRANCH_ARTIFACTS.items()
    }
