"""APP 平台登录交换复核域（施工方案 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §4 阶段
17 + §5.3，批次 B6/W19 收尾；契约 contracts/app_auth_schema.json 的
platform_login_exchange phase）。

只读离线：复用本包共享引擎 app_review_common（B5 落地：观察键→证据形态确定性映射
→rule_satisfied 升级判定→8 状态分级、confirm 升级门），本模块只定义 App 语境的
平台登录分支/证据形态/观察映射/升级规则常量与筛选入口。不发任何请求、不创建/滥用
登录凭证（契约 red_lines："仅在有人工提供的授权材料或本地流量时分析，不自动创建
或滥用登录凭证"）。观察输入为复核会话从操作员提供的授权材料或本地流量（HAR/抓包
导出/设备端导出）提炼的结构化记录。

App 语境五分支（与 contracts/app_auth_schema.json
phases.platform_login_exchange.branches、app init/audit 种子三方同源；方案 §4
阶段 17 覆盖清单：OAuth 授权码 code 一次性和过期；运营商一键登录（预取号 token/
本机号码一键授权）与设备绑定；access_token 保管边界；uid/手机号是否被错误当成
授权依据）：
- oauth_code_one_time：OAuth 授权码一次性（同一 code 二次兑换）；
- oauth_code_expiry：授权码过期（过期 code 仍可兑换）；
- one_click_login_device_binding：运营商一键登录与设备绑定（预取号 token 跨设备
  /绑定缺失）；
- access_token_custody：access_token 保管（是否只在安全存储与服务端，是否落入
  日志/剪贴板/普通存储）；
- uid_authorization_basis：uid/手机号被错误当成授权依据。

升级边界（实现定义供操作者复核）：仅对应分支的确认证据（*_confirmed，来自既有
只读证据的复核判定且可复现）可升级 candidate；"兑换被接受/TTL 或绑定标记存在/
客户端可见线索"等形态与支持性观察永不升级（signal 不是漏洞）。uid/手机号与公开
设备标识不是授权依据（契约 red_lines）。confirmed 五门判定仍归
finding_quality_gate；本模块只做候选层分级校验。

与 xcx 分支常量不同（wx.login code 语境换 App OAuth/一键登录语境），按方案 §5.3
复用边界自包含定义常量，不 import miniapp 常量。
"""
from __future__ import annotations

from typing import Iterable, Mapping

from authorized_assessment.app import app_review_common as arc

# 契约标识与版本（app_auth_schema.schema_version/contract 同源）。
APP_AUTH_CONTRACT = "app_auth_schema"
APP_AUTH_SCHEMA_VERSION = "1.0"

# 认证拆分三 phase 与产物路径（app_auth_schema.phases 键序、app init
# REVIEW_JSON_ARTIFACTS/AUTH_REVIEW_BRANCHES、audit 常量三方同源）。
AUTH_PHASES: tuple[str, ...] = (
    "platform_login_exchange",
    "session_token_lifecycle",
    "signature_replay",
)
AUTH_REVIEW_ARTIFACTS: dict[str, str] = {
    "platform_login_exchange": "artifacts/app/auth/platform-login-review.json",
    "session_token_lifecycle": "artifacts/app/auth/session-lifecycle-review.json",
    "signature_replay": "artifacts/app/auth/signature-replay-review.json",
}

# phase 与产物路径（本模块承载 platform_login_exchange）。
PLATFORM_LOGIN_PHASE = "platform_login_exchange"
PLATFORM_LOGIN_REVIEW_ARTIFACT = "artifacts/app/auth/platform-login-review.json"

# 五分支（契约 phases.platform_login_exchange.branches、init/audit 种子同源；
# 顺序即契约顺序）。
PLATFORM_LOGIN_BRANCHES: tuple[str, ...] = (
    "oauth_code_one_time",
    "oauth_code_expiry",
    "one_click_login_device_binding",
    "access_token_custody",
    "uid_authorization_basis",
)

# 证据形态（15：10 形态/支持性永不升级 + 5 确认形态与分支一一对应）。
PLATFORM_LOGIN_EVIDENCE_KINDS: tuple[str, ...] = (
    "oauth_code_reuse_accepted_observed",
    "oauth_code_single_use_marker_observed",
    "expired_oauth_code_accepted_observed",
    "oauth_code_ttl_marker_observed",
    "one_click_token_client_visible_observed",
    "device_binding_marker_observed",
    "access_token_plain_storage_clue_observed",
    "access_token_log_exposure_clue_observed",
    "uid_as_authz_observed",
    "device_id_as_authz_observed",
    "oauth_code_replay_confirmed",
    "expired_oauth_code_exchange_confirmed",
    "one_click_token_cross_device_confirmed",
    "access_token_custody_breach_confirmed",
    "uid_authz_bypass_confirmed",
)

