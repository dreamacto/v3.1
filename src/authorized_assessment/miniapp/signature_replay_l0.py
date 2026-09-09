"""signature_replay L0 受控重放执行器（WZ/XCX 能力升级 P2 ⑧，方案 §4 X-2，2026-09-07）。

形态对标 batch16 能力模块（plan + ingest 两段式）与 idor_triage 引擎约束。本模块是
"能力模块"：不含任何默认执行路径，plan 模式零网络零执行，重放动作全部由操作者在
Tier C 审批门内手工执行，ingest 只解析操作者手工回填的结构化结果（本模块定义的
契约，不吃自由文本）。

与 signature_replay_review.py（Batch 10 离线评审域）的关系：离线评审只做重放假设
与观察筛选；本模块是其 L0 受控验证层——离线评审筛出的重放假设，经操作者审批后
按本模块的 runbook 手工重放，结果回填 ingest 产出候选行，再走既有 review_ledger /
finding 五门。confirmed 永不由本模块产生。

受控约束（全部硬编码为本模块常量，并与 contracts/miniapp_auth_schema.json
l0_executor 段同源锁定，由 validate_run_contracts.py 与
tests/test_signature_replay_l0.py 双向校验）：
- 单请求重放 1 次：每个时间窗（T+5s / T+60s）对同一请求只重放 1 次，无并发；
- 时间窗对比：原请求（T0 基线）vs T+5s vs T+60s 三窗口观测；
- 只读 GET 型端点：method 必须 GET；endpoint_class 必须 read_only_data；
- 每 host ≤3 端点；连续动作间隔 delay ≥3s；
- write_risk_ack 必须为 false：任何写型/业务型端点永不重放——这是硬红线，
  与 race_triage 的 write_risk_ack==true 人工批准语义相反：本 L0 无审批解锁
  路径，设 true 即拒绝（fail-closed），缺失同样拒绝。

产物：artifacts/miniapp/auth/signature-replay-l0.jsonl（ingest 输出，逐行 JSON）。
"""
from __future__ import annotations

from typing import Iterable, Mapping
from urllib.parse import urlparse

from authorized_assessment.miniapp import platform_login_exchange as auth_engine
from authorized_assessment.triage import response_baseline as rb

SIGNATURE_REPLAY_L0_SCHEMA_VERSION = "1.0"
SIGNATURE_REPLAY_L0_CONTRACT = "miniapp_auth_schema.l0_executor"
SIGNATURE_REPLAY_L0_ARTIFACT = "artifacts/miniapp/auth/signature-replay-l0.jsonl"

# 受控约束常量（契约 l0_executor.constraints 同源）。
L0_ALLOWED_METHODS: tuple[str, ...] = ("GET",)
L0_ENDPOINT_CLASSES: tuple[str, ...] = ("read_only_data", "business_action", "write")
L0_ALLOWED_ENDPOINT_CLASS = "read_only_data"
L0_MAX_ENDPOINTS_PER_HOST = 3
L0_MIN_DELAY_SECONDS = 3.0
L0_TIME_WINDOW_OFFSETS_SECONDS: tuple[int, ...] = (5, 60)
L0_REPLAYS_PER_WINDOW = 1
L0_WRITE_RISK_ACK_MUST_BE = False

# 观测窗口标签：T0 基线 + 两个重放窗。
L0_WINDOW_ORIGINAL = "original"
L0_REPLAY_WINDOW_LABELS: tuple[str, ...] = ("t_plus_5s", "t_plus_60s")
L0_WINDOW_LABELS: tuple[str, ...] = (L0_WINDOW_ORIGINAL,) + L0_REPLAY_WINDOW_LABELS

# 可选响应类别（操作者回填；用于 200-with-error 形态排除，缺省仅按状态+结构指纹判）。
L0_RESPONSE_CLASSES: tuple[str, ...] = (
    "business_success",
    "business_error",
    "auth_required",
    "challenge",
    "other",
)
L0_REJECTED_RESPONSE_CLASSES: tuple[str, ...] = ("business_error", "auth_required", "challenge")

