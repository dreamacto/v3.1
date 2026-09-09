"""APP 流共享评审引擎（施工方案 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §5.3，
批次 B5/W19 中段）+ app 契约族 review JSON 形状的单一构建/校验实现。

只读离线：沿用统一筛选模式（观察键→证据形态确定性映射→rule_satisfied 升级判定→
8 状态分级），不发任何请求、不重打包、不脱壳、不绕过 pinning、不攻击设备
（APP_NO_REPACKING_RULE）。观察输入为复核会话从操作员提供的包副本、解包产物与既有
清单/流量证据提炼的结构化记录。

复用边界（方案 §5.3）：分支常量与 miniapp 不同（hardening 七分支新增
signing/hardening/debug_info 三分支，auth 平台登录分支换 App 语境），因此本包复用
"代码模式"而非 import miniapp 常量——共享实现的单一来源是本模块（克隆
miniapp/platform_login_exchange.py 的引擎模式），分支/证据形态/映射/升级规则常量由
各域模块自包含定义。底层 triage 引擎（injection_candidates 的 rule_satisfied/
aggregate_category_status/validate_category_summary）为全仓单一实现，照常复用。

duplicate_execution=false：本包全部引擎只消费既有只读证据做候选层筛选，永不重复
执行任何探测/请求/解包动作（tool_strategy.json orchestration_only 条目同源语义）；
DUPLICATE_EXECUTION 常量供测试与文档锚定。

产物形状契约：contracts/app_*.json artifact_fields（12 键 JSON：rows=统一筛选候选行
8 状态，summaries=分支级汇总 branch_status 为 coverage_substatus 六值——由
injection_candidates.aggregate_category_status 单一引擎聚合）。契约名与版本经参数
传入（build/validate 不绑定单一契约），分支与产物路径常量由各域模块持有并与
契约、init 种子三方同源（tests/test_app_contract_sync.py 锁定；
scripts/maintenance/validate_run_contracts.py 在线校验）。
"""
from __future__ import annotations

from typing import Iterable, Mapping

from authorized_assessment.triage import injection_candidates as ic

# APP review JSON 骨架（contracts/app_*.json artifact_fields 同源；与 init 种子
# REVIEW_SKELETON_FIELDS、xcx 引擎 AUTH_REVIEW_* 行形状一致，category→branch 改名）。
APP_REVIEW_ROW_FIELDS: tuple[str, ...] = (
    "row_id",
    "branch",
    "status",
    "evidence_kinds",
    "source",
    "evidence_ref",
    "precondition",
    "reason",
)
APP_REVIEW_SUMMARY_FIELDS: tuple[str, ...] = (
    "branch",
    "branch_status",
    "applicability_counts",
    "status_counts",
    "tested_count",
    "reason",
    "source",
    "precondition",
)
APP_REVIEW_ARTIFACT_KEYS: tuple[str, ...] = (
    "schema_version",
    "contract",
    "phase",
    "observation_schema_version",
    "row_fields",
    "summary_fields",
    "substatuses",
    "rows",
    "summaries",
    "violations",
    "authorization_basis",
    "updated_at",
)

# coverage_substatus 六值（单一来源 injection_candidates.CATEGORY_STATUS_VALUES =
# COVERAGE_SUBSTATUSES；契约 coverage_substatus_schema 同源引用，不复制字面量）。
COVERAGE_STATUS_VALUES: tuple[str, ...] = ic.CATEGORY_STATUS_VALUES

# finding 8 状态（rows[].status / CSV boundary_status 共用；单一来源 ic）。
FINDING_STATUS_VALUES: tuple[str, ...] = ic.CANDIDATE_STATUS_VALUES

# 授权材料来源（artifact.authorization_basis 允许值；契约与 audit 种子同源）。
APP_AUTHORIZATION_BASIS_VALUES: tuple[str, ...] = (
    "operator_supplied_material",
    "local_traffic",
)

# 离线引擎永不重复执行任何探测（orchestration_only 同源语义；写入 artifact
# precondition 语义与文档锚点，测试锁定）。
DUPLICATE_EXECUTION = False
DUPLICATE_EXECUTION_NOTE = "duplicate_execution=false"


# ---------------------------------------------------------------------------
# 共享引擎（app 契约族各域模块复用；分支常量由调用方传入）
# ---------------------------------------------------------------------------

def derive_app_evidence_kinds(
    evidence: Mapping[str, object], observation_evidence_map: Mapping[str, str]
) -> list[str]:
    """观察键 → 证据形态（按映射表顺序，确定性；与 miniapp/xcx 引擎同款语义）。"""
    return [
        kind
        for key, kind in observation_evidence_map.items()
        if evidence.get(key)
    ]


