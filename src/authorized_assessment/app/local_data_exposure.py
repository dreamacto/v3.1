"""APP 本地数据暴露复核域（施工方案 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §4 阶段
24 + §5.3，批次 B6/W19 收尾；契约 contracts/app_storage_package_schema.json 的
local_data_exposure phase）。

只读离线：复用本包共享引擎 app_review_common（B5 落地：观察键→证据形态确定性映射
→rule_satisfied 升级判定→8 状态分级、confirm 升级门），本模块只定义本地数据暴露
分支/证据形态/观察映射/升级规则常量与筛选入口，并承载 storage 两 phase 共用的
"行内 platform 列"筛选助手（crypto_secret_review 复用，同 miniapp Batch11 宿主
模式）。不发任何请求、不读取凭证文件、不导出敏感数据原文——观察输入为复核会话
从操作员提供的授权材料、本地流量或包副本提炼的结构化记录；token/AppSecret/密钥
原文等敏感值不得复制到普通日志、报告、prompt、ledger 或交接内容（凭证纪律，红线
常量留痕）。

行内 platform 列（契约 invariant："行级 platform 区分（android/ios）由 row 扩展键
承载，不破坏 12 键形状"）：每条产行观察必须带 platform ∈ {android, ios}——
android（shared_prefs/sqlite/realm/外部存储/备份）与 ios（keychain/plist/快照）
的存储面不同，行级区分是 App 双平台去重与判定前提；平台无关的跨平台结论拆成两条
观察分别记录。只使用操作者授权材料与指定测试设备（方案 §4 阶段 24 红线）。

五分支（与 contracts/app_storage_package_schema.json phases.local_data_exposure.
branches、app init/audit 种子三方同源；分支名与 xcx 同名同义，按方案 §5.3 复用
边界在本包自包含定义常量）：
- token_persistence：token 是否落地；
- logout_cleanup：logout 是否清理；
- local_cache_database：本地缓存、数据库；
- logs_clipboard_screenshots：日志、剪贴板、截图；
- temp_files：临时文件。

升级边界（实现定义供操作者复核）：仅对应分支的确认证据（*_confirmed，来自既有
只读证据的复核判定且可复现）可升级 candidate；"存储键存在/缓存目录线索/清理
代码缺失"等形态与支持性观察永不升级（signal 不是漏洞）。confirmed 五门判定仍归
finding_quality_gate；本模块只做候选层分级校验。
"""
from __future__ import annotations

from typing import Iterable, Mapping

from authorized_assessment.app import app_review_common as arc
from authorized_assessment.app.hardening_integrity_review import (
    APP_STORAGE_PACKAGE_CONTRACT,
    APP_STORAGE_PACKAGE_SCHEMA_VERSION,
)
from authorized_assessment.triage import injection_candidates as ic

# phase 与产物路径（契约 phases.local_data_exposure.artifact、init/audit 种子三方
# 同源）。
LOCAL_DATA_PHASE = "local_data_exposure"
LOCAL_DATA_REVIEW_ARTIFACT = "artifacts/app/storage/local-data-review.json"

# 行内 platform 列允许值（契约 invariant "android/ios" 同源；本模块同时作为
# crypto_secret_review 的共享宿主）。
APP_PLATFORM_VALUES: tuple[str, ...] = ("android", "ios")

# platform 扩展行形状：8 标准字段 + platform 扩展键（12 键 artifact 形状不破坏，
# row_fields 仍为契约 8 字段，platform 是行扩展键）。
PLATFORM_TAGGED_ROW_FIELDS: tuple[str, ...] = arc.APP_REVIEW_ROW_FIELDS + ("platform",)