# 重放结果派生枚举与行状态（只产 signal/candidate/inconclusive；confirmed 永不产生）。
L0_REPLAY_OUTCOMES: tuple[str, ...] = (
    "accepted_both_windows",
    "accepted_t5_only",
    "accepted_t60_only",
    "rejected_both_windows",
    "inconclusive",
)
L0_ROW_STATUSES: tuple[str, ...] = ("signal", "candidate", "inconclusive")

# 与离线评审四分支的对接：L0 只服务 replay_window 分支的重放边界判定。
L0_ROW_BRANCH = "replay_window"

# 红线常量（写入 plan 与候选行 precondition）。
L0_NEVER_REPLAY_RULE: str = (
    "写型/业务型端点永不重放（write/business endpoint never replayed）；"
    "write_risk_ack 必须为 false——本 L0 无审批解锁路径，设 true 即拒绝（fail-closed）"
)
L0_MANUAL_EXECUTION_RULE: str = (
    "重放动作全部由操作者手工执行（Tier C 审批门内）；本模块零执行零网络，"
    "plan 只是纯数据 runbook"
)

L0_ROW_REQUIRED_FIELDS = (
    "row_id",
    "url",
    "http_method",
    "branch",
    "status",
    "replay_outcome",
    "windows",
    "source",
    "evidence_ref",
    "reason",
)


def _host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def validate_l0_config(config: Mapping[str, object], label: str = "l0_config") -> list[str]:
    """plan 入口校验：write_risk_ack 红线、方法、端点类别、host 预算。"""
    violations: list[str] = []
    if not isinstance(config, dict):
        return [f"{label}: 配置必须是键值映射"]
    ack = config.get("write_risk_ack", None)
    if ack is True:
        violations.append(
            f"{label}: write_risk_ack=true 被拒绝——{L0_NEVER_REPLAY_RULE}"
        )
    elif ack is not False:
        violations.append(
            f"{label}: write_risk_ack 缺失或非布尔，fail-closed 拒绝（必须显式 false）"
        )
    basis = str(config.get("authorization_basis") or "")
    if basis not in auth_engine.AUTHORIZATION_BASIS_VALUES:
        violations.append(
            f"{label}: authorization_basis 非法 {basis!r}"
            f"（允许值 {list(auth_engine.AUTHORIZATION_BASIS_VALUES)}）"
        )
    endpoints = config.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        violations.append(f"{label}: endpoints 必须为非空列表")
        return violations
    host_counts: dict[str, int] = {}
    seen_urls: set[str] = set()
    for index, endpoint in enumerate(endpoints, start=1):
        ep_label = f"{label}.endpoints[{index}]"
        if not isinstance(endpoint, dict):
            violations.append(f"{ep_label}: 端点必须是键值映射")
            continue
        url = str(endpoint.get("url") or "").strip()
        method = str(endpoint.get("method") or "").strip().upper()
        endpoint_class = str(endpoint.get("endpoint_class") or "").strip()
        if not url:
            violations.append(f"{ep_label}: 缺少 url")
            continue
        if url in seen_urls:
            violations.append(f"{ep_label}: url 重复 {url!r}（同端点不得重复登记）")
            continue
        seen_urls.add(url)
        if _host_of(url) == "":
            violations.append(f"{ep_label}: url 无法解析 host：{url!r}")
        if method not in L0_ALLOWED_METHODS:
            violations.append(
                f"{ep_label}: method {method!r} 被拒绝——只读 GET 型端点"
                f"（允许值 {list(L0_ALLOWED_METHODS)}）"
            )
        if endpoint_class != L0_ALLOWED_ENDPOINT_CLASS:
            if endpoint_class in L0_ENDPOINT_CLASSES:
                violations.append(
                    f"{ep_label}: endpoint_class {endpoint_class!r} 被拒绝——{L0_NEVER_REPLAY_RULE}"
                )
            else:
                violations.append(
                    f"{ep_label}: endpoint_class 未知 {endpoint_class!r}"
                    f"（允许值 {list(L0_ENDPOINT_CLASSES)}；仅 {L0_ALLOWED_ENDPOINT_CLASS!r} 可重放）"
                )
        host = _host_of(url)
        if host:
            host_counts[host] = host_counts.get(host, 0) + 1
    for host, count in sorted(host_counts.items()):
        if count > L0_MAX_ENDPOINTS_PER_HOST:
            violations.append(
                f"{label}: host {host} 端点数 {count} 超预算（每 host ≤{L0_MAX_ENDPOINTS_PER_HOST}）"
            )
    return violations


