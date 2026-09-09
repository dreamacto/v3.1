# -*- coding: utf-8 -*-
"""W10 · 周度度量 metrics_weekly.py

扫描 runs/*/（近 N 天）→ 聚合五指标 → reports/metrics_YYYYMMDD.md + reports/metrics_history.jsonl。
纯离线、零网络。缺数据的指标显示 N/A 不报错。

五指标：
 1 每run候选数      = Σ(各 *_candidates.jsonl 行数) / run 数
 2 确认率          = findings_ledger confirmed / (confirmed+rejected)
 3 人工小时/确认    = N/A（当前无复核时长数据源；接口预留）
 4 各队列FP率       = fp_memory 条数 / 对应候选总量（按 host 前缀聚类的近似）
 5 假设命中率       = hypothesis_ledger tested_confirmed / (tested_confirmed+tested_falsified)

用法：
  python metrics_weekly.py [--days 7] [--runs-root runs]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def _mtime_within(p: Path, days: int, now: datetime) -> bool:
    if days >= 99999:
        return True
    try:
        return (now - datetime.fromtimestamp(p.stat().st_mtime, CST)).days <= days
    except OSError:
        return False


def count_lines(p: Path) -> int:
    try:
        with p.open(encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def read_jsonl(p: Path) -> list[dict]:
    out = []
    if not p.is_file():
        return out
    with p.open(encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    return out


def scan_runs(runs_root: Path, days: int, now: datetime) -> tuple[list[dict], list[str]]:
    runs, incomplete = [], []
    if not runs_root.is_dir():
        return runs, incomplete
    for d in sorted(runs_root.iterdir()):
        if not d.is_dir() or not _mtime_within(d, days, now):
            continue
        # 测试/开发目录不计入运营度量（20260822 复盘：11 个 *_test* 目录混进周报）
        if re.search(r"(^|_)(test|smoke|dev|tmp|hdrtest)(_|$)", d.name, re.I):
            continue
        cand_total = 0
        cand_files = []
        for f in d.glob("*_candidates.jsonl"):
            n = count_lines(f)
            cand_total += n
            cand_files.append((f.name, n))
        has_summary = (d / "run_summary.json").is_file()
        summary = {}
        if has_summary:
            try:
                summary = json.loads((d / "run_summary.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                summary = {}
        runs.append({"dir": d.name, "candidates": cand_total, "cand_files": cand_files,
                     "has_summary": has_summary, "dedup_key": summary.get("dedup_key"),
                     "run_id": summary.get("run_id") or d.name})
        if not has_summary:
            incomplete.append(d.name)
    # Lineage-aware runs: retries with the same key count once; legacy runs remain distinct.
    unique = {}
    for run in runs:
        key = run.get("dedup_key") or f"legacy:{run['dir']}"
        previous = unique.get(key)
        if previous is None or run["dir"] > previous["dir"]:
            unique[key] = run
    return list(unique.values()), incomplete


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(CST)
    except (TypeError, ValueError):
        return None


def _row_in_window(row: dict, fallback: datetime, days: int, now: datetime) -> bool:
    if days >= 99999:
        return True
    stamp = _parse_dt(row.get("updated_at")) or fallback
    return (now - stamp).days <= days


def _status_bucket(status: str) -> str:
    status = (status or "").strip().lower()
    if status == "confirmed":
        return "confirmed"
    if status == "rejected" or status in {"duplicate", "out_of_scope", "fixed", "retest_passed"}:
        return "rejected"
    if status == "accepted_risk":
        return "accepted_risk"
    if status in {"approval_required", "blocked"}:
        return "blocked"
    if status in {"candidate", "pending", "needs_manual_validation", "needs_login", "signal", "in_progress", "proposed"}:
        return "open"
    return "unknown"


def _safe_ref(value: str, root: Path) -> str:
    """只返回 workspace 内相对引用，拒绝外部绝对路径。"""
    if not value:
        return ""
    try:
        p = Path(value)
        if not p.is_absolute():
            p = root / p
        resolved = p.resolve()
        return resolved.relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return ""


def _phase_snapshot(path: Path) -> dict:
    result = {"present": path.is_file(), "current_phase": "", "next_phase": "", "counts": Counter(), "blocked_reasons": [], "substatuses": {}}
    if not path.is_file():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return result
    result["current_phase"] = data.get("current_phase") or ""
    result["next_phase"] = data.get("next_phase") or ""
    for phase in data.get("phases") or []:
        status = str(phase.get("status") or "unknown").lower()
        result["counts"][status] += 1
        if status == "blocked" and phase.get("reason"):
            result["blocked_reasons"].append(str(phase["reason"])[:160])
        for key, value in (phase.get("substatuses") or {}).items():
            result["substatuses"][str(key)] = str(value)
    result["counts"] = dict(result["counts"])
    return result


def _engagement_meta(root: Path, now: datetime, days: int) -> dict:
    meta = {"files": {}, "target_model": {}, "coverage": {}, "safety_controls": {}, "evidence": {}, "reports": {}}
    for name in ("engagement.json", "scope.csv", "phase_status.json", "phase_status.miniapp.json", "review_ledger.csv"):
        meta["files"][name] = (root / name).is_file()
    for name, key in (("target-model.md", "target_model"), ("coverage.md", "coverage"), ("safety-controls.md", "safety_controls")):
        p = root / "notes" / name
        meta[key] = {"present": p.is_file(), "relative_path": _safe_ref(str(p), root)}
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8-sig", errors="replace")
                meta[key]["lines"] = len(text.splitlines())
                meta[key]["sections"] = sum(1 for line in text.splitlines() if line.lstrip().startswith("#"))
            except OSError:
                pass
    index = root / "evidence" / "index.csv"
    evidence = []
    if index.is_file():
        try:
            with index.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    sensitivity = (row.get("sensitivity") or "").strip().lower()
                    ref = _safe_ref(row.get("redacted_path") or "", root)
                    if sensitivity == "restricted_local_only" or not ref:
                        continue
                    evidence.append({k: row.get(k, "") for k in ("evidence_id", "finding_id", "captured_at", "sha256", "sensitivity", "retention")}|{"redacted_path": ref})
        except (OSError, csv.Error):
            pass
    meta["evidence"] = {"present": index.is_file(), "report_eligible_count": len(evidence), "refs": evidence[:100]}
    for name in ("findings.json", "meta.json"):
        p = root / "reports" / name
        meta["reports"][name] = {"present": p.is_file(), "relative_path": _safe_ref(str(p), root)}
    return meta


def scan_engagements(engagements_root: Path, days: int, now: datetime) -> list[dict]:
    """深度读取 engagement 工作区；共享 evidence 目录和非标准目录不纳入。"""
    records = []
    if not engagements_root.is_dir():
        return records
    for root in sorted(engagements_root.iterdir()):
        if not root.is_dir() or root.name == "evidence":
            continue
        ledger = root / "review_ledger.csv"
        has_identity = (root / "engagement.json").is_file() or (root / "scope.csv").is_file()
        if not has_identity and not ledger.is_file():
            continue
        fallback = datetime.fromtimestamp(ledger.stat().st_mtime, CST) if ledger.is_file() else now
        rows, by_status, updated_rows, unknown = [], Counter(), 0, Counter()
        if ledger.is_file():
            try:
                with ledger.open(encoding="utf-8-sig", newline="") as f:
                    for raw in csv.DictReader(f):
                        if _row_in_window(raw, fallback, days, now):
                            updated_rows += 1
                        status = (raw.get("status") or "").strip().lower()
                        bucket = _status_bucket(status)
                        by_status[bucket] += 1
                        if bucket == "unknown":
                            unknown[status or "<empty>"] += 1
                        rows.append({k: (raw.get(k) or "").strip() for k in ("item_id", "priority", "category", "asset", "endpoint", "candidate_type", "status", "confidence", "finding_id", "evidence_ref", "updated_at")})
            except (OSError, csv.Error):
                pass
        records.append({"name": root.name, "relative_path": root.relative_to(engagements_root).as_posix(), "ledger_rows": len(rows), "updated_rows": updated_rows, "by_status": dict(by_status), "unknown_statuses": dict(unknown), "phases": {"wz": _phase_snapshot(root / "phase_status.json"), "xcx": _phase_snapshot(root / "phase_status.miniapp.json")}, "meta": _engagement_meta(root, now, days), "rows": rows})
    return records


def collect_engagements(engagements_root: Path, days: int, now: datetime) -> dict:
    records = scan_engagements(engagements_root, days, now)
    stats = {"dirs": len(records), "ledger_rows": sum(r["ledger_rows"] for r in records), "updated_rows": sum(r["updated_rows"] for r in records), "by_status": Counter(), "recent_dirs": [r["name"] for r in records], "records": records}
    for record in records:
        stats["by_status"].update(record["by_status"])
    return stats


def collect_findings(runs_root: Path, days: int, now: datetime) -> Counter:
    c = Counter()
    for d in sorted(runs_root.iterdir() if runs_root.is_dir() else []):
        if not d.is_dir() or not _mtime_within(d, days, now):
            continue
        ws = d / "postrun_review"
        fl = ws / "findings_ledger.csv" if ws.is_dir() else None
        q = ws / "target_review_queue.csv" if ws.is_dir() else None
        if fl is not None and fl.is_file():
            import csv
            with fl.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    st = (row.get("status") or "").strip().lower()
                    if st:
                        c[f"findings_{st}"] += 1
        if q is not None and q.is_file():
            import csv
            with q.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    st = (row.get("disposition") or "pending").strip().lower()
                    c[f"disp_{st}"] += 1
                    # P0/P1 复核存活率（20260822 复盘 P1 KPI）：L0 信号质量最直接的度量
                    if (row.get("priority") or "").strip().upper() in ("P0", "P1") and st != "pending":
                        c["p0p1_total"] += 1
                        # 仍成立的处置：确认/待登录/待审批/被门挡住/接受风险；rejected/duplicate/out_of_scope=死亡
                        if st in ("confirmed", "needs_login", "approval_required", "blocked", "accepted_risk"):
                            c["p0p1_survived"] += 1
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description="周度度量聚合（W10）")
    ap.add_argument("--days", type=int, default=7, help="扫描近 N 天（99999=全量）")
    ap.add_argument("--runs-root", default="runs")
    ap.add_argument("--kb", default="knowledge_base")
    a = ap.parse_args()

    now = datetime.now(CST)
    runs_root = ROOT / a.runs_root
    kb_root = ROOT / a.kb
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)

    runs, incomplete = scan_runs(runs_root, a.days, now)
    n_runs = len(runs)
    cand_sum = sum(r["candidates"] for r in runs)

    # 指标1
    m1 = (cand_sum / n_runs) if n_runs else None

    # 指标2 确认率（queue disposition 近似 + findings_ledger 双口径）
    cnt = collect_findings(runs_root, a.days, now)
    eng = collect_engagements(ROOT / "engagements", a.days, now)
    confirmed = cnt.get("findings_confirmed", 0)
    rejected = cnt.get("disp_rejected", 0)
    denom = confirmed + rejected
    m2 = (confirmed / denom) if denom else None
    disp_confirmed = cnt.get("disp_confirmed", 0)

    # engagement 侧采用归一化状态；candidate/signal/待人工不计入终态分母
    eng_confirmed = eng["by_status"].get("confirmed", 0)
    eng_rejected = eng["by_status"].get("rejected", 0)
    eng_den = eng_confirmed + eng_rejected
    eng_m2 = (eng_confirmed / eng_den) if eng_den else None
    combined_confirmed = confirmed + eng_confirmed
    combined_rejected = rejected + eng_rejected
    combined_den = combined_confirmed + combined_rejected
    combined_m2 = (combined_confirmed / combined_den) if combined_den else None

    # 指标3 人工小时/确认：当前无数据源
    m3 = "N/A（无复核时长数据源；在 postrun_review 记录人工起止时间后启用）"

    # 指标4 FP 率（fp_memory 条数 / 候选总量）
    fp_entries = read_jsonl(kb_root / "fp_memory.jsonl")
    m4 = (len(fp_entries) / cand_sum) if cand_sum else None

    # 指标5 假设命中率
    ledger = read_jsonl(kb_root / "hypothesis_ledger.jsonl")
    tested_c = sum(1 for h in ledger if h.get("status") == "tested_confirmed")
    tested_f = sum(1 for h in ledger if h.get("status") == "tested_falsified")
    m5 = (tested_c / (tested_c + tested_f)) if (tested_c + tested_f) else None

    # 指标6 P0/P1 复核存活率
    p0p1_t, p0p1_s = cnt.get("p0p1_total", 0), cnt.get("p0p1_survived", 0)
    m6 = (p0p1_s / p0p1_t) if p0p1_t else None

    def fmt(x, pct=False):
        if x is None:
            return "N/A"
        return f"{x*100:.1f}%" if pct else f"{x:.2f}"

    # 最吵队列：候选最多的 run 文件
    noisy = Counter()
    for r in runs:
        for fname, n in r["cand_files"]:
            noisy[fname] += n
    noisy_top = noisy.most_common(3)

    date = now.strftime("%Y%m%d")
    md = reports / f"metrics_{date}.md"
    lines = [
        f"# 周度度量 · {date}",
        "",
        f"- 扫描窗口：近 {a.days} 天 · runs 目录 {n_runs} 个 · engagements 工作区 {eng['dirs']} 个 · 生成 {now_iso()}",
        "",
        "## 数据源覆盖",
        "",
        f"- runs：去重后 {n_runs} 个，候选 {cand_sum} 条；缺少 run_summary 的目录 {len(incomplete)} 个。",
        f"- engagements：{eng['dirs']} 个标准工作区，台账 {eng['ledger_rows']} 行，本窗口更新 {eng['updated_rows']} 行。",
        f"- engagement 状态：confirmed={eng_confirmed}，rejected={eng_rejected}，open={eng['by_status'].get('open', 0)}，blocked={eng['by_status'].get('blocked', 0)}，accepted_risk={eng['by_status'].get('accepted_risk', 0)}，unknown={eng['by_status'].get('unknown', 0)}。",
        "- engagement 读取：phase_status.json 与 phase_status.miniapp.json 分开读取；目标模型、覆盖、安全说明和脱敏证据索引仅取结构化摘要。",
        "",
        "## 五指标",
        "",
        "| # | 指标 | 值 | 说明 |",
        "|---|---|---|---|",
        f"| 1 | 每 run 候选数 | {fmt(m1)} | Σ candidates jsonl / run 数（共 {cand_sum} 条候选） |",
        f"| 2 | 确认率（runs 原口径） | {fmt(m2, pct=True)} | findings confirmed={confirmed} / (confirmed+rejected={denom})；queue 侧 confirmed={disp_confirmed} |",
        f"| 2a | 确认率（engagement） | {fmt(eng_m2, pct=True)} | engagement confirmed={eng_confirmed} / (confirmed+rejected={eng_den})；open/blocked 不计入分母 |",
        f"| 2b | 确认率（双源合并） | {fmt(combined_m2, pct=True)} | runs + engagement 的 confirmed={combined_confirmed} / rejected={combined_rejected}；仅用于本周参考 |",
        f"| 3 | 人工小时/确认 | {m3} | |",
        f"| 4 | FP 记忆率 | {fmt(m4, pct=True)} | fp_memory {len(fp_entries)} 条 / 候选 {cand_sum} |",
        f"| 5 | 假设命中率 | {fmt(m5, pct=True)} | ledger tested {tested_c}+{tested_f} |",
        f"| 6 | P0/P1 复核存活率 | {fmt(m6, pct=True)} | 复核后仍成立的 P0/P1（确认/审批门/待登录等）={cnt.get('p0p1_survived',0)} / 已审 P0/P1 总数={cnt.get('p0p1_total',0)}；持续偏低=L0 在产噪声 |",
        "",
        "## 最吵队列（候选最多的来源文件）",
        "",
    ]
    if noisy_top:
        lines += [f"- `{name}`：{n} 条" for name, n in noisy_top]
    else:
        lines.append("- 无候选文件")
    if eng["dirs"]:
        lines += ["", "## engagement 工作区明细", ""]
        for record in eng["records"]:
            phases = record["phases"]
            wz = phases["wz"]
            xcx = phases["xcx"]
            lines.append(
                f"- `{record['relative_path']}`：ledger={record['ledger_rows']}（窗口更新={record['updated_rows']}），"
                f"WZ={wz['current_phase'] or '未提供'}→{wz['next_phase'] or '—'}，"
                f"XCX={xcx['current_phase'] or '未提供'}→{xcx['next_phase'] or '—'}，"
                f"证据索引可报告条目={record['meta']['evidence'].get('report_eligible_count', 0)}。"
            )
    if incomplete:
        lines += ["", "## 数据不全的 run（缺 run_summary.json）", ""]
        lines += [f"- {n}" for n in incomplete[:20]]
    md.write_text("\n".join(lines), encoding="utf-8")

    hist = reports / "metrics_history.jsonl"
    with hist.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "date": date, "generated": now_iso(), "runs_scanned": n_runs,
            "candidates_total": cand_sum,
            "candidates_per_run": round(m1, 3) if m1 is not None else None,
            "confirm_rate": round(m2, 4) if m2 is not None else None,
            "fp_memory_entries": len(fp_entries),
            "hypothesis_hit_rate": round(m5, 4) if m5 is not None else None,
            "findings_confirmed": confirmed, "queue_confirmed": disp_confirmed,
            "engagements_scanned": eng["dirs"], "engagement_ledger_rows": eng["ledger_rows"],
            "engagement_updated_rows": eng["updated_rows"],
            "engagement_confirmed": eng_confirmed, "engagement_rejected": eng_rejected,
            "engagement_open": eng["by_status"].get("open", 0),
            "engagement_blocked": eng["by_status"].get("blocked", 0),
            "combined_confirmed": combined_confirmed, "combined_rejected": combined_rejected,
            "combined_confirm_rate": round(combined_m2, 4) if combined_m2 is not None else None,
            "incomplete_runs": len(incomplete),
        }, ensure_ascii=False) + "\n")

    print(f"[+] 报告 → {md}")
    print(f"[+] history 追加一行 → {hist}")
    print(f"[*] runs={n_runs} 候选={cand_sum} 每run候选={fmt(m1)} 确认率={fmt(m2, pct=True)} FP率={fmt(m4, pct=True)} 假设命中率={fmt(m5, pct=True)}")


if __name__ == "__main__":
    main()