def grade_app_observation(
    branch: str,
    evidence_kinds: Iterable[str],
    upgrade_rules: Mapping[str, Mapping[str, object]],
    evidence_kinds_all: Iterable[str],
    insufficient_kinds: Iterable[str],
    status_hint: str | None = None,
) -> str:
    """APP 观察分级：确认形态满足升级规则 → candidate；否则 signal。status_hint
    尊重人工判定（8 状态合法值原样返回）。无升级规则的分支（契约 never_upgrade，
    如 hardening_obfuscation_markers）永不升级。"""
    if status_hint in ic.CANDIDATE_STATUS_VALUES:
        return status_hint
    rule = upgrade_rules.get(branch)
    if rule is None:
        return "signal"
    satisfied, _ = ic.rule_satisfied(
        rule, list(evidence_kinds), list(evidence_kinds_all), list(insufficient_kinds)
    )
    return "candidate" if satisfied else "signal"


def validate_app_review_row(
    row: Mapping[str, object],
    branches: Iterable[str],
    evidence_kinds_all: Iterable[str],
    insufficient_kinds: Iterable[str],
    upgrade_rules: Mapping[str, Mapping[str, object]],
    label: str = "app_review_row",
) -> list[str]:
    """候选行校验：8 状态 + 分支枚举 + 证据形态 + 升级规则（复用 ic 引擎语义；
    confirm 升级门：candidate/confirmed 必须满足对应分支升级规则且 evidence_ref
    非空，否则记违例）。"""
    violations: list[str] = []
    if not isinstance(row, Mapping):
        return [f"{label}: 行必须是键值映射"]
    for field in APP_REVIEW_ROW_FIELDS:
        if field not in row:
            violations.append(f"{label}: 缺少必需字段 {field}")
    branch = str(row.get("branch") or "")
    branch_list = list(branches)
    if branch and branch not in branch_list:
        violations.append(f"{label}.branch 非法: {branch!r}（允许值 {branch_list}）")
    status = str(row.get("status") or "")
    if status and status not in ic.CANDIDATE_STATUS_VALUES:
        violations.append(
            f"{label}.status 非法: {status!r}（允许值 {list(ic.CANDIDATE_STATUS_VALUES)}）"
        )
    kinds = row.get("evidence_kinds")
    if kinds is not None:
        if not isinstance(kinds, (list, tuple)):
            violations.append(f"{label}.evidence_kinds 必须为列表")
        else:
            kind_list = [str(k) for k in kinds]
            if not kind_list:
                violations.append(f"{label}.evidence_kinds 不能为空（signal 也需记录观察形态）")
            unknown = sorted({k for k in kind_list if k not in set(evidence_kinds_all)})
            if unknown:
                violations.append(f"{label}.evidence_kinds 未知形态: {unknown}")
            if len(set(kind_list)) != len(kind_list):
                violations.append(f"{label}.evidence_kinds 存在重复项")
            if status in ("candidate", "confirmed"):
                rule = upgrade_rules.get(branch)
                if rule is None:
                    violations.append(
                        f"{label}: branch={branch} 永不升级（契约 never_upgrade_rule）"
                    )
                else:
                    satisfied, why = ic.rule_satisfied(
                        rule,
                        kind_list,
                        evidence_kinds_all,
                        insufficient_kinds,
                    )
                    if not satisfied:
                        violations.append(
                            f"{label}: status={status} 但升级证据不满足——{why}"
                        )
    if status in ("candidate", "confirmed", "needs_manual_validation") and not str(
        row.get("evidence_ref") or ""
    ).strip():
        violations.append(f"{label}: status={status} 但 evidence_ref 为空（候选必须可证明）")
    return violations


def validate_app_branch_summary(
    summary: Mapping[str, object],
    branches: Iterable[str],
    label: str = "app_branch_summary",
) -> list[str]:
    """分支汇总行校验：经 category 键适配复用 ic.validate_category_summary 全语义
    （三统计概念分离/tested_count 一致性/candidate>0 需 source+precondition/
    not_applicable 需 reason 且无计数）。"""
    if not isinstance(summary, Mapping):
        return [f"{label}: 汇总行必须是键值映射"]
    mapped = {
        "category": summary.get("branch"),
        "category_status": summary.get("branch_status"),
        "applicability_counts": summary.get("applicability_counts"),
        "status_counts": summary.get("status_counts"),
        "tested_count": summary.get("tested_count"),
        "reason": summary.get("reason"),
        "source": summary.get("source"),
        "precondition": summary.get("precondition"),
    }
    return ic.validate_category_summary(mapped, label=label, categories=list(branches))