def build_signature_replay_l0_plan(
    config: Mapping[str, object],
) -> tuple[dict, list[str]]:
    """构建受控重放 runbook（纯数据；零执行、零网络）。

    违例（写 ack、写/业务方法、超预算等）时 plan 仍返回完整约束回显，但
    executable=false 且不展开任何 replay_steps——被拒绝的配置不产出可执行步骤。
    """
    violations = validate_l0_config(config)
    endpoints = config.get("endpoints") if isinstance(config.get("endpoints"), list) else []
    basis = str(config.get("authorization_basis") or "")
    executable = not violations
    plan_endpoints: list[dict] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        url = str(endpoint.get("url") or "").strip()
        if not url:
            continue
        entry: dict = {
            "url": url,
            "method": str(endpoint.get("method") or "").strip().upper(),
            "host": _host_of(url),
            "endpoint_class": str(endpoint.get("endpoint_class") or "").strip(),
            "evidence_ref": str(endpoint.get("evidence_ref") or ""),
            "original_capture": {
                "label": L0_WINDOW_ORIGINAL,
                "note": "T0 原始请求响应记录（基线；status/结构指纹/长度，不存值）",
            },
        }
        if executable:
            entry["replay_steps"] = [
                {
                    "label": f"t_plus_{offset}s",
                    "offset_seconds": offset,
                    "replays": L0_REPLAYS_PER_WINDOW,
                    "delay_floor_seconds": L0_MIN_DELAY_SECONDS,
                    "note": "原样重发同一签名请求字节（单请求、单次、无并发）",
                }
                for offset in L0_TIME_WINDOW_OFFSETS_SECONDS
            ]
        else:
            entry["replay_steps"] = []
        plan_endpoints.append(entry)
    plan = {
        "schema_version": SIGNATURE_REPLAY_L0_SCHEMA_VERSION,
        "contract": SIGNATURE_REPLAY_L0_CONTRACT,
        "plan_only": True,
        "module_executes": False,
        "executable": executable,
        "executor": "operator_manual",
        "approval_gate": "tier_c_single_candidate",
        "artifact": SIGNATURE_REPLAY_L0_ARTIFACT,
        "authorization_basis": basis,
        "write_risk_ack": L0_WRITE_RISK_ACK_MUST_BE,
        "constraints": {
            "allowed_methods": list(L0_ALLOWED_METHODS),
            "endpoint_classes": list(L0_ENDPOINT_CLASSES),
            "allowed_endpoint_class": L0_ALLOWED_ENDPOINT_CLASS,
            "max_endpoints_per_host": L0_MAX_ENDPOINTS_PER_HOST,
            "min_delay_seconds": L0_MIN_DELAY_SECONDS,
            "time_window_offsets_seconds": list(L0_TIME_WINDOW_OFFSETS_SECONDS),
            "replays_per_window": L0_REPLAYS_PER_WINDOW,
            "write_risk_ack_must_be": L0_WRITE_RISK_ACK_MUST_BE,
        },
        "red_lines": [L0_NEVER_REPLAY_RULE, L0_MANUAL_EXECUTION_RULE],
        "endpoints": plan_endpoints,
        "note": "本模块只生成计划不执行；结果经 ingest 解析（操作者手工回填）",
        "violations": violations,
    }
    return plan, violations


def _accepted(window_row: Mapping[str, object], original_row: Mapping[str, object]) -> bool:
    """确定性判据：业务成功状态 + 结构指纹与基线一致（可选响应类别排除错误形态）。"""
    try:
        status = int(window_row.get("http_status"))
    except (TypeError, ValueError):
        return False
    if status != 200:
        return False
    if str(window_row.get("body_fingerprint") or "") != str(original_row.get("body_fingerprint") or ""):
        return False
    response_class = str(window_row.get("response_class") or "").strip()
    if response_class and response_class in L0_REJECTED_RESPONSE_CLASSES:
        return False
    return True


