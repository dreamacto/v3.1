"""APP 包完整性/加固复核域（施工方案 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §4 阶段
10 + §5.3，批次 B5/W19 中段；契约 contracts/app_storage_package_schema.json 的
package_integrity_hardening_review phase）。

只观察不绕过（红线，契约 red_lines 同源）：本模块只分析操作员提供的包副本与既有
清单/解包证据，不做重打包、篡改、脱壳、绕过 pinning 或设备攻击；任何绕过动作
（脱壳/反调试 patch/SSL pinning bypass/frida 注入/重打包）= device_instrumentation/
app_hardened_unpack 审批门（双钥匙），本模块不提供任何此类能力。加固/壳特征
（附录 F so 文件名前缀表）只记 signal，不构成漏洞结论；"绕过加固"是测试技术不是
漏洞。确认证据只能来自既有只读证据的复核判定且可复现；confirmed 五门判定仍归
finding_quality_gate，本模块只做候选层分级校验。

七分支（与 contracts/app_storage_package_schema.json
phases.package_integrity_hardening_review.branches、app init/audit 种子三方同源）：
- package_version_inventory：安装包与 split/xapk 版本清单；
- signing_integrity：签名/证书完整性（v1/v2/v3 scheme、证书指纹、split 签名一致性）；
- hardening_obfuscation_markers：加固与混淆特征（附录 F 特征只记 signal，永不升级）；
- debug_switches：debuggable/allowBackup 等调试开关；
- debug_info_exposure：日志与调试信息暴露；
- update_endpoint_environment：热更新/dex.zip 下载源与环境切换；
- trusted_update_config：客户端是否信任可控更新配置。

升级边界（实现定义供操作者复核）：仅对应分支的确认证据（*_confirmed）可升级
candidate；"版本标记/签名标记/加固 so 特征/调试标记/更新地址存在"等形态与支持性
观察永不升级（signal 不是漏洞）。hardening_obfuscation_markers 分支无升级规则
（契约描述"加固 so 特征只记 signal，不构成结论"的引擎落点）。

与 xcx package_integrity_update 分支常量不同（新增 signing_integrity/
hardening_obfuscation_markers/debug_info_exposure），复用代码模式而非 import miniapp
常量（方案 §5.3 复用边界）；共享引擎宿主为 app_review_common。
"""
from __future__ import annotations

from typing import Iterable, Mapping

from authorized_assessment.app import app_review_common as arc

# 契约标识与版本（app_storage_package_schema.schema_version/contract 同源）。
APP_STORAGE_PACKAGE_CONTRACT = "app_storage_package_schema"
APP_STORAGE_PACKAGE_SCHEMA_VERSION = "1.0"

# phase 与产物路径（契约 phases.package_integrity_hardening_review.artifact、
# app init/audit 种子三方同源）。
HARDENING_PHASE = "package_integrity_hardening_review"
HARDENING_REVIEW_ARTIFACT = "artifacts/app/package/hardening-review.json"

# 七分支（契约 + init/audit 种子同源；顺序即契约顺序）。
HARDENING_REVIEW_BRANCHES: tuple[str, ...] = (
    "package_version_inventory",
    "signing_integrity",
    "hardening_obfuscation_markers",
    "debug_switches",
    "debug_info_exposure",
    "update_endpoint_environment",
    "trusted_update_config",
)

# 证据形态（20：14 形态/支持性永不升级 + 6 确认形态与可升级分支一一对应；
# hardening_obfuscation_markers 分支只有形态观察——加固 so 特征只记 signal）。
HARDENING_EVIDENCE_KINDS: tuple[str, ...] = (
    "package_version_labels_observed",
    "split_composition_observed",
    "signing_scheme_labels_observed",
    "certificate_fingerprint_observed",
    "packer_so_signature_observed",
    "obfuscation_markers_observed",
    "debuggable_marker_observed",
    "allowbackup_marker_observed",
    "debug_logging_marker_observed",
    "verbose_log_strings_observed",
    "update_address_observed",
    "environment_switch_marker_observed",
    "update_config_reference_observed",
    "remote_config_trust_clue_observed",
    "split_version_divergence_confirmed",
    "split_signature_divergence_confirmed",
    "debug_switch_active_confirmed",
    "debug_info_leak_confirmed",
    "controllable_update_address_confirmed",
    "client_trusts_remote_update_confirmed",
)