def screen_app_observations(
    observations: Iterable[Mapping[str, object]],
    branches: tuple[str, ...],
    observation_evidence_map: Mapping[str, str],
    evidence_kinds_all: tuple[str, ...],
    insufficient_kinds: tuple[str, ...],
    upgrade_rules: Mapping[str, Mapping[str, object]],
    all_branches: bool = True,
    label: str = "app_review_screening",
) -> tuple[list[dict], list[dict], list[str]]:
    """观察筛选 → (候选行, 分支汇总行, 违例)。

    观察必需键：branch（本域分支之一）、applicability；可选：
    observation_schema_version（缺失按当前版本，显式不符记违例）、endpoint/
    object_ref/source/evidence/evidence_ref/reason/precondition/status_hint。
    not_applicable 观察必须带 reason（coverage_substatus_schema 不变量）。
    """
    rows: list[dict] = []
    na_counts: dict[str, int] = {}
    na_reasons: dict[str, list[str]] = {}
    applicable_counts_acc: dict[str, int] = {}
    unknown_counts_acc: dict[str, int] = {}
    violations: list[str] = []
    for index, observation in enumerate(observations, start=1):
        if not isinstance(observation, Mapping):
            violations.append(f"{label}: 第 {index} 条观察必须是键值映射")
            continue
        obs_version = observation.get("observation_schema_version")
        if obs_version is not None and str(obs_version) != ic.OBSERVATION_SCHEMA_VERSION:
            violations.append(
                f"{label}: 第 {index} 条观察 observation_schema_version={obs_version!r} "
                f"与当前版本 {ic.OBSERVATION_SCHEMA_VERSION!r} 不符"
            )
        branch = str(observation.get("branch") or "")
        if branch not in branches:
            violations.append(
                f"{label}: 第 {index} 条观察 branch 非法 {branch!r}（允许值 {list(branches)}）"
            )
            continue
        applicability = str(observation.get("applicability") or "unknown")
        if applicability not in ic.APPLICABLE_VALUES:
            violations.append(
                f"{label}: 第 {index} 条观察 applicability 非法 {applicability!r}"
                f"（允许值 {list(ic.APPLICABLE_VALUES)}）"
            )
            continue
        reason = str(observation.get("reason") or "").strip()
        if applicability == "not_applicable":
            na_counts[branch] = na_counts.get(branch, 0) + 1
            if reason:
                na_reasons.setdefault(branch, []).append(reason)
            else:
                violations.append(
                    f"{label}: 第 {index} 条观察 branch={branch} not_applicable 但 reason 为空"
                    "（没有理由的 not_applicable 是违例，coverage_substatus_schema 不变量）"
                )
            continue
        if applicability == "applicable":
            applicable_counts_acc[branch] = applicable_counts_acc.get(branch, 0) + 1
        else:
            unknown_counts_acc[branch] = unknown_counts_acc.get(branch, 0) + 1
        kinds = derive_app_evidence_kinds(observation.get("evidence") or {}, observation_evidence_map)
        status = grade_app_observation(
            branch,
            kinds,
            upgrade_rules,
            evidence_kinds_all,
            insufficient_kinds,
            str(observation.get("status_hint") or "") or None,
        )
        source = str(observation.get("source") or "").strip()
        if not source:
            violations.append(f"{label}: 第 {index} 条观察缺少来源 source")
        row = {
            "row_id": f"{label.split('.')[-1]}-{index:04d}",
            "branch": branch,
            "status": status,
            "evidence_kinds": kinds,
            "source": source,
            "evidence_ref": str(observation.get("evidence_ref") or ""),
            "precondition": str(observation.get("precondition") or ""),
            "reason": reason,
        }
        rows.append(row)
        violations += validate_app_review_row(
            row,
            branches,
            evidence_kinds_all,
            insufficient_kinds,
            upgrade_rules,
            label=f"{label}[{row['row_id']}]",
        )

    summary_branches = (
        list(branches)
        if all_branches
        else sorted(
            {str(r["branch"]) for r in rows}
            | set(na_counts)
            | set(applicable_counts_acc)
            | set(unknown_counts_acc)
        )
    )
    summaries: list[dict] = []
    for branch in summary_branches:
        branch_rows = [r for r in rows if r["branch"] == branch]
        status_counts = {s: 0 for s in ic.CANDIDATE_STATUS_VALUES}
        for r in branch_rows:
            status_counts[r["status"]] += 1
        applicability_counts = {
            "applicable": applicable_counts_acc.get(branch, 0),
            "not_applicable": na_counts.get(branch, 0),
            "unknown": unknown_counts_acc.get(branch, 0),
        }
        tested_count = sum(status_counts[s] for s in ic.DEFINITIVE_RESULT_STATUSES)
        branch_status = ic.aggregate_category_status(
            [r["status"] for r in branch_rows], na_counts.get(branch, 0) > 0
        )
        reasons = [str(r.get("reason") or "") for r in branch_rows if r.get("reason")]
        if na_reasons.get(branch):
            reasons += na_reasons[branch]
        summaries.append(
            {
                "branch": branch,
                "branch_status": branch_status,
                "applicability_counts": applicability_counts,
                "status_counts": status_counts,
                "tested_count": tested_count,
                "reason": "; ".join(reasons[:1]) if reasons else "本次筛选无该分支升级观察",
                "source": next((str(r["source"]) for r in branch_rows if r.get("source")), ""),
                "precondition": next(
                    (str(r["precondition"]) for r in branch_rows if r.get("precondition")), ""
                ),
            }
        )
        violations += validate_app_branch_summary(
            summaries[-1], branches, label=f"{label}.summary[{branch}]"
        )
    return rows, summaries, violations