def screen_platform_tagged_observations(
    observations: Iterable[Mapping[str, object]],
    branches: tuple[str, ...],
    observation_evidence_map: Mapping[str, str],
    evidence_kinds_all: tuple[str, ...],
    insufficient_kinds: tuple[str, ...],
    upgrade_rules: Mapping[str, Mapping[str, object]],
    all_branches: bool = True,
    label: str = "local_data_exposure",
) -> tuple[list[dict], list[dict], list[str]]:
    """带行内 platform 列的观察筛选 → (候选行, 分支汇总行, 违例)。

    在共享引擎筛选结果上逐行附着 platform 扩展键（观察键 platform → 行扩展键，
    不破坏 12 键 artifact 形状）；产行观察的 platform 必须为 android/ios，缺失或
    非法记违例（fail-visible：行仍产出供复核，违例进 artifact.violations）。
    产行子序列按共享引擎跳过规则镜像推导（非映射/非法 branch/非法 applicability/
    not_applicable 不产行），行数不一致时防御性记违例并跳过附着。
    """
    rows, summaries, violations = arc.screen_app_observations(
        observations,
        branches,
        observation_evidence_map,
        evidence_kinds_all,
        insufficient_kinds,
        upgrade_rules,
        all_branches=all_branches,
        label=label,
    )
    producing: list[Mapping[str, object]] = []
    for observation in observations:
        if not isinstance(observation, Mapping):
            continue
        if str(observation.get("branch") or "") not in branches:
            continue
        applicability = str(observation.get("applicability") or "unknown")
        if applicability not in ic.APPLICABLE_VALUES or applicability == "not_applicable":
            continue
        producing.append(observation)
    if len(producing) != len(rows):
        violations.append(
            f"{label}: platform 列附着失败（产行观察 {len(producing)} 条 ↔ 候选行 "
            f"{len(rows)} 行不一致——共享引擎跳过规则漂移，需复核）"
        )
        return rows, summaries, violations
    for row, observation in zip(rows, producing):
        platform = str(observation.get("platform") or "").strip()
        row["platform"] = platform
        if platform not in APP_PLATFORM_VALUES:
            violations.append(
                f"{label}[{row['row_id']}]: platform 非法/缺失 {platform!r}"
                f"（行内 platform 列必须区分 android/ios）"
            )
    return rows, summaries, violations


def validate_platform_tagged_row(
    row: Mapping[str, object],
    branches: tuple[str, ...],
    evidence_kinds_all: tuple[str, ...],
    insufficient_kinds: tuple[str, ...],
    upgrade_rules: Mapping[str, Mapping[str, object]],
    label: str = "platform_tagged_candidate",
) -> list[str]:
    """platform 扩展行校验：共享 8 字段语义 + platform ∈ {android, ios} 强制。"""
    violations = arc.validate_app_review_row(
        row,
        branches,
        evidence_kinds_all,
        insufficient_kinds,
        upgrade_rules,
        label=label,
    )
    if isinstance(row, Mapping):
        platform = str(row.get("platform") or "").strip()
        if platform not in APP_PLATFORM_VALUES:
            violations.append(
                f"{label}: platform 非法/缺失 {platform!r}"
                f"（行内 platform 列必须区分 android/ios，允许值 {list(APP_PLATFORM_VALUES)}）"
            )
    return violations


# 五分支（契约 phases.local_data_exposure.branches 同源）。
LOCAL_DATA_BRANCHES: tuple[str, ...] = (
    "token_persistence",
    "logout_cleanup",
    "local_cache_database",
    "logs_clipboard_screenshots",
    "temp_files",
)

# 证据形态（15：10 形态/支持性永不升级 + 5 确认形态与分支一一对应；与 xcx 同名
# 同义，本地存储语义经 platform 列区分 android/ios 存储面）。
LOCAL_DATA_EVIDENCE_KINDS: tuple[str, ...] = (
    "token_storage_key_observed",
    "token_value_persisted_observed",
    "logout_cleanup_code_observed",
    "residual_data_after_logout_observed",
    "cache_directory_clue_observed",
    "local_database_record_clue_observed",
    "log_sensitive_field_observed",
    "clipboard_write_marker_observed",
    "screenshot_capture_marker_observed",
    "temp_file_retention_clue_observed",
    "token_survives_logout_confirmed",
    "cross_account_cache_reuse_confirmed",
    "database_sensitive_rows_confirmed",
    "log_or_clipboard_leak_confirmed",
    "temp_file_sensitive_content_confirmed",
)

# "不算漏洞"证据形态：仅形态/支持性观察，未证明本地数据边界失效。
LOCAL_DATA_INSUFFICIENT_KINDS: tuple[str, ...] = (
    "token_storage_key_observed",
    "token_value_persisted_observed",
    "logout_cleanup_code_observed",
    "residual_data_after_logout_observed",
    "cache_directory_clue_observed",
    "local_database_record_clue_observed",
    "log_sensitive_field_observed",
    "clipboard_write_marker_observed",
    "screenshot_capture_marker_observed",
    "temp_file_retention_clue_observed",
)