# "不算漏洞"证据形态：仅形态/支持性观察，未证明完整性/信任边界失效。
HARDENING_INSUFFICIENT_KINDS: tuple[str, ...] = (
    "package_version_labels_observed",
    "split_composition_observed",
    "signing_scheme_labels_observed",
    "certificate_fingerprint_observed",
    "packer_so_signature_observed",
    "obfuscation_markers_observed",
    "debuggable_marker_observed",
    "allowbackup_marker_observed",
    "debug_logging_marker_observed",
    "verbose_log_strings_observed",
    "update_address_observed",
    "environment_switch_marker_observed",
    "update_config_reference_observed",
    "remote_config_trust_clue_observed",
)

# 升级规则（实现定义，固定语义；确认形态与分支一一对应、不跨分支升级）：
# "确认"语义要求观察来自既有只读证据（包副本/解包产物/清单/流量）的复核判定且
# 可复现；禁止为取得确认而重打包、篡改、脱壳、绕过 pinning 或攻击设备（契约
# red_lines，precondition 必须留痕）。hardening_obfuscation_markers 无规则 =
# 永不升级（契约"加固 so 特征只记 signal"）。
HARDENING_UPGRADE_RULES: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "package_version_inventory": {
        "required_any_groups": (("split_version_divergence_confirmed",),)
    },
    "signing_integrity": {
        "required_any_groups": (("split_signature_divergence_confirmed",),)
    },
    "debug_switches": {
        "required_any_groups": (("debug_switch_active_confirmed",),)
    },
    "debug_info_exposure": {
        "required_any_groups": (("debug_info_leak_confirmed",),)
    },
    "update_endpoint_environment": {
        "required_any_groups": (("controllable_update_address_confirmed",),)
    },
    "trusted_update_config": {
        "required_any_groups": (("client_trusts_remote_update_confirmed",),)
    },
}

# v1 观察键 → 证据形态（确定性映射；版本化演进同 OBSERVATION_SCHEMA_VERSION）。
HARDENING_OBSERVATION_EVIDENCE_MAP: dict[str, str] = {
    key: key for key in HARDENING_EVIDENCE_KINDS
}

HARDENING_OBSERVATION_FIELD_DOCS: dict[str, str] = {
    "package_version_labels_observed": "观察到主包/split/xapk 版本标记（支持性）",
    "split_composition_observed": "观察到 split/xapk 组成与分发渠道（支持性）",
    "signing_scheme_labels_observed": "观察到 v1/v2/v3 签名 scheme 标记（仅形态）",
    "certificate_fingerprint_observed": "观察到证书指纹/主体信息（仅形态）",
    "packer_so_signature_observed": "观察到加固壳 so 特征（附录 F 前缀表命中；只记"
    " signal，新版壳可能改名或 VMP 化导致特征失效，需以 DEX 结构特征复核）",
    "obfuscation_markers_observed": "观察到混淆/优化标记（ProGuard/R8 mapping 缺失"
    "等，仅形态）",
    "debuggable_marker_observed": "观察到 debuggable 标记（仅形态）",
    "allowbackup_marker_observed": "观察到 allowBackup=true 标记（仅形态）",
    "debug_logging_marker_observed": "观察到调试日志开关标记（仅形态）",
    "verbose_log_strings_observed": "观察到冗长日志/调试字符串残留（仅形态）",
    "update_address_observed": "观察到热更新/dex.zip 下载地址（支持性）",
    "environment_switch_marker_observed": "观察到测试/预发/正式环境切换标记（仅形态）",
    "update_config_reference_observed": "观察到更新配置引用/加载点（支持性）",
    "remote_config_trust_clue_observed": "观察到远程配置影响客户端行为线索（仅形态）",
    "split_version_divergence_confirmed": "已确认 split/子包与主包版本不一致且加载"
    "行为受其影响（既有只读证据复核且可复现）",
    "split_signature_divergence_confirmed": "已确认签名 scheme 缺失/降级或 split 间"
    "证书不一致且可复现（既有只读证据复核；不做重签名或篡改验证）",
    "debug_switch_active_confirmed": "已确认发布包调试开关（debuggable/allowBackup/"
    "调试日志）处于可用状态且改变行为（既有只读证据复核且可复现）",
    "debug_info_leak_confirmed": "已确认发布包残留调试信息可被提取且含敏感内容"
    "（既有只读证据复核且可复现）",
    "controllable_update_address_confirmed": "已确认更新/下载地址可被外部内容影响或"
    "指向非预期环境（既有只读证据复核且可复现；不发起请求验证）",
    "client_trusts_remote_update_confirmed": "已确认客户端无条件信任可控更新配置并"
    "据此改变代码/数据流（既有只读证据复核且可复现；不做重打包或篡改验证）",
}