def derive_substatuses(summaries: Iterable[Mapping[str, object]]) -> dict[str, str]:
    """分支汇总 → phase substatuses 投影（branch_status 六值；approval_required 仅
    由复核显式设置，聚合不产生）。"""
    return {str(s["branch"]): str(s["branch_status"]) for s in summaries}


def build_app_review_artifact(
    contract: str,
    schema_version: str,
    phase: str,
    rows: Iterable[Mapping[str, object]],
    summaries: Iterable[Mapping[str, object]],
    violations: Iterable[str],
    authorization_basis: str,
    updated_at: str,
    substatuses: Mapping[str, str] | None = None,
) -> dict:
    """契约形状 artifact dict（12 键；contract/schema_version 经参数传入，供
    app 契约族各域复用同一构建实现）。"""
    summary_list = [dict(s) for s in summaries]
    return {
        "schema_version": schema_version,
        "contract": contract,
        "phase": phase,
        "observation_schema_version": ic.OBSERVATION_SCHEMA_VERSION,
        "row_fields": list(APP_REVIEW_ROW_FIELDS),
        "summary_fields": list(APP_REVIEW_SUMMARY_FIELDS),
        "substatuses": dict(substatuses) if substatuses is not None else derive_substatuses(summary_list),
        "rows": [dict(r) for r in rows],
        "summaries": summary_list,
        "violations": list(violations),
        "authorization_basis": authorization_basis,
        "updated_at": updated_at,
    }


def validate_app_review_artifact(
    artifact: Mapping[str, object],
    contract: str,
    schema_version: str,
    phase: str,
    branches: tuple[str, ...],
    evidence_kinds_all: tuple[str, ...],
    insufficient_kinds: tuple[str, ...],
    upgrade_rules: Mapping[str, Mapping[str, object]],
    label: str = "app_review_artifact",
) -> list[str]:
    """契约形状 artifact 校验（与 skill audit 语义一致；模块侧供会话落盘前自检）。"""
    violations: list[str] = []
    if not isinstance(artifact, Mapping):
        return [f"{label}: artifact 必须是键值映射"]
    for key in APP_REVIEW_ARTIFACT_KEYS:
        if key not in artifact:
            violations.append(f"{label}: 缺少必需键 {key}")
    if str(artifact.get("contract") or "") != contract:
        violations.append(f"{label}: contract 必须为 {contract}")
    if str(artifact.get("phase") or "") != phase:
        violations.append(f"{label}: phase 必须为 {phase}，实际 {artifact.get('phase')!r}")
    if str(artifact.get("schema_version") or "") != schema_version:
        violations.append(f"{label}: schema_version 必须为 {schema_version}")
    basis = str(artifact.get("authorization_basis") or "").strip()
    if basis and basis not in APP_AUTHORIZATION_BASIS_VALUES:
        violations.append(
            f"{label}: authorization_basis {basis!r} 非法"
            f"（允许值 {list(APP_AUTHORIZATION_BASIS_VALUES)}）"
        )
    substatuses = artifact.get("substatuses")
    if not isinstance(substatuses, dict):
        violations.append(f"{label}: substatuses 必须为键值对象")
    else:
        for key, value in substatuses.items():
            if str(key) not in branches:
                violations.append(f"{label}.substatuses 未知分支: {key!r}")
            if str(value).strip() and str(value) not in ic.CATEGORY_STATUS_VALUES:
                violations.append(
                    f"{label}.substatuses.{key} 非法: {value!r}"
                    f"（允许值 {list(ic.CATEGORY_STATUS_VALUES)}）"
                )
    rows = artifact.get("rows")
    if not isinstance(rows, list):
        violations.append(f"{label}: rows 必须为列表")
    else:
        for row in rows:
            violations += validate_app_review_row(
                row,
                branches,
                evidence_kinds_all,
                insufficient_kinds,
                upgrade_rules,
                label=f"{label}.rows",
            )
    summaries = artifact.get("summaries")
    if not isinstance(summaries, list):
        violations.append(f"{label}: summaries 必须为列表")
    else:
        for summary in summaries:
            violations += validate_app_branch_summary(
                summary, branches, label=f"{label}.summaries"
            )
    return violations