def ingest_signature_replay_l0_results(
    results: Iterable[Mapping[str, object]],
    *,
    label: str = "l0_ingest",
) -> tuple[list[dict], list[str]]:
    """操作者手工回填的三窗口观测 → (判定行列表, 违例)。

    每行必须回指 url 与窗口；同 (url, window) 只允许 1 行（单请求重放 1 次）；
    每端点三窗口必须齐全。行内凭证类键拒绝（复用 response_baseline._credential_scan）。
    派生判据全部确定性：双窗接受=candidate（replay_window 分支，待人工复核）；
    单窗接受/双窗拒绝=signal；数据不全=inconclusive。confirmed 永不产生。
    """
    rows: list[dict] = []
    violations: list[str] = []
    grouped: dict[str, dict[str, dict]] = {}
    for index, raw in enumerate(results, start=1):
        row_label = f"{label}[{index}]"
        if not isinstance(raw, dict):
            violations.append(f"{row_label}: 观测必须是键值映射")
            continue
        violations += rb._credential_scan(raw, row_label)
        url = str(raw.get("url") or "").strip()
        window = str(raw.get("window") or "").strip()
        if not url or window not in L0_WINDOW_LABELS:
            violations.append(
                f"{row_label}: 缺少 url 或 window 非法 {window!r}（允许值 {list(L0_WINDOW_LABELS)}）"
            )
            continue
        if window in grouped.setdefault(url, {}):
            violations.append(
                f"{row_label}: ({url}, {window}) 重复观测——单请求重放 1 次，"
                "每窗口只允许 1 行"
            )
            continue
        grouped[url][window] = dict(raw)
    for url_index, url in enumerate(sorted(grouped), start=1):
        windows = grouped[url]
        missing = [w for w in L0_WINDOW_LABELS if w not in windows]
        for w in missing:
            violations.append(f"{label}: {url} 缺少 {w} 窗口观测（三窗口必须齐全）")
        original = windows.get(L0_WINDOW_ORIGINAL)
        if original is None or missing:
            rows.append(_build_row(
                url_index, url, "inconclusive", "inconclusive", windows,
                "窗口观测不齐全（fail-closed）：无法派生重放判据，只记 inconclusive",
            ))
            continue
        t5 = windows.get("t_plus_5s") or {}
        t60 = windows.get("t_plus_60s") or {}
        accepted_t5 = _accepted(t5, original)
        accepted_t60 = _accepted(t60, original)
        if accepted_t5 and accepted_t60:
            outcome = "accepted_both_windows"
            status = "candidate"
            reason = (
                "同一签名请求在 T+5s 与 T+60s 双窗均被原样接受（业务成功且结构指纹与"
                "基线一致）——replay_window 分支重放边界失效假设成立，进人工复核；"
                "confirmed 仍归五门判定"
            )
        elif accepted_t5 and not accepted_t60:
            outcome = "accepted_t5_only"
            status = "signal"
            reason = "T+5s 接受但 T+60s 拒绝——存在重放窗控制的正向证据，只记 signal"
        elif accepted_t60 and not accepted_t5:
            outcome = "accepted_t60_only"
            status = "inconclusive"
            reason = "T+5s 拒绝但 T+60s 接受（非常规形态）：需人工复核，只记 inconclusive"
        else:
            outcome = "rejected_both_windows"
            status = "signal"
            reason = "双窗均拒绝——重放防护在位（正向证据），只记 signal"
        rows.append(_build_row(url_index, url, status, outcome, windows, reason))
    for row in rows:
        violations += validate_signature_replay_l0_row(
            row, label=f"{label}[{row['row_id']}]"
        )
    return rows, violations