# "不算漏洞"证据形态：仅形态/支持性观察，未证明服务端认证边界失效。
PLATFORM_LOGIN_INSUFFICIENT_KINDS: tuple[str, ...] = (
    "oauth_code_reuse_accepted_observed",
    "oauth_code_single_use_marker_observed",
    "expired_oauth_code_accepted_observed",
    "oauth_code_ttl_marker_observed",
    "one_click_token_client_visible_observed",
    "device_binding_marker_observed",
    "access_token_plain_storage_clue_observed",
    "access_token_log_exposure_clue_observed",
    "uid_as_authz_observed",
    "device_id_as_authz_observed",
)

# 升级规则（实现定义，固定语义；确认形态与分支一一对应、不跨分支升级）：
# "确认"语义要求观察来自既有只读证据的复核判定且可复现；禁止为取得确认而真实
# 登录、重放授权码、跨设备取号或绕过绑定（契约 red_lines，precondition 必须留痕）。
PLATFORM_LOGIN_UPGRADE_RULES: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "oauth_code_one_time": {"required_any_groups": (("oauth_code_replay_confirmed",),)},
    "oauth_code_expiry": {
        "required_any_groups": (("expired_oauth_code_exchange_confirmed",),)
    },
    "one_click_login_device_binding": {
        "required_any_groups": (("one_click_token_cross_device_confirmed",),)
    },
    "access_token_custody": {
        "required_any_groups": (("access_token_custody_breach_confirmed",),)
    },
    "uid_authorization_basis": {
        "required_any_groups": (("uid_authz_bypass_confirmed",),)
    },
}

# v1 观察键 → 证据形态（确定性映射；版本化演进同 OBSERVATION_SCHEMA_VERSION）。
PLATFORM_LOGIN_OBSERVATION_EVIDENCE_MAP: dict[str, str] = {
    key: key for key in PLATFORM_LOGIN_EVIDENCE_KINDS
}

PLATFORM_LOGIN_OBSERVATION_FIELD_DOCS: dict[str, str] = {
    "oauth_code_reuse_accepted_observed": "观察到同一 OAuth 授权码的二次兑换被服务端"
    "接受（仅形态，不代表边界失效）",
    "oauth_code_single_use_marker_observed": "客户端代码/配置显示授权码一次性使用标记"
    "（支持性，正向线索）",
    "expired_oauth_code_accepted_observed": "观察到过期授权码兑换被接受（仅形态）",
    "oauth_code_ttl_marker_observed": "观察到授权码 TTL/有效期标记（支持性，正向线索）",
    "one_click_token_client_visible_observed": "观察到运营商一键登录预取号 token 客户端"
    "可见线索（仅形态）",
    "device_binding_marker_observed": "观察到设备绑定/本机号码校验标记（支持性，正向"
    "线索）",
    "access_token_plain_storage_clue_observed": "观察到 access_token 落入普通存储/"
    "剪贴板线索（仅形态）",
    "access_token_log_exposure_clue_observed": "观察到 access_token 出现在日志/调试输出"
    "线索（仅形态）",
    "uid_as_authz_observed": "观察到 uid/手机号被用作服务端授权判定线索（仅形态）",
    "device_id_as_authz_observed": "观察到公开设备标识（Android ID/IDFA/IDFV）被用作"
    "授权判定线索（仅形态）",
    "oauth_code_replay_confirmed": "已确认同一授权码可重复兑换出有效会话（既有只读"
    "证据复核且可复现；不重放授权码）",
    "expired_oauth_code_exchange_confirmed": "已确认过期授权码仍可兑换出有效会话"
    "（既有只读证据复核且可复现）",
    "one_click_token_cross_device_confirmed": "已确认一键登录 token 可跨设备/跨号码"
    "使用或绑定校验缺失可复现（既有只读证据复核且可复现；不自动取号或换卡）",
    "access_token_custody_breach_confirmed": "已确认 access_token 离开安全存储与服务端"
    "边界（落入日志/剪贴板/普通存储且可被读取，既有只读证据复核且可复现；不复制"
    "token 原文）",
    "uid_authz_bypass_confirmed": "已确认替换/伪造 uid 或手机号可获得越权访问（既有"
    "只读证据复核且可复现；不自动创建或滥用登录凭证）",
}

