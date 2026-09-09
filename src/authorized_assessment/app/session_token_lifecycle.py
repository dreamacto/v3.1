"""APP 会话 token 生命周期复核域（施工方案 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §4
阶段 18 + §5.3，批次 B6/W19 收尾；契约 contracts/app_auth_schema.json 的
session_token_lifecycle phase）。

只读离线：复用本包共享引擎 app_review_common（B5 落地），本模块只定义 token 生命
周期分支/证据形态/观察映射/升级规则常量与筛选入口。不发任何请求、不自动登录、不
申请或续期凭证（契约 red_lines："仅在有人工提供的授权材料或本地流量时分析，不自动
创建或滥用登录凭证"）。观察输入为复核会话从操作员提供的授权材料或本地流量提炼的
结构化记录。

五分支（与 contracts/app_auth_schema.json phases.session_token_lifecycle.branches、
app init/audit 种子三方同源；分支名与 xcx 同名同义，方案 §5.3"引擎可直接薄封装
复用"——常量按复用边界在本包自包含定义，不 import miniapp 常量）：
- token_rotation：token 轮换（refresh/轮换后旧 token 是否失效）；
- token_revocation_logout：失效与注销（吊销/注销后 token 是否仍可用）；
- multi_device_login：多设备登录（并发会话是否受控可管理）；
- stale_token_new_api：旧 token 对新版本接口（版本演进后旧凭证边界）；
- device_user_tenant_binding：设备/用户/租户绑定（token 上下文绑定）。

升级边界（实现定义供操作者复核）：仅对应分支的确认证据（*_confirmed，来自既有
只读证据的复核判定且可复现）可升级 candidate；"请求被接受/机制标记存在/绑定缺失
线索"等形态与支持性观察永不升级（signal 不是漏洞）。旧 token 对新接口的验证只做
既有证据复核，不自动发送写请求（写操作归审批门）。confirmed 五门判定仍归
finding_quality_gate；本模块只做候选层分级校验。
"""
from __future__ import annotations

from typing import Iterable, Mapping

from authorized_assessment.app import app_review_common as arc
from authorized_assessment.app.platform_login_exchange import (
    APP_AUTH_CONTRACT,
    APP_AUTH_SCHEMA_VERSION,
)

# phase 与产物路径（契约 phases.session_token_lifecycle.artifact、init/audit 种子
# 三方同源）。
SESSION_TOKEN_PHASE = "session_token_lifecycle"
SESSION_TOKEN_REVIEW_ARTIFACT = "artifacts/app/auth/session-lifecycle-review.json"

# 五分支（契约 phases.session_token_lifecycle.branches 同源）。
SESSION_TOKEN_BRANCHES: tuple[str, ...] = (
    "token_rotation",
    "token_revocation_logout",
    "multi_device_login",
    "stale_token_new_api",
    "device_user_tenant_binding",
)

# 证据形态（14：9 形态/支持性永不升级 + 5 确认形态与分支一一对应；与 xcx 同名
# 同义，token 生命周期语义平台无关）。
SESSION_TOKEN_EVIDENCE_KINDS: tuple[str, ...] = (
    "token_reuse_after_refresh_observed",
    "rotation_marker_observed",
    "logout_token_accepted_observed",
    "revocation_endpoint_marker_observed",
    "concurrent_session_clue_observed",
    "device_list_marker_observed",
    "stale_token_accepted_observed",
    "binding_absent_observed",
    "binding_marker_observed",
    "stale_token_after_rotation_confirmed",
    "revoked_token_usable_confirmed",
    "uncontrolled_device_session_confirmed",
    "stale_token_privilege_confirmed",
    "cross_tenant_token_use_confirmed",
)

# "不算漏洞"证据形态：仅形态/支持性观察，未证明服务端生命周期边界失效。
SESSION_TOKEN_INSUFFICIENT_KINDS: tuple[str, ...] = (
    "token_reuse_after_refresh_observed",
    "rotation_marker_observed",
    "logout_token_accepted_observed",
    "revocation_endpoint_marker_observed",
    "concurrent_session_clue_observed",
    "device_list_marker_observed",
    "stale_token_accepted_observed",
    "binding_absent_observed",
    "binding_marker_observed",
)

# 升级规则（实现定义，固定语义；确认形态与分支一一对应、不跨分支升级）：
# "确认"语义要求观察来自既有只读证据的复核判定且可复现；禁止为取得确认而自动
# 登录/续期/重放 token 或发送写请求（写操作归审批门，precondition 必须留痕）。
SESSION_TOKEN_UPGRADE_RULES: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "token_rotation": {
        "required_any_groups": (("stale_token_after_rotation_confirmed",),)
    },
    "token_revocation_logout": {
        "required_any_groups": (("revoked_token_usable_confirmed",),)
    },
    "multi_device_login": {
        "required_any_groups": (("uncontrolled_device_session_confirmed",),)
    },
    "stale_token_new_api": {
        "required_any_groups": (("stale_token_privilege_confirmed",),)
    },
    "device_user_tenant_binding": {
        "required_any_groups": (("cross_tenant_token_use_confirmed",),)
    },
}

# v1 观察键 → 证据形态（确定性映射；版本化演进同 OBSERVATION_SCHEMA_VERSION）。
SESSION_TOKEN_OBSERVATION_EVIDENCE_MAP: dict[str, str] = {
    key: key for key in SESSION_TOKEN_EVIDENCE_KINDS
}

