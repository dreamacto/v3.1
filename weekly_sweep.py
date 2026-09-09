# -*- coding: utf-8 -*-
"""配方 E 周度沉淀：双事实源、纯离线、幂等快照。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import metrics_weekly

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _engagement_cursor(record: dict) -> dict:
    rows = record.get("rows", [])
    updated = [r.get("updated_at") for r in rows if r.get("updated_at")]
    return {
        "path": record["relative_path"],
        "ledger_rows": record["ledger_rows"],
        "updated_rows": record["updated_rows"],
        "max_updated_at": max(updated) if updated else None,
        "wz_current_phase": record["phases"]["wz"].get("current_phase", ""),
        "xcx_current_phase": record["phases"]["xcx"].get("current_phase", ""),
    }


def sweep(days: int = 7, runs_root: str = "runs", engagements_root: str = "engagements", kb: str = "knowledge_base", reports: str = "reports") -> dict:
    now = datetime.now(CST)
    runs_path = ROOT / runs_root
    engagements_path = ROOT / engagements_root
    kb_path = ROOT / kb
    reports_path = ROOT / reports
    reports_path.mkdir(parents=True, exist_ok=True)
    runs, incomplete = metrics_weekly.scan_runs(runs_path, days, now)
    engagement_stats = metrics_weekly.collect_engagements(engagements_path, days, now)
    previous_path = kb_path / "last_sweep.json"
    previous = {}
    if previous_path.is_file():
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}

    cursor = {
        "last_sweep": now.isoformat(timespec="seconds"),
        "runs_covered": [f"{runs_root.rstrip('/\\')}/{r['dir']}" for r in runs],
        "engagements_covered": [_engagement_cursor(r) for r in engagement_stats["records"]],
        "engagement_rows_covered": {r["relative_path"]: r["ledger_rows"] for r in engagement_stats["records"]},
        "previous_last_sweep": previous.get("last_sweep"),
        "runs_scanned": len(runs),
        "engagements_scanned": engagement_stats["dirs"],
        "incomplete_runs": len(incomplete),
    }
    kb_path.mkdir(parents=True, exist_ok=True)
    previous_rows = previous.get("fingerprint_rows_kept")
    if previous_rows is not None:
        cursor["fingerprint_rows_kept"] = previous_rows
    previous_excluded = previous.get("fingerprint_rows_excluded_fp")
    if previous_excluded is not None:
        cursor["fingerprint_rows_excluded_fp"] = previous_excluded
    previous_path.write_text(json.dumps(cursor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    date = now.strftime("%Y-%m-%d")
    report = reports_path / f"weekly_{date}.md"
    lines = [
        f"# 周度沉淀 · {date}",
        "",
        f"- 窗口：近 {days} 天；生成：{now.isoformat(timespec='seconds')}；纯离线。",
        "",
        "## 数据源覆盖",
        "",
        f"- `runs/`：去重后 {len(runs)} 个，缺 `run_summary.json` 的目录 {len(incomplete)} 个。",
        f"- `engagements/`：{engagement_stats['dirs']} 个标准工作区，台账 {engagement_stats['ledger_rows']} 行，本窗口更新 {engagement_stats['updated_rows']} 行。",
        "- engagement 深度读取了两个独立 phase 游标、目标模型/覆盖/安全说明文件摘要、台账稳定字段和脱敏 evidence index；顶层共享 `engagements/evidence/` 已排除。",
        "",
        "## engagement 状态",
        "",
    ]
    for status, count in sorted(engagement_stats["by_status"].items()):
        lines.append(f"- `{status}`：{count}")
    lines += ["", "## engagement 工作区快照", ""]
    for record in engagement_stats["records"]:
        wz, xcx = record["phases"]["wz"], record["phases"]["xcx"]
        lines.append(
            f"- `{record['relative_path']}`：ledger {record['ledger_rows']} 行（窗口更新 {record['updated_rows']}），"
            f"WZ `{wz.get('current_phase') or '未提供'}`，XCX `{xcx.get('current_phase') or '未提供'}`，"
            f"可报告证据索引 {record['meta']['evidence'].get('report_eligible_count', 0)} 条。"
        )
    lines += ["", "## 沉淀边界", "", "- 本次只写周报和 `knowledge_base/last_sweep.json` 游标；候选不会自动升级为 confirmed。", "- 不写入凭证、原始请求/响应、raw evidence、个人数据或工作区外路径。", "- 指纹、误报和假设库仍按各自既有追加式生产者与人工终审规则更新。", ""]
    report.write_text("\n".join(lines), encoding="utf-8")
    return {"report": str(report), "cursor": str(previous_path), "runs": len(runs), "engagements": engagement_stats["dirs"], "ledger_rows": engagement_stats["ledger_rows"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="双事实源周度沉淀（纯离线）")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument("--engagements-root", default="engagements")
    parser.add_argument("--kb", default="knowledge_base")
    parser.add_argument("--reports", default="reports")
    args = parser.parse_args()
    result = sweep(args.days, args.runs_root, args.engagements_root, args.kb, args.reports)
    print(f"[+] 周报 → {result['report']}")
    print(f"[+] 游标 → {result['cursor']}")
    print(f"[*] runs={result['runs']} engagements={result['engagements']} 台账={result['ledger_rows']}")


if __name__ == "__main__":
    main()
