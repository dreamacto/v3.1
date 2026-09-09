"""APP 密码学与密钥处理复核域（施工方案 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §4
阶段 25 + §5.3，批次 B6/W19 收尾；契约 contracts/app_storage_package_schema.json 的
crypto_and_secret_handling phase）。

只读离线：复用本包共享引擎 app_review_common（B5 落地）与 local_data_exposure
承载的"行内 platform 列"筛选助手（storage 两 phase 同款形状），本模块只定义密码学
与密钥处理分支/证据形态/观察映射/升级规则常量与筛选入口。不发任何请求、不读取
凭证文件、不复制密钥/AppSecret 原文到普通日志/报告/prompt/ledger/交接内容；不做
密钥有效性的主动验证——有效性确认只来自既有只读证据（包源码/清单/本地流量）的
复核（红线常量留痕）。

四分支（与 contracts/app_storage_package_schema.json
phases.crypto_and_secret_handling.branches、app init/audit 种子三方同源；分支名与
xcx 同名同义，xcx 侧后续增补的被动泄露面分支不在 APP 契约内，本模块不引入）：
- hardcoded_secrets：AppSecret/AK/SK/jpush/umeng/maps key 等硬编码；
- custom_crypto：自定义加密；
- weak_random_key_derivation：弱随机数、密钥派生；
- debug_config_env_keys：包中调试配置和环境密钥（只覆盖密钥材料暴露面；调试开关
  本身归 package_integrity_hardening_review.debug_switches，契约 invariant 留痕，
  避免重复计数）。

secret_candidate 红线（契约 red_lines 原文语义）："发现密钥字符串但无法证明有效性
时只能是 secret_candidate（未证实线索，8 状态模型记 signal），不能直接称为密钥
泄露漏洞；不做 key 有效性探测、不发请求"。落地方式：secret_candidate 是未证实
线索的台账语义，不是 finding 8 状态（8 状态模型被契约三方锁定，不新增状态）；
未证实密钥字符串在候选层记 status=signal（仅形态观察永不升级），只有密钥有效性
被既有只读证据确认（服务端接受/可达使用点，可复现）才升级 candidate；confirmed
五门判定仍归 finding_quality_gate。
"""
from __future__ import annotations

from typing import Iterable, Mapping

from authorized_assessment.app import app_review_common as arc
from authorized_assessment.app.hardening_integrity_review import (
    APP_STORAGE_PACKAGE_CONTRACT,
    APP_STORAGE_PACKAGE_SCHEMA_VERSION,
)
from authorized_assessment.app.local_data_exposure import (
    screen_platform_tagged_observations,
    validate_platform_tagged_row,
)

# phase 与产物路径（契约 phases.crypto_and_secret_handling.artifact、init/audit
# 种子三方同源）。
CRYPTO_SECRET_PHASE = "crypto_and_secret_handling"
CRYPTO_SECRET_REVIEW_ARTIFACT = "artifacts/app/crypto/secret-review.json"

# 四分支（契约 phases.crypto_and_secret_handling.branches 同源）。
CRYPTO_SECRET_BRANCHES: tuple[str, ...] = (
    "hardcoded_secrets",
    "custom_crypto",
    "weak_random_key_derivation",
    "debug_config_env_keys",
)

# 证据形态（12：8 形态/支持性永不升级 + 4 确认形态与四分支一一对应；与 xcx 同名
# 同义，App 语境覆盖 AK/SK、jpush/umeng/maps key 等移动端密钥形态，经行内 platform
# 列区分 android/ios 包面）。
CRYPTO_SECRET_EVIDENCE_KINDS: tuple[str, ...] = (
    "secret_like_string_observed",
    "secret_reference_marker_observed",
    "custom_crypto_code_observed",
    "custom_crypto_usage_marker_observed",
    "weak_random_call_observed",
    "key_derivation_marker_observed",
    "env_key_in_config_observed",
    "debug_config_key_clue_observed",
    "secret_reachable_confirmed",
    "custom_crypto_bypassable_confirmed",
    "predictable_random_confirmed",
    "env_key_accepted_confirmed",
)