# 升级规则（实现定义，固定语义；确认形态与分支一一对应、不跨分支升级）：
# "确认"语义要求观察来自既有只读证据（本地副本/流量/包源码/指定测试设备观察）的
# 复核判定且可复现；禁止为取得确认而批量导出、下载或复制敏感数据原文（凭证/敏感
# 数据纪律，precondition 必须留痕）。
LOCAL_DATA_UPGRADE_RULES: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "token_persistence": {
        "required_any_groups": (("token_survives_logout_confirmed",),)
    },
    "logout_cleanup": {
        "required_any_groups": (("token_survives_logout_confirmed",),)
    },
    "local_cache_database": {
        "required_any_groups": (
            ("cross_account_cache_reuse_confirmed", "database_sensitive_rows_confirmed"),
        )
    },
    "logs_clipboard_screenshots": {
        "required_any_groups": (("log_or_clipboard_leak_confirmed",),)
    },
    "temp_files": {
        "required_any_groups": (("temp_file_sensitive_content_confirmed",),)
    },
}

# v1 观察键 → 证据形态（确定性映射；版本化演进同 OBSERVATION_SCHEMA_VERSION）。
LOCAL_DATA_OBSERVATION_EVIDENCE_MAP: dict[str, str] = {
    key: key for key in LOCAL_DATA_EVIDENCE_KINDS
}

LOCAL_DATA_OBSERVATION_FIELD_DOCS: dict[str, str] = {
    "token_storage_key_observed": "观察到本地存储中存在 token 相关键名（android "
    "shared_prefs/sqlite/realm/外部存储/备份或 ios keychain/plist/快照，仅形态，"
    "不代表敏感值落地）",
    "token_value_persisted_observed": "观察到 token 值被写入本地存储/缓存线索（仅形态）",
    "logout_cleanup_code_observed": "观察到 logout 清理代码路径（支持性，正向线索）",
    "residual_data_after_logout_observed": "观察到注销后本地残留数据线索（仅形态）",
    "cache_directory_clue_observed": "观察到本地缓存目录/文件线索（仅形态）",
    "local_database_record_clue_observed": "观察到本地数据库/结构化存储记录线索"
    "（仅形态）",
    "log_sensitive_field_observed": "观察到日志/输出包含敏感字段名线索（仅形态）",
    "clipboard_write_marker_observed": "观察到剪贴板写入调用标记（仅形态）",
    "screenshot_capture_marker_observed": "观察到截图/屏幕捕获调用标记（仅形态）",
    "temp_file_retention_clue_observed": "观察到临时文件保留/未清理线索（仅形态）",
    "token_survives_logout_confirmed": "已确认注销/切换账号后 token 仍留在本地存储且"
    "可被再次使用（既有只读证据复核且可复现；不读取或导出凭证值）",
    "cross_account_cache_reuse_confirmed": "已确认跨账号缓存/数据库记录复用可复现"
    "（既有只读证据复核且可复现）",
    "database_sensitive_rows_confirmed": "已确认本地数据库保存敏感记录且无访问控制"
    "（既有只读证据复核且可复现；不导出记录原文）",
    "log_or_clipboard_leak_confirmed": "已确认日志/剪贴板/截图内容含敏感数据且可被"
    "其他应用或进程读取（既有只读证据复核且可复现）",
    "temp_file_sensitive_content_confirmed": "已确认临时文件含敏感数据且保留到会话"
    "之外（既有只读证据复核且可复现）",
}

# 红线常量（契约 red_lines + 凭证纪律；写入 artifact 与候选 precondition 语义）。
LOCAL_DATA_MATERIAL_RULE: str = (
    "本地数据复核仅使用操作员提供的授权材料、本地流量、包副本或指定测试设备观察；"
    "不读取凭证文件、不导出敏感数据原文，token/密钥等敏感值不复制到普通日志、报告、"
    "prompt、ledger 或交接内容"
)

# 引擎不变量（契约 invariants/red_lines 的引擎侧锚点；测试与文档引用）。
LOCAL_DATA_INVARIANTS: tuple[str, ...] = (
    "只用操作者授权材料与指定测试设备的既有只读证据；设备改动/root/越狱/装证书属"
    "审批门，本引擎不依赖任何设备改动",
    "行内 platform 列必须区分 android/ios（row 扩展键承载，不破坏 12 键形状）",
    "token/AppSecret/密钥原文等敏感值不复制到普通日志、报告、prompt、ledger 或交接内容",
    "仅 *_confirmed（既有只读证据复核且可复现）可升级 candidate；confirmed 仍归漏洞"
    "成立五门判定，duplicate_execution=false",
)


