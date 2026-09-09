"""input_testing 编排器（实施规格 5.4 input_testing 子阶段；orchestration_only
+ W-4 受限 probe 预算制审计）。

职责边界（操作员决定④⑥ + 2026-09-07 P1 方案 §3 W-4）：只负责编排与产物治理——
初始化产物骨架、调用已接入的筛选域（injection_candidate_screening /
parser_deserialization_screening / ssrf_candidate_screening /
file_path_candidate_screening / browser_boundary_review 的既有模块）、把候选与类别
汇总落盘、审计产物完整性。编排器自身仍不重复执行任何子阶段探测动作（不发请求、
不发 payload、不签发 OOB token、不读本地文件）；注入面探测从"零 probe"放宽为
"白名单 probe + 预算"——由白名单脚本在阶段外执行，探测事件落 probe 台账
（artifacts/input-testing/probe-ledger.jsonl），本模块只审计台账：非白名单脚本或
超预算（每 host >10 参数 / 单参数多发 / arjun 单 host >1 次）必须被拒。

产物路径：规格 5.4 明示 artifacts/ssrf/ 三件与 artifacts/browser-boundary/
cors-csrf-cache.jsonl、reports/browser-boundary.md；injection/parser/file-path 三域
路径为规格未明示部分的实现定义（artifacts/input-testing/、artifacts/file-path/），
登记于 INPUT_TESTING_ARTIFACTS 单一事实源（probe 台账为 W-4 增补）。全部离线、
只读输入、幂等初始化。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from authorized_assessment.triage import browser_boundary as bb
from authorized_assessment.triage import file_path_candidate_screening as fp
from authorized_assessment.triage import injection_candidates as ic
from authorized_assessment.triage import parser_deserialization as pdeser
from authorized_assessment.triage import ssrf_candidate_screening as ssrf

# 产物路径登记（相对 workspace 根；spec 5.4 明示 ssrf 三件与 browser-boundary 两件，
# 其余为实现定义；probe_ledger_jsonl 为 W-4 受限 probe 预算制增补，2026-09-07）。
INPUT_TESTING_ARTIFACTS: dict[str, str] = {
    "injection_summary_csv": "artifacts/input-testing/injection-category-summary.csv",
    "injection_candidates_jsonl": "artifacts/input-testing/injection-candidates.jsonl",
    "parser_summary_csv": "artifacts/input-testing/parser-deserialization-category-summary.csv",
    "parser_candidates_jsonl": "artifacts/input-testing/parser-deserialization-candidates.jsonl",
    "ssrf_candidates_jsonl": "artifacts/ssrf/ssrf_candidates.jsonl",
    "ssrf_review_queue_csv": "artifacts/ssrf/ssrf_review_queue.csv",
    "oob_token_manifest": "artifacts/ssrf/oob_token_manifest.json",
    "browser_boundary_jsonl": "artifacts/browser-boundary/cors-csrf-cache.jsonl",
    "browser_boundary_report_md": "reports/browser-boundary.md",
    "file_path_summary_csv": "artifacts/file-path/file-path-category-summary.csv",
    "file_path_candidates_jsonl": "artifacts/file-path/file-path-candidates.jsonl",
    "probe_ledger_jsonl": "artifacts/input-testing/probe-ledger.jsonl",
}

# ---------------------------------------------------------------------------
# W-4 受限 probe 预算制（2026-09-07 P1，方案 §3 W-4 + tool_strategy input_testing）
# ---------------------------------------------------------------------------

# probe 白名单：marker 档 = 注入 marker 单发（每参数惰性/浅层判据）；discovery 档 =
# 参数发现（arjun，单 host ≤1 次运行，GET 优先）。白名单外脚本（sqlmap/dalfox/
# XSStrike/任何利用型工具）不属本阶段预算，仍走既有审批门。
PROBE_TOOL_WHITELIST: dict[str, dict[str, str]] = {
    "sqli_triage.py": {"profile": "shallow boolean/error differential", "kind": "marker"},
    "xss_candidate_triage.py": {"profile": "lazy inert marker", "kind": "marker"},
    "arjun": {"profile": "parameter discovery, GET first, single run per host", "kind": "discovery"},
}
# 预算（tool_strategy.json input_testing notes 同源）：每 host 注入 marker 参数 ≤10、
# 每参数单发（1 次请求）；arjun 每 host ≤1 次发现运行。
PROBE_BUDGET_MAX_PARAMS_PER_HOST = 10
PROBE_BUDGET_MAX_REQUESTS_PER_PARAM = 1
PROBE_DISCOVERY_MAX_RUNS_PER_HOST = 1
PROBE_LEDGER_ROW_FIELDS = (
    "host",
    "tool",
    "params",
    "requests_per_param",
    "evidence_ref",
    "reason",
)

SSRF_REVIEW_QUEUE_FIELDS = (
    "candidate_id",
    "status",
    "parameter_name",
    "source",
    "evidence_ref",
    "reason",
    "precondition",
)


def artifact_path(workspace: Path, key: str) -> Path:
    return Path(workspace) / INPUT_TESTING_ARTIFACTS[key]


def init_input_testing_artifacts(workspace: Path) -> list[str]:
    """初始化产物骨架（幂等：已存在的文件不覆盖，返回本次新建的相对路径列表）。"""
    workspace = Path(workspace)
    created: list[str] = []
    for key, rel in INPUT_TESTING_ARTIFACTS.items():
        path = workspace / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if key.endswith("_csv"):
            if key.endswith("summary_csv"):
                _write_summary_csv(path, [])
            else:
                _write_queue_csv(path, [])
        elif key.endswith("_jsonl"):
            path.write_text("", encoding="utf-8")
        elif key == "oob_token_manifest":
            path.write_text(
                json.dumps({"schema_version": "1.0", "tokens": []}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        elif key == "browser_boundary_report_md":
            path.write_text(bb.build_browser_boundary_report([], []), encoding="utf-8")
        created.append(rel)
    return created


def _write_summary_csv(path: Path, summaries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(list(ic.CATEGORY_SUMMARY_FIELDS))
        for row in summaries:
            writer.writerow(
                [
                    row.get("category", ""),
                    row.get("category_status", ""),
                    json.dumps(row.get("applicability_counts", {}), ensure_ascii=False, sort_keys=True),
                    json.dumps(row.get("status_counts", {}), ensure_ascii=False, sort_keys=True),
                    row.get("tested_count", 0),
                    row.get("reason", ""),
                    row.get("source", ""),
                    row.get("precondition", ""),
                ]
            )


def _write_queue_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(SSRF_REVIEW_QUEUE_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SSRF_REVIEW_QUEUE_FIELDS})


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def run_input_testing_screening(
    workspace: Path,
    *,
    injection_observations: list[dict] | None = None,
    parser_observations: list[dict] | None = None,
    ssrf_observations: list[dict] | None = None,
    browser_boundary_observations: list[dict] | None = None,
    file_path_observations: list[dict] | None = None,
    write: bool = True,
) -> dict:
    """已接入筛选域的筛选 + 落盘（离线端到端）。返回报告 dict；违例非空不视为失败——
    产物如实落盘，由 audit 与复核会话处置（筛选层不吞违例也不替人判定）。
    """
    workspace = Path(workspace)
    inj_rows, inj_summaries, inj_violations = ic.screen_observations(injection_observations or [])
    parser_rows, parser_summaries, parser_violations = pdeser.screen_parser_observations(
        parser_observations or []
    )
    ssrf_rows, ssrf_summary, ssrf_violations = ssrf.screen_ssrf_observations(ssrf_observations or [])
    bb_rows, bb_summaries, bb_violations = bb.screen_browser_boundary_observations(
        browser_boundary_observations or []
    )
    fp_rows, fp_summaries, fp_violations = fp.screen_file_path_observations(
        file_path_observations or []
    )
    report = {
        "domains": {
            "injection_candidate_screening": {
                "candidates": len(inj_rows),
                "summaries": len(inj_summaries),
                "violations": inj_violations,
            },
            "parser_deserialization_screening": {
                "candidates": len(parser_rows),
                "summaries": len(parser_summaries),
                "violations": parser_violations,
            },
            "ssrf_candidate_screening": {
                "candidates": len(ssrf_rows),
                "summary": ssrf_summary,
                "violations": ssrf_violations,
            },
            "browser_boundary_review": {
                "candidates": len(bb_rows),
                "summaries": len(bb_summaries),
                "violations": bb_violations,
            },
            "file_path_candidate_screening": {
                "candidates": len(fp_rows),
                "summaries": len(fp_summaries),
                "violations": fp_violations,
            },
        },
        "violations": inj_violations + parser_violations + ssrf_violations + bb_violations
        + fp_violations,
    }
    if write:
        init_input_testing_artifacts(workspace)
        _write_summary_csv(artifact_path(workspace, "injection_summary_csv"), inj_summaries)
        _write_jsonl(artifact_path(workspace, "injection_candidates_jsonl"), inj_rows)
        _write_summary_csv(artifact_path(workspace, "parser_summary_csv"), parser_summaries)
        _write_jsonl(artifact_path(workspace, "parser_candidates_jsonl"), parser_rows)
        _write_jsonl(artifact_path(workspace, "ssrf_candidates_jsonl"), ssrf_rows)
        _write_queue_csv(artifact_path(workspace, "ssrf_review_queue_csv"), ssrf_rows)
        _write_jsonl(artifact_path(workspace, "browser_boundary_jsonl"), bb_rows)
        report_md = artifact_path(workspace, "browser_boundary_report_md")
        report_md.parent.mkdir(parents=True, exist_ok=True)
        report_md.write_text(bb.build_browser_boundary_report(bb_summaries, bb_violations), encoding="utf-8")
        _write_summary_csv(artifact_path(workspace, "file_path_summary_csv"), fp_summaries)
        _write_jsonl(artifact_path(workspace, "file_path_candidates_jsonl"), fp_rows)
    return report


def _read_summary_csv(path: Path) -> tuple[list[dict], list[str]]:
    violations: list[str] = []
    summaries: list[dict] = []
    if not path.is_file():
        return [], [f"missing artifact: {path.name}"]
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header != list(ic.CATEGORY_SUMMARY_FIELDS):
            return [], [f"{path.name}: 表头与契约字段不符: {header}"]
        for line_no, raw in enumerate(reader, start=2):
            if not raw:
                continue
            try:
                summaries.append(
                    {
                        "category": raw[0],
                        "category_status": raw[1],
                        "applicability_counts": json.loads(raw[2]),
                        "status_counts": json.loads(raw[3]),
                        "tested_count": int(raw[4]),
                        "reason": raw[5],
                        "source": raw[6],
                        "precondition": raw[7],
                    }
                )
            except (IndexError, ValueError, json.JSONDecodeError) as exc:
                violations.append(f"{path.name}:L{line_no}: 解析失败 {exc}")
    return summaries, violations


def _read_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    violations: list[str] = []
    rows: list[dict] = []
    if not path.is_file():
        return [], [f"missing artifact: {path.name}"]
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            violations.append(f"{path.name}:L{line_no}: 解析失败 {exc}")
    return rows, violations


def _consistency_violations(
    summaries: list[dict], candidate_rows: list[dict], label: str, category_key: str = "category"
) -> list[str]:
    """summary.status_counts / tested_count 必须与候选行归组重算一致（端到端闭环）。"""
    violations: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for row in candidate_rows:
        grouped.setdefault(str(row.get(category_key) or ""), []).append(row)
    for summary in summaries:
        category = str(summary.get(category_key) or "")
        cat_rows = grouped.get(category, [])
        counts = {s: 0 for s in ic.CANDIDATE_STATUS_VALUES}
        for row in cat_rows:
            status = str(row.get("status") or "")
            if status in counts:
                counts[status] += 1
        for status, count in counts.items():
            recorded = int((summary.get("status_counts") or {}).get(status, 0))
            if recorded != count:
                violations.append(
                    f"{label}[{category}].status_counts.{status}={recorded} 与候选行重算 {count} 不一致"
                )
        recorded_tested = int(summary.get("tested_count") or 0)
        recomputed = sum(counts[s] for s in ic.DEFINITIVE_RESULT_STATUSES)
        if recorded_tested != recomputed:
            violations.append(
                f"{label}[{category}].tested_count={recorded_tested} 与候选行重算 {recomputed} 不一致"
            )
    orphan = sorted(set(grouped) - {str(s.get(category_key) or "") for s in summaries})
    if orphan:
        violations.append(f"{label}: 候选行存在汇总未覆盖的类别 {orphan}")
    return violations


def validate_probe_ledger(rows: list[dict], label: str = "probe-ledger") -> list[str]:
    """W-4 probe 台账审计：白名单 + 预算（2026-09-07 P1，方案 §3 W-4）。

    行契约（PROBE_LEDGER_ROW_FIELDS）：host/tool/params/requests_per_param 必填，
    evidence_ref/reason 可选。规则：tool 必须在 PROBE_TOOL_WHITELIST（非白名单即
    拒）；marker 档每 host 去重参数并集 ≤10、每参数单发（requests_per_param=1）；
    discovery 档（arjun）每 host ≤1 次运行。台账为空 = 零 probe（纯离线管线），
    合法。返回违例列表（非空即超预算/非白名单事实，交 audit 与复核处置）。
    """
    violations: list[str] = []
    host_params: dict[str, set[str]] = {}
    host_discovery_runs: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        row_label = f"{label}:L{index}"
        if not isinstance(row, dict):
            violations.append(f"{row_label}: 行必须是键值映射")
            continue
        for field in ("host", "tool", "params", "requests_per_param"):
            if field not in row:
                violations.append(f"{row_label}: 缺少必需字段 {field}")
        host = str(row.get("host") or "").strip()
        tool = str(row.get("tool") or "").strip()
        if not host:
            violations.append(f"{row_label}: host 为空")
            continue
        if tool not in PROBE_TOOL_WHITELIST:
            violations.append(
                f"{row_label}: 非白名单 probe 脚本 {tool!r}"
                f"（允许值 {sorted(PROBE_TOOL_WHITELIST)}；利用型工具走既有审批门）"
            )
            continue
        kind = PROBE_TOOL_WHITELIST[tool]["kind"]
        params = row.get("params")
        if not isinstance(params, list) or not params:
            violations.append(f"{row_label}: params 必须为非空列表")
            continue
        param_names = [str(item).strip() for item in params]
        if any(not item for item in param_names):
            violations.append(f"{row_label}: params 含空参数名")
            continue
        requests = row.get("requests_per_param")
        if not isinstance(requests, int) or isinstance(requests, bool):
            violations.append(f"{row_label}: requests_per_param 必须为整数")
            continue
        if requests > PROBE_BUDGET_MAX_REQUESTS_PER_PARAM:
            violations.append(
                f"{row_label}: 超预算——单参数请求 {requests} 次 > 单发上限 "
                f"{PROBE_BUDGET_MAX_REQUESTS_PER_PARAM}"
            )
        if requests < 1:
            violations.append(f"{row_label}: requests_per_param 必须 ≥1")
        if kind == "discovery":
            host_discovery_runs[host] = host_discovery_runs.get(host, 0) + 1
            if len(param_names) > 1:
                violations.append(
                    f"{row_label}: discovery 档单次运行只记一条（params 应为发现批次，"
                    "不得按参数拆行绕过单 host ≤1 次预算）"
                )
        else:
            host_params.setdefault(host, set()).update(param_names)
    for host, params in sorted(host_params.items()):
        if len(params) > PROBE_BUDGET_MAX_PARAMS_PER_HOST:
            violations.append(
                f"{label}: 超预算——host {host} 注入 marker 参数 {len(params)} 个 > "
                f"每 host 上限 {PROBE_BUDGET_MAX_PARAMS_PER_HOST}"
            )
    for host, runs in sorted(host_discovery_runs.items()):
        if runs > PROBE_DISCOVERY_MAX_RUNS_PER_HOST:
            violations.append(
                f"{label}: 超预算——host {host} 参数发现运行 {runs} 次 > "
                f"每 host 上限 {PROBE_DISCOVERY_MAX_RUNS_PER_HOST}（arjun 单 host ≤1 次）"
            )
    return violations


def audit_input_testing(workspace: Path) -> tuple[bool, list[str]]:
    """审计 input_testing 产物：存在性 + 行契约 + summary↔候选一致性 + OOB manifest 红线
    + W-4 probe 台账白名单/预算。

    返回 (ok, violations)。产物从未生成（全部缺骨架）时同样报违例——审计不做静默通过。
    """
    workspace = Path(workspace)
    violations: list[str] = []
    missing = [rel for rel in INPUT_TESTING_ARTIFACTS.values() if not (workspace / rel).is_file()]
    if missing:
        violations.append(f"input_testing: 缺少产物文件 {missing}")
        return False, violations

    probe_rows, v = _read_jsonl(artifact_path(workspace, "probe_ledger_jsonl"))
    violations += v
    violations += validate_probe_ledger(probe_rows)

    inj_summaries, v = _read_summary_csv(artifact_path(workspace, "injection_summary_csv"))
    violations += v
    inj_rows, v = _read_jsonl(artifact_path(workspace, "injection_candidates_jsonl"))
    violations += v
    for index, row in enumerate(inj_rows, start=1):
        violations += [
            f"injection-candidates.jsonl:L{index}: {msg}"
            for msg in ic.validate_injection_candidate(row, label=f"candidate[{row.get('candidate_id')}]")
        ]
    for summary in inj_summaries:
        violations += ic.validate_category_summary(summary, label="injection-category-summary")
    violations += _consistency_violations(inj_summaries, inj_rows, "injection-category-summary")

    parser_summaries, v = _read_summary_csv(artifact_path(workspace, "parser_summary_csv"))
    violations += v
    parser_rows, v = _read_jsonl(artifact_path(workspace, "parser_candidates_jsonl"))
    violations += v
    for index, row in enumerate(parser_rows, start=1):
        violations += [
            f"parser-candidates.jsonl:L{index}: {msg}"
            for msg in ic.validate_injection_candidate(row, label=f"candidate[{row.get('candidate_id')}]")
        ]
    for summary in parser_summaries:
        violations += ic.validate_category_summary(summary, label="parser-category-summary")
    violations += _consistency_violations(parser_summaries, parser_rows, "parser-category-summary")

    ssrf_rows, v = _read_jsonl(artifact_path(workspace, "ssrf_candidates_jsonl"))
    violations += v
    for index, row in enumerate(ssrf_rows, start=1):
        violations += [
            f"ssrf_candidates.jsonl:L{index}: {msg}"
            for msg in ssrf.validate_ssrf_candidate(row, label=f"candidate[{row.get('candidate_id')}]")
        ]
    queue_path = artifact_path(workspace, "ssrf_review_queue_csv")
    with queue_path.open("r", encoding="utf-8", newline="") as f:
        queue_rows = list(csv.DictReader(f))
    if len(queue_rows) != len(ssrf_rows):
        violations.append(
            f"ssrf_review_queue.csv 行数 {len(queue_rows)} 与 ssrf_candidates.jsonl {len(ssrf_rows)} 不一致"
        )

    manifest, err = None, None
    try:
        manifest = json.loads(artifact_path(workspace, "oob_token_manifest").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        err = str(exc)
    if err or not isinstance(manifest, dict):
        violations.append(f"oob_token_manifest.json 不可解析: {err}")
    else:
        violations += ssrf.validate_oob_token_manifest(manifest)

    bb_rows, v = _read_jsonl(artifact_path(workspace, "browser_boundary_jsonl"))
    violations += v
    for index, row in enumerate(bb_rows, start=1):
        violations += [
            f"cors-csrf-cache.jsonl:L{index}: {msg}"
            for msg in bb.validate_browser_boundary_candidate(
                row, label=f"candidate[{row.get('candidate_id')}]"
            )
        ]
    report_payload, report_err = bb.extract_report_summary(
        artifact_path(workspace, "browser_boundary_report_md").read_text(encoding="utf-8")
    )
    if report_err or report_payload is None:
        violations.append(f"browser-boundary.md: {report_err}")
    else:
        if str(report_payload.get("domain") or "") != "browser_boundary":
            violations.append("browser-boundary.md: domain 字段缺失或不符")
        if str(report_payload.get("schema_version") or "") != bb.REPORT_SCHEMA_VERSION:
            violations.append(
                f"browser-boundary.md: schema_version 与当前 {bb.REPORT_SCHEMA_VERSION!r} 不符"
            )
        bb_summaries = report_payload.get("category_summaries")
        if not isinstance(bb_summaries, list):
            violations.append("browser-boundary.md: category_summaries 必须为列表")
            bb_summaries = []
        for summary in bb_summaries:
            violations += ic.validate_category_summary(
                summary,
                label="browser-boundary-report",
                categories=bb.BROWSER_BOUNDARY_CATEGORIES,
            )
        violations += _consistency_violations(
            bb_summaries, bb_rows, "browser-boundary-report"
        )

    fp_summaries, v = _read_summary_csv(artifact_path(workspace, "file_path_summary_csv"))
    violations += v
    fp_rows, v = _read_jsonl(artifact_path(workspace, "file_path_candidates_jsonl"))
    violations += v
    for index, row in enumerate(fp_rows, start=1):
        violations += [
            f"file-path-candidates.jsonl:L{index}: {msg}"
            for msg in fp.validate_file_path_candidate(
                row, label=f"candidate[{row.get('candidate_id')}]"
            )
        ]
    for summary in fp_summaries:
        violations += ic.validate_category_summary(
            summary, label="file-path-category-summary", categories=fp.FILE_PATH_CATEGORIES
        )
    violations += _consistency_violations(fp_summaries, fp_rows, "file-path-category-summary")

    return not violations, violations