# 红线常量（契约 red_lines 同源；写入 artifact 与候选 precondition 语义）。
APP_NO_REPACKING_RULE: str = (
    "不做重打包、篡改、脱壳、绕过 pinning 或设备攻击；包完整性/加固复核只分析"
    "操作员提供的包副本与既有清单证据，加固特征只记 signal"
)
OBSERVE_ONLY_RULE: str = "只观察不绕过：任何脱壳/反调试 patch/SSL pinning bypass/frida 注入/重打包 = 审批门，绕过是测试技术不是漏洞结论"

# 引擎不变量（契约 invariants 的引擎侧锚点；测试与文档引用）。
HARDENING_INVARIANTS: tuple[str, ...] = (
    "只观察不绕过：观察输入只能是操作员提供的包副本、解包产物与既有清单/流量证据",
    "加固/壳特征（附录 F）只记 signal，永不升级 candidate",
    "确认证据只能来自既有只读证据的复核判定且可复现；confirmed 仍归漏洞成立五门判定",
    "本引擎只消费既有证据做候选层筛选，duplicate_execution=false",
)


def screen_hardening_observations(
    observations: Iterable[Mapping[str, object]],
    all_branches: bool = True,
    label: str = "package_integrity_hardening_review",
) -> tuple[list[dict], list[dict], list[str]]:
    """包完整性/加固复核筛选 → (候选行, 分支汇总行, 违例)。"""
    return arc.screen_app_observations(
        observations,
        HARDENING_REVIEW_BRANCHES,
        HARDENING_OBSERVATION_EVIDENCE_MAP,
        HARDENING_EVIDENCE_KINDS,
        HARDENING_INSUFFICIENT_KINDS,
        HARDENING_UPGRADE_RULES,
        all_branches=all_branches,
        label=label,
    )


def validate_hardening_candidate(
    row: Mapping[str, object], label: str = "hardening_candidate"
) -> list[str]:
    return arc.validate_app_review_row(
        row,
        HARDENING_REVIEW_BRANCHES,
        HARDENING_EVIDENCE_KINDS,
        HARDENING_INSUFFICIENT_KINDS,
        HARDENING_UPGRADE_RULES,
        label=label,
    )


def build_hardening_review_artifact(
    rows: Iterable[Mapping[str, object]],
    summaries: Iterable[Mapping[str, object]],
    violations: Iterable[str],
    authorization_basis: str,
    updated_at: str,
    substatuses: Mapping[str, str] | None = None,
) -> dict:
    """12 键 hardening-review.json 产物（契约 artifact_fields 形状）。"""
    return arc.build_app_review_artifact(
        APP_STORAGE_PACKAGE_CONTRACT,
        APP_STORAGE_PACKAGE_SCHEMA_VERSION,
        HARDENING_PHASE,
        rows,
        summaries,
        violations,
        authorization_basis,
        updated_at,
        substatuses=substatuses,
    )


def validate_hardening_review_artifact(
    artifact: Mapping[str, object], label: str = "hardening_review_artifact"
) -> list[str]:
    """落盘前自检（与 skill audit 的产物校验语义一致）。"""
    return arc.validate_app_review_artifact(
        artifact,
        APP_STORAGE_PACKAGE_CONTRACT,
        APP_STORAGE_PACKAGE_SCHEMA_VERSION,
        HARDENING_PHASE,
        HARDENING_REVIEW_BRANCHES,
        HARDENING_EVIDENCE_KINDS,
        HARDENING_INSUFFICIENT_KINDS,
        HARDENING_UPGRADE_RULES,
        label=label,
    )


def _cli() -> int:
    """离线 CLI：观察 JSON 文件 → hardening review artifact JSON（纯文件到文件）。"""
    import argparse
    import json
    from datetime import datetime
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Offline app package integrity/hardening review "
        "(no network, observe-only: no repacking/tampering/unpacking-bypass)."
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
    rows, summaries, violations = screen_hardening_observations(observations)
    artifact = build_hardening_review_artifact(
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