# "不算漏洞"证据形态：仅形态/支持性观察——密钥字符串未经有效性确认时只能是
# secret_candidate（未证实线索，8 状态记 signal），不能直接称为密钥泄露漏洞。
CRYPTO_SECRET_INSUFFICIENT_KINDS: tuple[str, ...] = (
    "secret_like_string_observed",
    "secret_reference_marker_observed",
    "custom_crypto_code_observed",
    "custom_crypto_usage_marker_observed",
    "weak_random_call_observed",
    "key_derivation_marker_observed",
    "env_key_in_config_observed",
    "debug_config_key_clue_observed",
)

# 升级规则（实现定义，固定语义；确认形态与分支一一对应、不跨分支升级）：
# "确认"语义要求观察来自既有只读证据（包源码/清单/本地流量）的复核判定且可
# 复现；不主动验证密钥有效性、不发送请求、不复制密钥原文（precondition 必须
# 留痕）。
CRYPTO_SECRET_UPGRADE_RULES: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "hardcoded_secrets": {
        "required_any_groups": (("secret_reachable_confirmed",),)
    },
    "custom_crypto": {
        "required_any_groups": (("custom_crypto_bypassable_confirmed",),)
    },
    "weak_random_key_derivation": {
        "required_any_groups": (("predictable_random_confirmed",),)
    },
    "debug_config_env_keys": {
        "required_any_groups": (("env_key_accepted_confirmed",),)
    },
}

# v1 观察键 → 证据形态（确定性映射；版本化演进同 OBSERVATION_SCHEMA_VERSION）。
CRYPTO_SECRET_OBSERVATION_EVIDENCE_MAP: dict[str, str] = {
    key: key for key in CRYPTO_SECRET_EVIDENCE_KINDS
}

CRYPTO_SECRET_OBSERVATION_FIELD_DOCS: dict[str, str] = {
    "secret_like_string_observed": "观察到疑似密钥/AppSecret/AK/SK/jpush/umeng/maps "
    "key 等硬编码字符串（仅形态——secret_candidate 线索，未证实有效性不得升级）",
    "secret_reference_marker_observed": "观察到密钥引用/加载点标记（支持性）",
    "custom_crypto_code_observed": "观察到自定义加密实现代码（仅形态）",
    "custom_crypto_usage_marker_observed": "观察到自定义加密调用点标记（支持性）",
    "weak_random_call_observed": "观察到弱随机数调用（固定种子/时间种子/Math.random "
    "等，仅形态）",
    "key_derivation_marker_observed": "观察到密钥派生/固定盐标记（仅形态）",
    "env_key_in_config_observed": "观察到配置中的环境密钥字段（仅形态）",
    "debug_config_key_clue_observed": "观察到调试配置中密钥材料线索（仅形态；调试开关"
    "本身归 package_integrity_hardening_review.debug_switches，不重复计数）",
    "secret_reachable_confirmed": "已确认硬编码密钥被服务端接受或到达可达使用点且"
    "产生实际权限（既有只读证据复核且可复现；不主动验证、不复制密钥原文）",
    "custom_crypto_bypassable_confirmed": "已确认自定义加密可被标准工具复原或绕过"
    "且保护的数据可读（既有只读证据复核且可复现）",
    "predictable_random_confirmed": "已确认随机数/派生输出可预测并影响密钥或凭证"
    "强度（既有只读证据复核且可复现）",
    "env_key_accepted_confirmed": "已确认环境密钥真实有效且被客户端用于敏感决策"
    "（既有只读证据复核且可复现；不主动验证）",
}

# 红线常量（契约 red_lines 原文语义 + 凭证纪律；写入 artifact 与候选 precondition）。
SECRET_CANDIDATE_RED_LINE: str = (
    "发现密钥字符串但无法证明有效性时只能是 secret_candidate（未证实线索，"
    "8 状态模型记 signal），不能直接称为密钥泄露漏洞；不做 key 有效性探测、不发请求"
)
CRYPTO_MATERIAL_RULE: str = (
    "密钥与加密复核仅使用操作员提供的授权材料或包副本的既有只读证据；不主动验证"
    "密钥有效性、不发送请求、不读取凭证文件、不复制密钥/AppSecret 原文到普通日志、"
    "报告、prompt、ledger 或交接内容"
)