def _build_row(
    row_index: int,
    url: str,
    status: str,
    outcome: str,
    windows: Mapping[str, Mapping[str, object]],
    reason: str,
) -> dict:
    window_meta: dict[str, dict] = {}
    for window in L0_WINDOW_LABELS:
        raw = windows.get(window) or {}
        window_meta[window] = {
            "http_status": raw.get("http_status"),
            "body_fingerprint": str(raw.get("body_fingerprint") or ""),
            "body_len": raw.get("body_len"),
            "response_class": str(raw.get("response_class") or ""),
        }
    evidence_ref = ""
    for window in L0_WINDOW_LABELS:
        raw = windows.get(window) or {}
        evidence_ref = str(raw.get("evidence_ref") or "")
        if evidence_ref:
            break
    return {
        "row_id": f"srl0-{row_index:04d}",
        "url": url,
        "http_method": L0_ALLOWED_METHODS[0],
        "branch": L0_ROW_BRANCH,
        "status": status,
        "replay_outcome": outcome,
        "windows": window_meta,
        "source": "signature_replay_l0_ingest",
        "evidence_ref": evidence_ref,
        "precondition": f"{L0_NEVER_REPLAY_RULE}；{L0_MANUAL_EXECUTION_RULE}",
        "reason": reason,
    }


def validate_signature_replay_l0_row(
    row: Mapping[str, object], label: str = "l0_row"
) -> list[str]:
    """判定行校验：字段、枚举、confirmed 拒绝、窗口齐全、candidate 证据索引。"""
    violations: list[str] = []
    if not isinstance(row, dict):
        return [f"{label}: 判定行必须是键值映射"]
    for field in L0_ROW_REQUIRED_FIELDS:
        if field not in row:
            violations.append(f"{label}: 缺少必需字段 {field}")
    status = str(row.get("status") or "")
    if status and status not in L0_ROW_STATUSES:
        violations.append(
            f"{label}: status 非法 {status!r}（允许值 {list(L0_ROW_STATUSES)}；"
            "confirmed 永不由 L0 ingest 产生）"
        )
    outcome = str(row.get("replay_outcome") or "")
    if outcome and outcome not in L0_REPLAY_OUTCOMES:
        violations.append(f"{label}: replay_outcome 非法 {outcome!r}")
    branch = str(row.get("branch") or "")
    if branch and branch != L0_ROW_BRANCH:
        violations.append(f"{label}: branch 只允许 {L0_ROW_BRANCH!r}（L0 只服务重放窗分支）")
    method = str(row.get("http_method") or "")
    if method and method not in L0_ALLOWED_METHODS:
        violations.append(f"{label}: http_method 只允许 {list(L0_ALLOWED_METHODS)}")
    windows = row.get("windows")
    if windows is not None:
        if not isinstance(windows, dict) or tuple(sorted(windows)) != tuple(sorted(L0_WINDOW_LABELS)):
            violations.append(
                f"{label}: windows 必须恰好包含 {list(L0_WINDOW_LABELS)} 三窗口"
            )
    if status == "candidate":
        if outcome != "accepted_both_windows":
            violations.append(
                f"{label}: candidate 只能来自 accepted_both_windows（双窗接受）"
            )
        if not str(row.get("evidence_ref") or "").strip():
            violations.append(f"{label}: candidate 缺少 evidence_ref（证据索引强制）")
    return violations


def _cli() -> int:
    """离线 CLI：plan（config→runbook JSON）/ ingest（观测 JSONL→判定行 JSONL）。"""
    import argparse
    import json
    from datetime import datetime
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description=(
            "Signature-replay L0 controlled executor (plan+ingest; zero execution, "
            "operator manual replay only)."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan", help="Build pure-data replay runbook from config JSON")
    plan_parser.add_argument("--config", required=True, help="Config JSON file")
    plan_parser.add_argument("--out", required=True, help="Output plan JSON path")
    ingest_parser = sub.add_parser("ingest", help="Parse operator-filled observation JSONL")
    ingest_parser.add_argument("--results", required=True, help="Observation JSONL file")
    ingest_parser.add_argument("--out", required=True, help="Output artifact JSONL path")
    args = parser.parse_args()
    if args.command == "plan":
        config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
        plan, violations = build_signature_replay_l0_plan(config)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"executable={plan['executable']} endpoints={len(plan['endpoints'])} "
              f"violations={len(violations)}")
        return 0 if not violations else 2
    observations = [
        json.loads(line)
        for line in Path(args.results).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    rows, violations = ingest_signature_replay_l0_results(observations)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    print(f"rows={len(rows)} violations={len(violations)}")
    for v in violations:
        print(f"  violation: {v}")
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(_cli())