SESSION_TOKEN_OBSERVATION_FIELD_DOCS: dict[str, str] = {
    "token_reuse_after_refresh_observed": "观察到 refresh/轮换后旧 token 仍被用于请求"
    "（仅形态，不代表旧 token 长期有效）",
    "rotation_marker_observed": "观察到轮换机制标记（refresh_token/rotation 字段等，"
    "支持性，正向线索）",
    "logout_token_accepted_observed": "观察到注销后 token 请求仍被接受（仅形态）",
    "revocation_endpoint_marker_observed": "观察到吊销/注销端点标记（支持性，正向线索）",
    "concurrent_session_clue_observed": "观察到并发/多设备会话线索（仅形态）",
    "device_list_marker_observed": "观察到设备管理/登录设备列表标记（支持性，正向线索）",
    "stale_token_accepted_observed": "观察到旧版本 token 对新版本接口被接受（仅形态）",
    "binding_absent_observed": "未见设备/用户/租户绑定校验线索（缺失≠不存在，仅形态）",
    "binding_marker_observed": "观察到绑定校验标记（支持性，正向线索）",
    "stale_token_after_rotation_confirmed": "已确认 refresh/轮换后旧 token 长期有效"
    "（既有只读证据复核且可复现；不自动登录或续期凭证）",
    "revoked_token_usable_confirmed": "已确认吊销/注销后 token 仍可访问授权数据（既有"
    "只读证据复核且可复现；不重放写请求）",
    "uncontrolled_device_session_confirmed": "已确认新设备登录后旧设备会话不受控且"
    "不可注销（既有只读证据复核且可复现）",
    "stale_token_privilege_confirmed": "已确认旧 token 在新版本接口保有超出其应得的"
    "权限（既有只读证据复核且可复现；不自动发送写请求）",
    "cross_tenant_token_use_confirmed": "已确认 token 跨租户/用户上下文使用可复现"
    "（既有只读证据复核且可复现）",
}

# 红线常量（契约 red_lines + 审批门语义；写入 artifact 与候选 precondition）。
TOKEN_REVIEW_MATERIAL_RULE: str = (
    "token 生命周期分析仅使用操作员提供的授权材料或本地流量；不自动登录、不申请"
    "或续期凭证"
)
NO_TOKEN_WRITE_REPLAY_RULE: str = (
    "旧 token 对新接口/注销边界只做既有只读证据复核；不自动发送写请求，写操作"
    "归审批门"
)

# 引擎不变量（契约 invariants/red_lines 的引擎侧锚点；测试与文档引用）。
SESSION_TOKEN_INVARIANTS: tuple[str, ...] = (
    "观察输入只能是操作员提供的授权材料或本地流量，不自动登录、不申请或续期凭证",
    "旧 token 对新接口/注销边界只做既有只读证据复核；不自动发送写请求",
    "仅 *_confirmed（既有只读证据复核且可复现）可升级 candidate；confirmed 仍归漏洞"
    "成立五门判定",
    "本引擎只消费既有证据做候选层筛选，duplicate_execution=false",
)


def screen_session_token_observations(
    observations: Iterable[Mapping[str, object]],
    all_branches: bool = True,
    label: str = "session_token_lifecycle",
) -> tuple[list[dict], list[dict], list[str]]:
    """会话 token 生命周期复核筛选 → (候选行, 分支汇总行, 违例)。"""
    return arc.screen_app_observations(
        observations,
        SESSION_TOKEN_BRANCHES,
        SESSION_TOKEN_OBSERVATION_EVIDENCE_MAP,
        SESSION_TOKEN_EVIDENCE_KINDS,
        SESSION_TOKEN_INSUFFICIENT_KINDS,
        SESSION_TOKEN_UPGRADE_RULES,
        all_branches=all_branches,
        label=label,
    )


def validate_session_token_candidate(
    row: Mapping[str, object], label: str = "session_token_candidate"
) -> list[str]:
    return arc.validate_app_review_row(
        row,
        SESSION_TOKEN_BRANCHES,
        SESSION_TOKEN_EVIDENCE_KINDS,
        SESSION_TOKEN_INSUFFICIENT_KINDS,
        SESSION_TOKEN_UPGRADE_RULES,
        label=label,
    )


def build_session_token_review_artifact(
    rows: Iterable[Mapping[str, object]],
    summaries: Iterable[Mapping[str, object]],
    violations: Iterable[str],
    authorization_basis: str,
    updated_at: str,
    substatuses: Mapping[str, str] | None = None,
) -> dict:
    """12 键 session-lifecycle-review.json 产物（契约 artifact_fields 形状）。"""
    return arc.build_app_review_artifact(
        APP_AUTH_CONTRACT,
        APP_AUTH_SCHEMA_VERSION,
        SESSION_TOKEN_PHASE,
        rows,
        summaries,
        violations,
        authorization_basis,
        updated_at,
        substatuses=substatuses,
    )


def validate_session_token_review_artifact(
    artifact: Mapping[str, object], label: str = "session_token_review_artifact"
) -> list[str]:
    """落盘前自检（与 skill audit 的产物校验语义一致）。"""
    return arc.validate_app_review_artifact(
        artifact,
        APP_AUTH_CONTRACT,
        APP_AUTH_SCHEMA_VERSION,
        SESSION_TOKEN_PHASE,
        SESSION_TOKEN_BRANCHES,
        SESSION_TOKEN_EVIDENCE_KINDS,
        SESSION_TOKEN_INSUFFICIENT_KINDS,
        SESSION_TOKEN_UPGRADE_RULES,
        label=label,
    )


def _cli() -> int:
    """离线 CLI：观察 JSON 文件 → auth review artifact JSON（纯文件到文件）。"""
    import argparse
    import json
    from datetime import datetime
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Offline app session token lifecycle review "
        "(no network, no credential use)."
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
    rows, summaries, violations = screen_session_token_observations(observations)
    artifact = build_session_token_review_artifact(
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