# 引擎不变量（契约 invariants/red_lines 的引擎侧锚点；测试与文档引用）。
CRYPTO_SECRET_INVARIANTS: tuple[str, ...] = (
    "secret_candidate 红线：发现密钥字符串但无法证明有效性时只能是 secret_candidate"
    "（未证实线索，8 状态记 signal），不能直接称为密钥泄露漏洞",
    "不做 key 有效性探测、不发请求、不复制密钥/AppSecret 原文到任何输出",
    "行内 platform 列必须区分 android/ios（row 扩展键承载，不破坏 12 键形状）",
    "仅 *_confirmed（既有只读证据复核且可复现）可升级 candidate；confirmed 仍归漏洞"
    "成立五门判定，duplicate_execution=false",
)


def screen_crypto_secret_observations(
    observations: Iterable[Mapping[str, object]],
    all_branches: bool = True,
    label: str = "crypto_and_secret_handling",
) -> tuple[list[dict], list[dict], list[str]]:
    """密码学与密钥处理复核筛选（含行内 platform 列）→ (候选行, 分支汇总行, 违例)。"""
    return screen_platform_tagged_observations(
        observations,
        CRYPTO_SECRET_BRANCHES,
        CRYPTO_SECRET_OBSERVATION_EVIDENCE_MAP,
        CRYPTO_SECRET_EVIDENCE_KINDS,
        CRYPTO_SECRET_INSUFFICIENT_KINDS,
        CRYPTO_SECRET_UPGRADE_RULES,
        all_branches=all_branches,
        label=label,
    )


def validate_crypto_secret_candidate(
    row: Mapping[str, object], label: str = "crypto_secret_candidate"
) -> list[str]:
    return validate_platform_tagged_row(
        row,
        CRYPTO_SECRET_BRANCHES,
        CRYPTO_SECRET_EVIDENCE_KINDS,
        CRYPTO_SECRET_INSUFFICIENT_KINDS,
        CRYPTO_SECRET_UPGRADE_RULES,
        label=label,
    )


def build_crypto_secret_review_artifact(
    rows: Iterable[Mapping[str, object]],
    summaries: Iterable[Mapping[str, object]],
    violations: Iterable[str],
    authorization_basis: str,
    updated_at: str,
    substatuses: Mapping[str, str] | None = None,
) -> dict:
    """12 键 secret-review.json 产物（契约 artifact_fields 形状；行内 platform 为
    row 扩展键，artifact row_fields 仍为契约 8 字段）。"""
    return arc.build_app_review_artifact(
        APP_STORAGE_PACKAGE_CONTRACT,
        APP_STORAGE_PACKAGE_SCHEMA_VERSION,
        CRYPTO_SECRET_PHASE,
        rows,
        summaries,
        violations,
        authorization_basis,
        updated_at,
        substatuses=substatuses,
    )


def validate_crypto_secret_review_artifact(
    artifact: Mapping[str, object], label: str = "crypto_secret_review_artifact"
) -> list[str]:
    """落盘前自检（与 skill audit 的产物校验语义一致；platform 扩展行在行级校验）。"""
    violations = arc.validate_app_review_artifact(
        artifact,
        APP_STORAGE_PACKAGE_CONTRACT,
        APP_STORAGE_PACKAGE_SCHEMA_VERSION,
        CRYPTO_SECRET_PHASE,
        CRYPTO_SECRET_BRANCHES,
        CRYPTO_SECRET_EVIDENCE_KINDS,
        CRYPTO_SECRET_INSUFFICIENT_KINDS,
        CRYPTO_SECRET_UPGRADE_RULES,
        label=label,
    )
    rows = artifact.get("rows") if isinstance(artifact, Mapping) else None
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                violations += validate_crypto_secret_candidate(
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
        description="Offline app crypto and secret handling review (no network, no "
        "credential files, no key value export; unproven secret strings stay "
        "secret_candidate clues)."
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
    rows, summaries, violations = screen_crypto_secret_observations(observations)
    artifact = build_crypto_secret_review_artifact(
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