def screen_local_data_observations(
    observations: Iterable[Mapping[str, object]],
    all_branches: bool = True,
    label: str = "local_data_exposure",
) -> tuple[list[dict], list[dict], list[str]]:
    """本地数据暴露复核筛选（含行内 platform 列）→ (候选行, 分支汇总行, 违例)。"""
    return screen_platform_tagged_observations(
        observations,
        LOCAL_DATA_BRANCHES,
        LOCAL_DATA_OBSERVATION_EVIDENCE_MAP,
        LOCAL_DATA_EVIDENCE_KINDS,
        LOCAL_DATA_INSUFFICIENT_KINDS,
        LOCAL_DATA_UPGRADE_RULES,
        all_branches=all_branches,
        label=label,
    )


def validate_local_data_candidate(
    row: Mapping[str, object], label: str = "local_data_candidate"
) -> list[str]:
    return validate_platform_tagged_row(
        row,
        LOCAL_DATA_BRANCHES,
        LOCAL_DATA_EVIDENCE_KINDS,
        LOCAL_DATA_INSUFFICIENT_KINDS,
        LOCAL_DATA_UPGRADE_RULES,
        label=label,
    )


def build_local_data_review_artifact(
    rows: Iterable[Mapping[str, object]],
    summaries: Iterable[Mapping[str, object]],
    violations: Iterable[str],
    authorization_basis: str,
    updated_at: str,
    substatuses: Mapping[str, str] | None = None,
) -> dict:
    """12 键 local-data-review.json 产物（契约 artifact_fields 形状；行内 platform
    为 row 扩展键，artifact row_fields 仍为契约 8 字段）。"""
    return arc.build_app_review_artifact(
        APP_STORAGE_PACKAGE_CONTRACT,
        APP_STORAGE_PACKAGE_SCHEMA_VERSION,
        LOCAL_DATA_PHASE,
        rows,
        summaries,
        violations,
        authorization_basis,
        updated_at,
        substatuses=substatuses,
    )


def validate_local_data_review_artifact(
    artifact: Mapping[str, object], label: str = "local_data_review_artifact"
) -> list[str]:
    """落盘前自检（与 skill audit 的产物校验语义一致；platform 扩展行在行级校验）。"""
    violations = arc.validate_app_review_artifact(
        artifact,
        APP_STORAGE_PACKAGE_CONTRACT,
        APP_STORAGE_PACKAGE_SCHEMA_VERSION,
        LOCAL_DATA_PHASE,
        LOCAL_DATA_BRANCHES,
        LOCAL_DATA_EVIDENCE_KINDS,
        LOCAL_DATA_INSUFFICIENT_KINDS,
        LOCAL_DATA_UPGRADE_RULES,
        label=label,
    )
    rows = artifact.get("rows") if isinstance(artifact, Mapping) else None
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                violations += validate_local_data_candidate(
                    row, label=f"{label}.rows[{row.get('row_id', '?')}]"
                )
    return violations


def _cli() -> int:
    """离线 CLI：观察 JSON 文件 → review artifact JSON（纯文件到文件）。"""
    import argparse
    import json
    from datetime import datetime
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Offline app local data exposure review (no network, no credential "
        "files, no sensitive value export; rows carry an android/ios platform column)."
    )
    parser.add_argument("--observations", required=True, help="Observations JSON file (list or {observations: [...]})")
    parser.add_argument("--out", required=True, help="Output artifact JSON path")
    parser.add_argument(
        "--authorization-basis",
        default="operator_supplied_material",
        choices=list(arc.APP_AUTHORIZATION_BASIS_VALUES),
    )
    args = parser.parse_args()
    payload = json.loads(Path(args.observations).read_text(encoding="utf-8-sig"))
    observations = payload.get("observations", []) if isinstance(payload, dict) else payload
    if not isinstance(observations, list):
        print("ERROR: observations must be a list", flush=True)
        return 2
    rows, summaries, violations = screen_local_data_observations(observations)
    artifact = build_local_data_review_artifact(
        rows,
        summaries,
        violations,
        authorization_basis=args.authorization_basis,
        updated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"rows={len(artifact['rows'])} summaries={len(artifact['summaries'])} "
          f"violations={len(artifact['violations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