# 红线常量（契约 app_auth_schema.red_lines 同源；写入 artifact 与候选 precondition）。
APP_NO_CREDENTIAL_CREATION_RULE: str = (
    "仅在有人工提供的授权材料或本地流量时分析，不自动创建或滥用登录凭证"
)
APP_DEVICE_IDENTITY_CREDENTIAL_RULE: str = (
    "运营商一键登录 token、device-id、Android ID/IDFA/IDFV 等设备与凭证标识属凭证"
    "纪律范围，不进报告/ledger/日志样例/prompt/截图/交接内容"
)
UID_NOT_AUTHORIZATION_RULE: str = (
    "uid/手机号/公开设备标识不是授权依据，不得作为授权判定"
)

# 引擎不变量（契约 invariants/red_lines 的引擎侧锚点；测试与文档引用）。
PLATFORM_LOGIN_INVARIANTS: tuple[str, ...] = (
    "观察输入只能是操作员提供的授权材料或本地流量，不自动创建或滥用登录凭证",
    "设备与凭证标识（一键登录 token/device-id/Android ID/IDFA/IDFV）不进报告/ledger/"
    "日志样例/prompt/截图/交接内容",
    "uid/手机号/公开设备标识不是授权依据；仅 *_confirmed（既有只读证据复核且可复现）"
    "可升级 candidate",
    "confirmed 仍归漏洞成立五门判定；本引擎只做候选层分级校验，duplicate_execution=false",
)


def screen_platform_login_observations(
    observations: Iterable[Mapping[str, object]],
    all_branches: bool = True,
    label: str = "platform_login_exchange",
) -> tuple[list[dict], list[dict], list[str]]:
    """平台登录交换复核筛选 → (候选行, 分支汇总行, 违例)。"""
    return arc.screen_app_observations(
        observations,
        PLATFORM_LOGIN_BRANCHES,
        PLATFORM_LOGIN_OBSERVATION_EVIDENCE_MAP,
        PLATFORM_LOGIN_EVIDENCE_KINDS,
        PLATFORM_LOGIN_INSUFFICIENT_KINDS,
        PLATFORM_LOGIN_UPGRADE_RULES,
        all_branches=all_branches,
        label=label,
    )


def validate_platform_login_candidate(
    row: Mapping[str, object], label: str = "platform_login_candidate"
) -> list[str]:
    return arc.validate_app_review_row(
        row,
        PLATFORM_LOGIN_BRANCHES,
        PLATFORM_LOGIN_EVIDENCE_KINDS,
        PLATFORM_LOGIN_INSUFFICIENT_KINDS,
        PLATFORM_LOGIN_UPGRADE_RULES,
        label=label,
    )


def build_platform_login_review_artifact(
    rows: Iterable[Mapping[str, object]],
    summaries: Iterable[Mapping[str, object]],
    violations: Iterable[str],
    authorization_basis: str,
    updated_at: str,
    substatuses: Mapping[str, str] | None = None,
) -> dict:
    """12 键 platform-login-review.json 产物（契约 artifact_fields 形状）。"""
    return arc.build_app_review_artifact(
        APP_AUTH_CONTRACT,
        APP_AUTH_SCHEMA_VERSION,
        PLATFORM_LOGIN_PHASE,
        rows,
        summaries,
        violations,
        authorization_basis,
        updated_at,
        substatuses=substatuses,
    )


def validate_platform_login_review_artifact(
    artifact: Mapping[str, object], label: str = "platform_login_review_artifact"
) -> list[str]:
    """落盘前自检（与 skill audit 的产物校验语义一致）。"""
    return arc.validate_app_review_artifact(
        artifact,
        APP_AUTH_CONTRACT,
        APP_AUTH_SCHEMA_VERSION,
        PLATFORM_LOGIN_PHASE,
        PLATFORM_LOGIN_BRANCHES,
        PLATFORM_LOGIN_EVIDENCE_KINDS,
        PLATFORM_LOGIN_INSUFFICIENT_KINDS,
        PLATFORM_LOGIN_UPGRADE_RULES,
        label=label,
    )


def _cli() -> int:
    """离线 CLI：观察 JSON 文件 → auth review artifact JSON（纯文件到文件）。"""
    import argparse
    import json
    from datetime import datetime
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Offline app platform login exchange review "
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
    rows, summaries, violations = screen_platform_login_observations(observations)
    artifact = build_platform_login_review_artifact(
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
