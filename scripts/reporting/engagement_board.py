#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全目标作战台：跨 engagement 聚合 WZ/XCX 双流程状态、闲置度与待操作员任务。

只读离线工具：只读 engagements/ 与 runs/ 的盘上事实源，不发任何网络请求，
不写任何 engagement 工作区。默认打印到 stdout；--write 落盘对应产物。

用法（canonical）：
    python scripts/reporting/engagement_board.py                    # 总板
    ... engagement_board.py --write                                 # 写 engagements/_BOARD.md
    ... engagement_board.py --tasks [--write]                       # 全部未闭环操作员待办（_TASKS.md）
    ... engagement_board.py --runs 15                               # 最近 run 复核态轻量概览
    ... engagement_board.py --focus <名称子串> [--json] [--write]    # 单目标深看（_FOCUS.md）
    ... engagement_board.py --handoff <名称子串> [--stream wz|xcx] [--write]   # 交接提示词骨架（logs/）
    ... engagement_board.py --submit <名称子串> [--write]           # SRC 提交草稿（logs/）
    ... engagement_board.py --assets                                # 跨目标资产对账
    ... engagement_board.py --json                                  # 机器可读（供 AI 会话开场读取）

状态板判定全部来自盘上游标/台账，本脚本不做任何"完成推断"，只做聚合展示；
候选/待验证条目不等于漏洞结论，处置以各工作区台账与人工复核为准。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

try:  # Windows 控制台 GBK 兜底
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

TZ_CN = timezone(timedelta(hours=8))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGAGEMENTS_DIR = os.path.join(PROJECT_ROOT, "engagements")
RUNS_DIR = os.path.join(PROJECT_ROOT, "runs")
BOARD_PATH = os.path.join(ENGAGEMENTS_DIR, "_BOARD.md")

# 台账中视为"未闭环"的状态（disposition 口径与项目复核台账一致）
OPEN_LEDGER_STATUSES = {
    "candidate",
    "needs_manual_validation",
    "approval_required",
    "pending",
    "needs_login",
    "signal",
    "inconclusive",
}
DONE_LEDGER_STATUSES = {"confirmed", "rejected", "duplicate", "out_of_scope", "accepted_risk", "blocked"}

# phase 条目里视为"已闭"的状态
CLOSED_PHASE_STATUSES = {"complete", "completed", "not_applicable", "skipped", "n/a", "na"}

CLOSED_HINTS = ("关闭", "closed", "结项", "已完成交付", "close")

OPEN_TASK_RE = re.compile(r"^(\s*)- \[ \]\s*(.*)$")
DONE_TASK_RE = re.compile(r"^\s*- \[[xX]\]\s+")


def _now() -> datetime:
    return datetime.now(TZ_CN)


def _parse_ts(value):
    """尽力解析 ISO 时间戳；失败返回 None。"""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_CN)
        return dt
    except ValueError:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=TZ_CN)
            except ValueError:
                return None
    return None


def _read_json(path):
    try:
        with io.open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:
        return None


def _read_csv_rows(path):
    try:
        with io.open(path, encoding="utf-8-sig", newline="") as fh:
            return [dict(r) for r in csv.DictReader(fh)]
    except Exception:
        return []


def _clamp(text, limit=110):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# phase_status 解析（对项目内三种已知形态容错）
# ---------------------------------------------------------------------------

def parse_phase_file(path):
    """返回 dict(stream_kind, current_phase, next_open, done, total, last_ts,
    closed, phases, open_phases)；文件缺失返回 None。"""
    if not os.path.isfile(path):
        return None
    data = _read_json(path)
    if not isinstance(data, dict):
        return None
    raw_phases = data.get("phases")
    if not isinstance(raw_phases, list):
        raw_phases = []

    phases = []
    last_ts = None
    for entry in raw_phases:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("phase") or "").strip()
        status = str(entry.get("status") or "").strip().lower()
        ts = _parse_ts(entry.get("updated_at"))
        if ts and (last_ts is None or ts > last_ts):
            last_ts = ts
        phases.append(
            {
                "phase": name,
                "status": status,
                "required": bool(entry.get("required", True)),
                "reason": str(entry.get("reason") or "").strip(),
                "ts": ts,
            }
        )

    done = sum(1 for p in phases if p["status"] in CLOSED_PHASE_STATUSES)
    open_phases = [p for p in phases if p["status"] not in CLOSED_PHASE_STATUSES]

    current = str(data.get("current_phase") or "").strip()
    closed = False
    if current:
        low = current.lower()
        if low in ("none", "end"):
            closed = str(data.get("last_completed_phase") or "").strip() in ("reporting", "evidence", "cleanup")
        elif any(h in low for h in CLOSED_HINTS):
            closed = True
    elif phases:
        # 旧形态：无顶层 current_phase，用首个未闭 phase 推导当前阶段
        if open_phases:
            current = open_phases[0]["phase"]
        else:
            current = phases[-1]["phase"]
            closed = True
    else:
        current = "(空游标)"

    next_open = open_phases[0]["phase"] if open_phases else ""

    return {
        "current_phase": current,
        "next_open": next_open,
        "done": done,
        "total": len(phases),
        "last_ts": last_ts,
        "closed": closed,
        "phases": phases,
        "open_phases": open_phases,
        "raw": data,
    }


def stream_state(info):
    """把单个流程游标归类为 active / reporting / closed / empty。"""
    if info is None:
        return "empty"
    if info["closed"]:
        return "closed"
    cur = info["current_phase"].lower()
    if cur.startswith("reporting"):
        return "reporting"
    if cur == "(空游标)":
        return "empty"
    return "active"


# ---------------------------------------------------------------------------
# operator_tasks.md 解析
# ---------------------------------------------------------------------------

def parse_operator_tasks(path):
    """返回 (open_tasks, done_count)。open_task 为 dict(line, digest)。"""
    if not os.path.isfile(path):
        return [], 0
    open_tasks, done_count = [], 0
    try:
        with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
            for line in fh:
                m = OPEN_TASK_RE.match(line.rstrip())
                if m:
                    open_tasks.append({"indent": len(m.group(1)), "text": m.group(2).strip()})
                elif DONE_TASK_RE.match(line):
                    done_count += 1
    except Exception:
        return [], 0
    return open_tasks, done_count


# ---------------------------------------------------------------------------
# findings.json / 台账 / 报告
# ---------------------------------------------------------------------------

def parse_findings(path):
    data = _read_json(path)
    if not isinstance(data, dict):
        return None
    counts = {}
    for key in ("confirmed", "candidate", "needs_manual_validation", "accepted_risk", "rejected"):
        val = data.get(key)
        if isinstance(val, list):
            counts[key] = len(val)
    if not counts:
        return None
    return counts


def parse_ledger(path):
    if not os.path.isfile(path):
        return None
    rows = _read_csv_rows(path)
    status_counter = Counter()
    open_items = []
    assets = []
    for row in rows:
        status = (row.get("status") or "").strip().lower()
        status_counter[status] += 1
        active = (row.get("active") or "yes").strip().lower()
        asset = (row.get("asset") or "").strip()
        if asset:
            assets.append(
                {
                    "asset": asset,
                    "item_id": (row.get("item_id") or "").strip(),
                    "status": status,
                    "priority": (row.get("priority") or "").strip(),
                }
            )
        if status in OPEN_LEDGER_STATUSES and active in ("yes", "true", ""):
            open_items.append(
                {
                    "item_id": (row.get("item_id") or "").strip(),
                    "priority": (row.get("priority") or "").strip(),
                    "category": (row.get("category") or "").strip(),
                    "asset": asset,
                    "status": status,
                    "summary": _clamp(row.get("summary") or "", 140),
                }
            )
    return {
        "counter": status_counter,
        "open_items": open_items,
        "assets": assets,
        "total": len(rows),
    }


def engagement_base_name(dirname):
    """从目录名剥离 -xcx-YYYYMMDD / -YYYYMMDD 后缀，得到目标基名（用于关联 runs）。"""
    base = re.sub(r"(-xcx)?-20\d{6}.*$", "", dirname)
    return base or dirname


def latest_linked_run(base_name):
    """在 runs/ 目录名里找 <ts>_<base>_… 形态的最近 run，返回 (日期, 目录名) 或 None。"""
    if not os.path.isdir(RUNS_DIR):
        return None
    best = None
    for name in os.listdir(RUNS_DIR):
        m = re.match(r"^(\d{8})_(\d{6})_(.+)$", name)
        if not m:
            continue
        rest = m.group(3)
        if rest == base_name or rest.startswith(base_name + "_") or rest.startswith(base_name + "-"):
            key = m.group(1) + m.group(2)
            if best is None or key > best[0]:
                best = (key, name)
    if not best:
        return None
    return best[1][:4] + "-" + best[1][4:6] + "-" + best[1][6:8], best[1]


# ---------------------------------------------------------------------------
# engagement 聚合
# ---------------------------------------------------------------------------

def scan_engagement(dirpath):
    dirname = os.path.basename(dirpath)
    eng = {
        "dir": dirname,
        "path": dirpath,
        "streams": {},
        "operator_tasks_open": [],
        "operator_tasks_done": 0,
        "ledger": None,
        "findings": None,
        "reports": [],
        "created_at": None,
        "auth_status": "",
        "last_run": None,
    }

    eng_json = _read_json(os.path.join(dirpath, "engagement.json"))
    if isinstance(eng_json, dict):
        eng["created_at"] = _parse_ts(eng_json.get("created_at"))
        auth = eng_json.get("authorization") or {}
        if isinstance(auth, dict):
            eng["auth_status"] = str(auth.get("status") or "").strip()

    wz = parse_phase_file(os.path.join(dirpath, "phase_status.json"))
    xcx = parse_phase_file(os.path.join(dirpath, "phase_status.miniapp.json"))
    if wz:
        eng["streams"]["WZ"] = wz
    if xcx:
        eng["streams"]["XCX"] = xcx

    open_tasks, done_tasks = parse_operator_tasks(os.path.join(dirpath, "notes", "operator_tasks.md"))
    eng["operator_tasks_open"] = open_tasks
    eng["operator_tasks_done"] = done_tasks

    eng["ledger"] = parse_ledger(os.path.join(dirpath, "review_ledger.csv"))
    eng["findings"] = parse_findings(os.path.join(dirpath, "reports", "findings.json"))

    reports_dir = os.path.join(dirpath, "reports")
    if os.path.isdir(reports_dir):
        for name in sorted(os.listdir(reports_dir)):
            if name.lower().endswith((".md", ".docx", ".json")):
                eng["reports"].append(name)

    eng["base_name"] = engagement_base_name(dirname)
    eng["last_run"] = latest_linked_run(eng["base_name"])
    return eng


def engagement_last_activity(eng):
    timestamps = []
    for info in eng["streams"].values():
        if info["last_ts"]:
            timestamps.append(info["last_ts"])
    if eng["created_at"]:
        timestamps.append(eng["created_at"])
    for sub in ("notes", "reports", "artifacts"):
        sub_dir = os.path.join(eng["path"], sub)
        if os.path.isdir(sub_dir):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(sub_dir), TZ_CN)
                timestamps.append(mtime)
            except OSError:
                pass
    if not timestamps:
        try:
            timestamps.append(datetime.fromtimestamp(os.path.getmtime(eng["path"]), TZ_CN))
        except OSError:
            pass
    return max(timestamps) if timestamps else None


def engagement_state(eng):
    """合并双流程 → active / reporting / closed / init_only。"""
    states = [stream_state(info) for info in eng["streams"].values()]
    if not states:
        return "init_only"
    if all(s == "closed" for s in states):
        return "closed"
    if any(s == "active" for s in states):
        return "active"
    if any(s == "reporting" for s in states):
        return "reporting"
    return "init_only"


STATE_LABEL = {
    "active": "进行中",
    "reporting": "待结项",
    "closed": "已关闭",
    "init_only": "仅初始化",
}

STATE_ICON = {
    "active": "🟡",
    "reporting": "🔵",
    "closed": "⚫",
    "init_only": "⚪",
}


def format_streams(eng):
    parts = []
    for kind in ("WZ", "XCX"):
        info = eng["streams"].get(kind)
        if not info:
            continue
        state = stream_state(info)
        icon = STATE_ICON.get(state, "·")
        prog = f"{info['done']}/{info['total']}"
        cur = info["current_phase"]
        cur_short = _clamp(cur, 46)
        parts.append(f"{kind}{icon}{prog} {cur_short}")
    return "<br>".join(parts) if parts else "—"


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def build_rows(engagements, now=None):
    now = now or _now()
    rows = []
    for eng in engagements:
        state = engagement_state(eng)
        last = engagement_last_activity(eng)
        idle_days = max(0, (now - last).days) if last else None
        rows.append(
            {
                "eng": eng,
                "state": state,
                "last": last,
                "idle": idle_days,
                "open_tasks": len(eng["operator_tasks_open"]),
                "open_ledger": len(eng["ledger"]["open_items"]) if eng["ledger"] else 0,
                "confirmed": eng["ledger"]["counter"].get("confirmed", 0) if eng["ledger"] else 0,
            }
        )
    return rows


def sort_key(row):
    """看板排序：状态分组 → 闲置久的在前 → 待办多的在前。"""
    order = {"active": 0, "reporting": 1, "init_only": 2, "closed": 3}
    last = row["last"]
    last_key = last.timestamp() if last else 0
    return (order.get(row["state"], 9), last_key, -row["open_tasks"])


def collect_status_conflicts(engagements):
    """跨目标口径冲突：同一资产在甲工作区 confirmed、乙工作区 rejected。"""
    asset_status = {}
    for eng in engagements:
        if not eng["ledger"]:
            continue
        for entry in eng["ledger"].get("assets", []):
            key = entry["asset"].lower().rstrip("/.")
            if not key:
                continue
            asset_status.setdefault(key, {}).setdefault(entry["status"], set()).add(eng["dir"])
    conflicts = []
    for key, by_status in asset_status.items():
        confirmed_dirs = by_status.get("confirmed", set())
        rejected_dirs = by_status.get("rejected", set())
        # 真冲突 = 双方无共同工作区；同一工作区内同资产不同条目一确认一否决属正常
        if confirmed_dirs and rejected_dirs and not (confirmed_dirs & rejected_dirs):
            sample = next(
                entry["asset"]
                for eng in engagements
                if eng["ledger"]
                for entry in eng["ledger"].get("assets", [])
                if entry["asset"].lower().rstrip("/.") == key
            )
            conflicts.append((sample, sorted(confirmed_dirs), sorted(rejected_dirs)))
    return sorted(conflicts)


def render_board(rows, now):
    lines = []
    counts = Counter(r["state"] for r in rows)
    total_open_tasks = sum(r["open_tasks"] for r in rows)
    total_open_ledger = sum(r["open_ledger"] for r in rows)

    lines.append("# 全目标作战台")
    lines.append("")
    lines.append(
        f"> 生成时间 {now.strftime('%Y-%m-%d %H:%M')} ｜ "
        f"共 {len(rows)} 目标：🟡进行中 {counts.get('active', 0)} ｜ "
        f"🔵待结项 {counts.get('reporting', 0)} ｜ ⚪仅初始化 {counts.get('init_only', 0)} ｜ "
        f"⚫已关闭 {counts.get('closed', 0)}"
    )
    lines.append(
        f"> 未闭环操作员待办 **{total_open_tasks}** 条 ｜ 台账未闭环条目 **{total_open_ledger}** 条 ｜ "
        f"本板由 scripts/reporting/engagement_board.py 只读聚合，事实源在各 engagement 工作区"
    )
    lines.append("")

    # —— 今日建议 ——
    stale_active = [r for r in rows if r["state"] == "active" and (r["idle"] or 0) >= 3]
    reporting_open = [r for r in rows if r["state"] == "reporting" and r["open_tasks"] > 0]
    if rows:
        lines.append("## 今日建议")
        lines.append("")
        tips = []
        engagements = [r["eng"] for r in rows]
        for sample, c_dirs, r_dirs in collect_status_conflicts(engagements)[:3]:
            tips.append(
                f"- ⚠️ **口径冲突**：`{sample}` 在 {'、'.join(f'`{d}`' for d in c_dirs)} 为 confirmed，"
                f"但在 {'、'.join(f'`{d}`' for d in r_dirs)} 为 rejected——先对齐口径再提交/结项"
            )
        for r in sorted(stale_active, key=lambda x: -(x["idle"] or 0))[:3]:
            streams = "、".join(k for k in r["eng"]["streams"])
            if r["open_tasks"] > 0:
                tips.append(
                    f"- `{r['eng']['dir']}`（{streams}）已闲置 **{r['idle']} 天**，当前 {format_streams(r['eng'])}，"
                    f"且压着 {r['open_tasks']} 条操作员待办"
                )
            else:
                tips.append(
                    f"- `{r['eng']['dir']}`（{streams}）已闲置 **{r['idle']} 天**且无登记待办——"
                    "建议先决断：继续推进下一 phase，还是评估关停"
                )
        for r in sorted(reporting_open, key=lambda x: -x["open_tasks"])[:3]:
            tips.append(
                f"- `{r['eng']['dir']}` 处于待结项且还有 **{r['open_tasks']} 条操作员待办**未闭环，适合先清账再结项"
            )
        if not tips:
            tips.append("- 无明显积压：可从「进行中」表挑一个推进，或跑 `--tasks` 清待办")
        lines.extend(tips)
        lines.append("")

    # —— 总表 ——
    lines.append("## 全目标总表")
    lines.append("")
    lines.append("| 目标 | 状态 | 流程进度 | 最近活动 | 闲置 | 待办 | 台账未闭环 | confirmed | 最近 run |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=sort_key):
        eng = r["eng"]
        last_str = r["last"].strftime("%m-%d %H:%M") if r["last"] else "?"
        idle_str = f"{r['idle']}d" if r["idle"] is not None else "?"
        run_str = ""
        if eng["last_run"]:
            run_str = f"`{eng['last_run'][1][:40]}`"
        lines.append(
            f"| [`{eng['dir']}`]({eng['dir']}) "
            f"| {STATE_ICON.get(r['state'], '')}{STATE_LABEL.get(r['state'], r['state'])} "
            f"| {format_streams(eng)} | {last_str} | {idle_str} "
            f"| {r['open_tasks'] or ''} | {r['open_ledger'] or ''} | {r['confirmed'] or ''} | {run_str} |"
        )
    lines.append("")

    # —— 待操作员任务 Top ——
    task_rows = [r for r in rows if r["open_tasks"]]
    if task_rows:
        lines.append("## 待操作员任务分布（按数量排序）")
        lines.append("")
        lines.append("| 目标 | 未闭环 | 已闭环 | 最近活动 |")
        lines.append("|---|---|---|---|")
        for r in sorted(task_rows, key=lambda x: -x["open_tasks"]):
            last_str = r["last"].strftime("%m-%d") if r["last"] else "?"
            lines.append(
                f"| [`{r['eng']['dir']}`]({r['eng']['dir']}) | {r['open_tasks']} "
                f"| {r['eng']['operator_tasks_done']} | {last_str} |"
            )
        lines.append("")
        lines.append("逐条内容见 `--tasks` 输出或 `--focus <目标>`。")
        lines.append("")

    # —— 台账未闭环 Top ——
    ledger_rows = [r for r in rows if r["open_ledger"] and r["state"] != "closed"]
    if ledger_rows:
        lines.append("## 台账未闭环条目分布（非关闭目标）")
        lines.append("")
        lines.append("| 目标 | candidate | needs_manual_validation | approval_required | 其他未闭环 |")
        lines.append("|---|---|---|---|---|")
        for r in sorted(ledger_rows, key=lambda x: -x["open_ledger"]):
            eng = r["eng"]
            open_items = eng["ledger"]["open_items"] if eng["ledger"] else []
            n_cand = sum(1 for i in open_items if i["status"] == "candidate")
            n_nmv = sum(1 for i in open_items if i["status"] == "needs_manual_validation")
            n_appr = sum(1 for i in open_items if i["status"] == "approval_required")
            other = r["open_ledger"] - n_cand - n_nmv - n_appr
            lines.append(
                f"| [`{eng['dir']}`]({eng['dir']}) | {n_cand or ''} | {n_nmv or ''} "
                f"| {n_appr or ''} | {other or ''} |"
            )
        lines.append("")

    # —— run 复核欠账提示 ——
    sweep_covered = _load_sweep_covered()
    run_names = sorted(
        (n for n in os.listdir(RUNS_DIR) if re.match(r"^\d{8}_\d{6}_", n)),
        reverse=True,
    )[:8] if os.path.isdir(RUNS_DIR) else []
    pending_runs = []
    for n in run_names:
        row = scan_run_row(n, sweep_covered)
        if row and row["queue_pending"]:
            pending_runs.append((row["name"], row["queue_pending"]))
    if pending_runs:
        lines.append("## run 复核欠账")
        lines.append("")
        for name, pending in pending_runs[:3]:
            lines.append(f"- `runs/{name}` 还有 **{pending} 条 target 复核未清**（fh 复核或 `run_lifecycle.py` 看详情）")
        lines.append("")

    lines.append("---")
    lines.append(
        "更多视图：`--tasks` 全部待操作员待办 ｜ `--runs` 最近 run 复核态 ｜ "
        "`--focus <目标>` 单目标深看 ｜ `--handoff <目标>` 交接提示词骨架 ｜ "
        "`--submit <目标>` SRC 提交草稿 ｜ `--assets` 跨目标资产对账 ｜ `--json` 供 AI 会话读盘"
    )
    lines.append("")
    lines.append(
        "*只读聚合：本板不修改任何 engagement/run 数据；候选与待验证条目不等于漏洞结论，"
        "处置仍以各工作区台账与人工复核为准。*"
    )
    return "\n".join(lines) + "\n"


def render_tasks(engagements):
    lines = ["# 全部未闭环操作员待办", ""]
    total = 0
    entries = []
    for eng in engagements:
        if eng["operator_tasks_open"]:
            entries.append(eng)
            total += len(eng["operator_tasks_open"])
    lines.append(f"> 共 **{total}** 条未闭环，分布在 {len(entries)} 个目标 ｜ 生成于 {datetime.now(TZ_CN).strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    for eng in sorted(entries, key=lambda e: -len(e["operator_tasks_open"])):
        lines.append(f"## {eng['dir']}（{len(eng['operator_tasks_open'])} 条）")
        lines.append("")
        streams = "；".join(
            f"{k}: {info['current_phase']}（{info['done']}/{info['total']}）"
            for k, info in eng["streams"].items()
        )
        if streams:
            lines.append(f"> 游标：{streams}")
            lines.append("")
        for t in eng["operator_tasks_open"]:
            text = _clamp(t["text"], 200)
            marker = "  " * (1 if t["indent"] > 0 else 0)
            lines.append(f"- [ ] {marker}{text}")
        lines.append("")
        lines.append(f"原文：`{eng['dir']}/notes/operator_tasks.md`（engagements/ 下）")
        lines.append("")
    return "\n".join(lines) + "\n" if total else "# 全部未闭环操作员待办\n\n（无未闭环待办）\n"


def collect_shared_assets(engagements, target_dir):
    """返回 {asset_display: [其他 engagement dir, ...]}：目标台账资产在其他工作区也出现。"""
    by_asset = {}
    for eng in engagements:
        if not eng["ledger"]:
            continue
        for entry in eng["ledger"].get("assets", []):
            key = entry["asset"].lower().rstrip("/.")
            if not key:
                continue
            by_asset.setdefault(key, {}).setdefault(eng["dir"], []).append(entry)
    result = {}
    for key, dirs in by_asset.items():
        if target_dir not in dirs:
            continue
        others = sorted(d for d in dirs if d != target_dir)
        if others:
            asset_display = dirs[target_dir][0]["asset"]
            result[asset_display] = others
    return result


def render_focus(eng, now, all_engagements=None):
    lines = [f"# 目标聚焦：{eng['dir']}", ""]
    auth = f"授权 {eng['auth_status']}" if eng["auth_status"] else "授权状态未登记"
    lines.append(f"> engagement.json：{auth} ｜ 生成于 {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    for kind in ("WZ", "XCX"):
        info = eng["streams"].get(kind)
        if not info:
            continue
        state = stream_state(info)
        lines.append(
            f"## {kind} 流程：{STATE_LABEL.get(state, state)}（{info['done']}/{info['total']} 阶段闭环）"
        )
        lines.append("")
        if info["open_phases"]:
            nxt = info["open_phases"][0]
            lines.append(f"- 当前阶段：**{info['current_phase']}**")
            if nxt["phase"] != info["current_phase"]:
                lines.append(f"- 下一个未闭阶段：**{nxt['phase']}**")
        else:
            lines.append(f"- 当前阶段：**{info['current_phase']}**（无未闭阶段）")
        if info["phases"]:
            last_p = max(info["phases"], key=lambda p: p["ts"].timestamp() if p["ts"] else 0)
            if last_p["reason"]:
                lines.append(f"- 最近阶段记录：{last_p['phase']} —— {_clamp(last_p['reason'], 160)}")
        lines.append("")
        lines.append("| 阶段 | 状态 | 时间 |")
        lines.append("|---|---|---|")
        for p in info["phases"]:
            ts = p["ts"].strftime("%m-%d %H:%M") if p["ts"] else ""
            mark = "✅" if p["status"] in CLOSED_PHASE_STATUSES else "⬜"
            lines.append(f"| {mark} {p['phase']} | {p['status']} | {ts} |")
        lines.append("")

    if eng["operator_tasks_open"]:
        lines.append(f"## 未闭环操作员待办（{len(eng['operator_tasks_open'])} 条）")
        lines.append("")
        for t in eng["operator_tasks_open"]:
            lines.append(f"- [ ] {_clamp(t['text'], 220)}")
        lines.append("")
    else:
        lines.append("## 未闭环操作员待办")
        lines.append("")
        lines.append("（无）")
        lines.append("")

    if eng["ledger"]:
        counter = eng["ledger"]["counter"]
        open_items = eng["ledger"]["open_items"]
        lines.append(
            f"## 复核台账：共 {eng['ledger']['total']} 条，未闭环 {len(open_items)} 条"
            f"（confirmed {counter.get('confirmed', 0)} / rejected {counter.get('rejected', 0)}"
            f" / accepted_risk {counter.get('accepted_risk', 0)}）"
        )
        lines.append("")
        if open_items:
            lines.append("| L编号 | 优先级 | 类别 | 状态 | 摘要 |")
            lines.append("|---|---|---|---|---|")
            prio_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
            for item in sorted(
                open_items, key=lambda i: (prio_order.get(i["priority"], 9), i["item_id"])
            ):
                lines.append(
                    f"| {item['item_id']} | {item['priority']} | {item['category']} | {item['status']} "
                    f"| {_clamp(item['summary'], 120)} |"
                )
            lines.append("")
    if all_engagements:
        shared = collect_shared_assets(all_engagements, eng["dir"])
        if shared:
            lines.append("## 跨目标共享资产（也在其他工作区台账中出现）")
            lines.append("")
            for asset, others in sorted(shared.items()):
                lines.append(f"- {asset} → {'；'.join(f'`{d}`' for d in others)}")
            lines.append("- 口径差异对账见 `--assets` 总视图；合并结论前先核对各工作区 scope。")
            lines.append("")
    if eng["findings"]:
        lines.append("## 结项 findings 概览")
        lines.append("")
        lines.append(
            "  ".join(f"{k}={v}" for k, v in eng["findings"].items())
        )
        lines.append("")
    if eng["reports"]:
        lines.append("## 报告产物")
        lines.append("")
        for name in eng["reports"][:12]:
            lines.append(f"- `reports/{name}`")
        if len(eng["reports"]) > 12:
            lines.append(f"- …共 {len(eng['reports'])} 个文件")
        lines.append("")
    if eng["last_run"]:
        lines.append(f"## 最近关联 run")
        lines.append("")
        lines.append(f"- `{eng['last_run'][1]}`（{eng['last_run'][0]}）")
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 交接提示词骨架
# ---------------------------------------------------------------------------

STREAM_RANK = {"active": 0, "reporting": 1, "init_only": 2, "closed": 3}


def pick_handoff_stream(eng, stream_hint=None):
    """选交接目标流程：显式指定优先；否则未闭/最新更新的流程优先。"""
    if stream_hint:
        key = stream_hint.upper()
        if key in eng["streams"]:
            return key, eng["streams"][key]
        return None, None
    best_key, best = None, None
    for kind, info in eng["streams"].items():
        rank = STREAM_RANK.get(stream_state(info), 9)
        # rank 小者优先；同 rank 取最近更新
        cand = (-rank, info["last_ts"].timestamp() if info["last_ts"] else 0)
        if best is None or cand > best[0]:
            best, best_key = (cand, info), kind
    return best_key, (best[1] if best else None)


def render_handoff(eng, stream_key, info, now, all_engagements=None):
    rel = f"engagements/{eng['dir']}"
    facts = [
        f"engagements/{eng['dir']}/engagement.json（授权状态：{eng['auth_status'] or '未登记'}）",
    ]
    if os.path.isfile(os.path.join(eng["path"], "scope.csv")):
        facts.append(f"engagements/{eng['dir']}/scope.csv（范围）")
    facts.append(f"engagements/{eng['dir']}/phase_status{'.' + 'miniapp' if stream_key == 'XCX' else ''}.json（{stream_key} 游标）")
    for kind, fname in (("WZ", "phase_status.json"), ("XCX", "phase_status.miniapp.json")):
        if kind != stream_key and os.path.isfile(os.path.join(eng["path"], fname)):
            facts.append(f"engagements/{eng['dir']}/{fname}（{kind} 游标，双游标隔离）")
    facts.extend(
        [
            f"engagements/{eng['dir']}/review_ledger.csv（复核台账，L 编号）",
            f"engagements/{eng['dir']}/notes/operator_tasks.md（操作员待办）",
            f"engagements/{eng['dir']}/notes/phases/（各阶段记录）",
        ]
    )
    other = [k for k in ("WZ", "XCX") if k != stream_key and k in eng["streams"]]
    other_note = ""
    if other:
        o = eng["streams"][other[0]]
        other_note = (
            f"\n- 另一流程 {other[0]}：{stream_state(o)}，当前 {o['current_phase']}"
            f"（{o['done']}/{o['total']}），双游标严格隔离，不要跨写"
        )

    lines = [
        f"# 交接提示词骨架：{eng['dir']}（{stream_key} 流程）",
        "",
        f"> 由 scripts/reporting/engagement_board.py 生成于 {now.strftime('%Y-%m-%d %H:%M')}，"
        "全部内容为盘上事实导航；新会话必须逐项回读事实源核实后再行动，不得只凭本骨架总结。",
        "",
        "## 你接手的目标",
        "",
        f"- 工作区：`{rel}/`",
        f"- 流程：{stream_key}，状态 {STATE_LABEL.get(stream_state(info), stream_state(info))}，"
        f"进度 {info['done']}/{info['total']}，游标 updated_at "
        f"{info['last_ts'].strftime('%Y-%m-%d %H:%M') if info['last_ts'] else '未知'}",
        f"- 当前阶段：{info['current_phase']}"
        + (
            f"；下一个未闭阶段：{info['next_open']}"
            if info["next_open"] and info["next_open"] != info["current_phase"]
            else ""
        ),
        f"- 授权：engagement.json authorization.status={eng['auth_status'] or '未登记'}；"
        "动作边界以 ROE.md 与当前 scope 为准，写操作一律审批门",
        other_note,
        "",
        "## 事实源（接手先读，按序）",
        "",
    ]
    lines.extend(f"- `{f}`" for f in facts)
    lines.append("")

    recent = sorted(
        [p for p in info["phases"] if p["ts"]],
        key=lambda p: p["ts"].timestamp(),
        reverse=True,
    )[:2]
    if recent:
        lines.append("## 最近阶段记录摘要（详情以 notes/phases/ 为准）")
        lines.append("")
        for p in recent:
            lines.append(f"- {p['ts'].strftime('%m-%d %H:%M')} {p['phase']}：{_clamp(p['reason'], 200)}")
        lines.append("")

    if eng["operator_tasks_open"]:
        lines.append(
            f"## 未闭环操作员待办（{len(eng['operator_tasks_open'])} 条，全文见 notes/operator_tasks.md）"
        )
        lines.append("")
        for t in eng["operator_tasks_open"][:12]:
            lines.append(f"- {_clamp(t['text'], 160)}")
        if len(eng["operator_tasks_open"]) > 12:
            lines.append(f"- …其余 {len(eng['operator_tasks_open']) - 12} 条见原文件")
        lines.append("")

    if eng["ledger"] and eng["ledger"]["open_items"]:
        items = eng["ledger"]["open_items"]
        prio_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
        top = sorted(items, key=lambda i: (prio_order.get(i["priority"], 9), i["item_id"]))[:8]
        lines.append(
            f"## 台账未闭环 {len(items)} 条（P1/P2 前 {len(top)} 条，处置以台账 validation_plan 为准）"
        )
        lines.append("")
        for i in top:
            lines.append(
                f"- {i['item_id']}（{i['priority']}/{i['status']}）{i['asset']}：{_clamp(i['summary'], 110)}"
            )
        lines.append("")

    if all_engagements:
        shared = collect_shared_assets(all_engagements, eng["dir"])
        if shared:
            lines.append("## 跨目标共享资产提示")
            lines.append("")
            for asset, others in sorted(shared.items()):
                lines.append(f"- {asset} 也在 {'、'.join(f'`{d}`' for d in others)} 台账中出现——"
                             "处置前先核对各工作区 scope 与口径（--assets 总对账）")
            lines.append("")

    lines.extend(
        [
            "## 由上个会话补全（本骨架不含，接手会话应向上个会话或盘上 phase notes 核实）",
            "",
            "- 目标理解快照：host 地图 / 技术栈 / 入口与认证拓扑 / 已排除攻击面及理由",
            "- 未测空间与原因（负面空间漏记 = 下个会话漏攻击面）",
            "- 本阶段产物与证据引用（artifacts/、evidence/ 路径清单）",
            "",
            "## 接手会话的第一步",
            "",
            f"1. 读 `{rel}/phase_status{'.' + 'miniapp' if stream_key == 'XCX' else ''}.json` 核对游标；",
            "2. 按 ROE.md / scope 核对授权与动作边界；",
            f"3. 从「{info['next_open'] or info['current_phase']}」继续，一次只推进一个 phase，"
            "完成后更新游标并询问操作者继续或交接。",
        ]
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# runs/ 复核态轻量视图（权威判定见 run_lifecycle.py，本处只做聚合概览）
# ---------------------------------------------------------------------------

def _load_sweep_covered():
    """读 knowledge_base/last_sweep.json 的 runs_covered（配方E 沉淀游标）。"""
    sweep_path = os.path.join(PROJECT_ROOT, "knowledge_base", "last_sweep.json")
    data = _read_json(sweep_path)
    if not isinstance(data, dict):
        return set()
    covered = data.get("runs_covered")
    if not isinstance(covered, list):
        return set()
    return {str(c) for c in covered}


def scan_run_row(run_name, sweep_covered=None):
    m = re.match(r"^(\d{8})_(\d{6})_(.+)$", run_name)
    if not m:
        return None
    run_dir = os.path.join(RUNS_DIR, run_name)
    if not os.path.isdir(run_dir):
        return None
    row = {
        "name": run_name,
        "date": f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}",
        "target": m.group(3),
        "queue_total": 0,
        "queue_pending": None,
        "verdicts": 0,
        "state": "",
        "report_draft": os.path.isdir(os.path.join(run_dir, "reports")),
        "awaiting_approval": False,
    }

    postrun = os.path.join(run_dir, "postrun_review")
    queue_path = os.path.join(postrun, "target_review_queue.csv")
    rows = _read_csv_rows(queue_path)
    row["queue_total"] = len(rows)
    if rows:
        row["queue_pending"] = sum(
            1 for r in rows if (r.get("disposition") or "pending") == "pending"
        )
    vdir = os.path.join(postrun, "verdicts")
    if os.path.isdir(vdir):
        row["verdicts"] = len([f for f in os.listdir(vdir) if f.endswith(".json")])

    if not os.path.isdir(postrun):
        row["state"] = "未建复核区"
    elif row["queue_pending"] is None:
        row["state"] = "复核区空"
    elif row["queue_pending"] > 0:
        row["state"] = f"复核中（pending {row['queue_pending']}/{row['queue_total']}）"
    else:
        row["state"] = "复核队列已清"

    ps = _read_json(os.path.join(run_dir, "phase_status.json"))
    if isinstance(ps, dict):
        cursor = str(ps.get("cursor") or "")
        stop_reason = str(ps.get("stop_reason") or "")
        if cursor in ("weak_credential_review", "credential_testing", "exploitability", "approval_gate") or "审批门" in stop_reason:
            row["awaiting_approval"] = True
            row["state"] += " · 停在审批门"
    if sweep_covered and any(run_name in str(c) or str(c) in run_name for c in sweep_covered):
        row["swept"] = True
        row["state"] += " · 已沉淀"
    return row


def render_runs(limit=10):
    if not os.path.isdir(RUNS_DIR):
        return "# 最近 run 复核态\n\n（runs/ 目录不存在）\n"
    eng_bases = {}
    if os.path.isdir(ENGAGEMENTS_DIR):
        for name in os.listdir(ENGAGEMENTS_DIR):
            if not name.startswith(("_", ".")) and os.path.isdir(os.path.join(ENGAGEMENTS_DIR, name)):
                eng_bases.setdefault(engagement_base_name(name), name)
    names = sorted(
        (n for n in os.listdir(RUNS_DIR) if re.match(r"^\d{8}_\d{6}_", n)),
        reverse=True,
    )[:limit]
    sweep_covered = _load_sweep_covered()
    rows = [r for r in (scan_run_row(n, sweep_covered) for n in names) if r]
    lines = [
        "# 最近 run 复核态（轻量概览）",
        "",
        f"> 最近 {len(rows)} 个 run ｜ 生成于 {datetime.now(TZ_CN).strftime('%Y-%m-%d %H:%M')} ｜ "
        "单 run 权威完成态以 `python run_lifecycle.py runs\\<ts>` 为准",
        "",
        "| run | 日期 | 目标 engagement | 队列 | verdicts | 复核态 | 报告草稿 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        queue = (
            f"{r['queue_pending']}/{r['queue_total']} pending"
            if r["queue_pending"] is not None and r["queue_total"] > 0
            else "—"
        )
        target = r["target"]
        eng_dir = ""
        best_len = 0
        for base, dir_name in eng_bases.items():
            if (target == base or target.startswith(base + "_") or target.startswith(base + "-")) and len(base) > best_len:
                eng_dir, best_len = dir_name, len(base)
        eng_cell = f"`engagements/{eng_dir}`" if eng_dir else "—"
        lines.append(
            f"| `runs/{r['name']}` | {r['date']} | {eng_cell} | {queue} | {r['verdicts'] or '—'} "
            f"| {r['state']} | {'有' if r['report_draft'] else '—'} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# SRC 提交草稿（从台账 confirmed 条目汇总；判定权在人工终审）
# ---------------------------------------------------------------------------

PRIORITY_RANK = {
    "P1": 0, "P2": 1, "P3": 2, "P4": 3,
    "high": 1, "medium": 2, "low": 3, "info": 4,
}
PRIORITY_TO_SEVERITY = {
    "P1": "严重", "P2": "高危", "P3": "中危", "P4": "低危",
    "high": "高危", "medium": "中危", "low": "低危", "info": "信息",
}


def extract_confirmed_items(eng):
    rows = _read_csv_rows(os.path.join(eng["path"], "review_ledger.csv"))
    items = []
    for row in rows:
        status = (row.get("status") or "").strip().lower()
        active = (row.get("active") or "yes").strip().lower()
        if status != "confirmed" or active in ("no", "false", "0"):
            continue
        prio = (row.get("priority") or "").strip()
        items.append(
            {
                "item_id": (row.get("item_id") or "").strip(),
                "priority": prio,
                "severity": PRIORITY_TO_SEVERITY.get(prio, "待定"),
                "category": (row.get("category") or "").strip(),
                "asset": (row.get("asset") or "").strip(),
                "endpoint": (row.get("endpoint") or "").strip(),
                "parameter": (row.get("parameter") or "").strip(),
                "role": (row.get("role") or "").strip(),
                "candidate_type": (row.get("candidate_type") or "").strip(),
                "confidence": (row.get("confidence") or "").strip(),
                "summary": (row.get("summary") or "").strip(),
                "validation_result": (row.get("validation_result") or "").strip(),
                "evidence_ref": (row.get("evidence_ref") or "").strip(),
                "source": (row.get("source") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
                "updated_at": (row.get("updated_at") or "").strip(),
            }
        )
    items.sort(key=lambda i: (PRIORITY_RANK.get(i["priority"], 9), i["item_id"]))
    return items


def render_submit(eng, now):
    items = extract_confirmed_items(eng)
    validated = sum(
        1 for i in items if i["validation_result"].upper().startswith(("CONFIRMED", "已确认"))
    )
    lines = [
        f"# SRC 提交草稿：{eng['dir']}",
        "",
        f"> 生成于 {now.strftime('%Y-%m-%d %H:%M')}（scripts/reporting/engagement_board.py --submit，"
        "只读聚合台账 confirmed 条目）。**本文件是草稿不是结论**：candidate/needs_manual_validation "
        "条目一律未收录；confirmed 条目也可能是资产背景记录而非漏洞，是否提交、标题措辞与等级"
        "由人工终审拍板。",
        "",
        f"- confirmed 条目：**{len(items)}** 条（其中 validation_result 以 CONFIRMED 开头的实证型 "
        f"{validated} 条）",
        f"- 未闭环面参考：台账 candidate/needs_manual_validation/approval_required 共 "
        f"{len(eng['ledger']['open_items']) if eng['ledger'] else 0} 条未闭环（不在本草稿内）",
        "",
        "## 提交前检查清单（逐项过，不过不交）",
        "",
        "- [ ] 人工终审：四问门（授权/可触达/可复现/实质影响）逐条过，宁缺勿滥"
        "（平台常见拒收=无法复现、影响不大）",
        "- [ ] 脱敏：草稿与证据不含 Cookie/Token/Session/密码/AppSecret；未脱敏样本数据"
        "仅限 ROE 允许的 3-5 条最小证明且已获操作者允许",
        "- [ ] 截图：平台复现步骤要求逐步截图——把 artifacts/evidence 里已有截图挂到对应步骤，"
        "缺的先补",
        "- [ ] 平台 AI 报告规范：补天有《关于AI生成漏洞报告的行为规范》公告，本草稿是从你自己的"
        "复核台账汇编的事实素材，提交前按公告要求人工改写定稿",
        "- [ ] 重复提交检查：同资产同漏洞族先查平台是否已有收录",
        "",
    ]
    if not items:
        lines.append("（本目标台账无 confirmed 条目，无草稿可生成）")
        return "\n".join(lines) + "\n"

    for idx, i in enumerate(items, 1):
        lines.append(f"## 草稿 {idx}/{len(items)}：{i['item_id']}")
        lines.append("")
        title_hint = i["candidate_type"] or i["category"] or "vulnerability"
        lines.append(f"- **拟提交标题（人工润色）**：{i['asset']} {title_hint}")
        lines.append(f"- **类型/等级**：事件型（厂商资产）· {i['severity']}"
                     f"（台账优先级 {i['priority']}，置信 {i['confidence'] or '未标'}）")
        lines.append(f"- **资产/接口**：{i['asset'] or '—'}{(' ' + i['endpoint']) if i['endpoint'] else ''}"
                     f"{('  参数：' + i['parameter']) if i['parameter'] else ''}"
                     f"{('  角色：' + i['role']) if i['role'] else ''}")
        lines.append(f"- **描述**：{_clamp(i['summary'], 500) or '—'}")
        lines.append(f"- **危害说明（人工补写，勿抄描述）**：")
        lines.append(f"- **复现/验证过程**：{_clamp(i['validation_result'], 700) or '（台账未填 validation_result，补齐再交）'}")
        lines.append(f"- **截图占位**：〔逐步复现截图——从证据文件对应取用〕")
        lines.append(f"- **证据索引**：{i['evidence_ref'] or '—'}")
        extra = []
        if i["source"]:
            extra.append(f"来源 {i['source']}")
        if i["notes"]:
            extra.append(f"备注 {_clamp(i['notes'], 160)}")
        if i["updated_at"]:
            extra.append(f"台账更新 {i['updated_at']}")
        if extra:
            lines.append(f"- **附注**：{'；'.join(extra)}")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_assets(engagements):
    """跨目标资产对账：同一 asset 出现在多个 engagement 台账时汇总展示。"""
    by_asset = {}
    for eng in engagements:
        if not eng["ledger"]:
            continue
        for entry in eng["ledger"].get("assets", []):
            key = entry["asset"].lower().rstrip("/.")
            if not key:
                continue
            by_asset.setdefault(key, []).append(
                {
                    "asset": entry["asset"],
                    "dir": eng["dir"],
                    "item_id": entry["item_id"],
                    "status": entry["status"],
                    "priority": entry["priority"],
                }
            )

    shared = {a: rows for a, rows in by_asset.items() if len({r["dir"] for r in rows}) >= 2}
    lines = [
        "# 跨目标资产对账（台账 asset 字段聚合）",
        "",
        f"> 扫描 {len(engagements)} 个 engagement 台账，共 {sum(len(v) for v in by_asset.values())} 条"
        f" asset 引用、{len(by_asset)} 个不同资产；**跨 ≥2 个目标的资产 {len(shared)} 个** ｜ "
        f"生成于 {datetime.now(TZ_CN).strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    if not shared:
        lines.append("（没有跨目标共享资产）")
        return "\n".join(lines) + "\n"

    lines.append("| 资产 | 覆盖目标数 | 目标（L 编号/状态） |")
    lines.append("|---|---|---|")
    for asset, rows in sorted(shared.items(), key=lambda kv: (-len({r["dir"] for r in kv[1]}), kv[0])):
        engs = sorted({r["dir"] for r in rows})
        detail = "；".join(
            f"{r['dir']}:{r['item_id']}({r['status']})" for r in sorted(rows, key=lambda r: (r["dir"], r["item_id"]))
        )
        lines.append(f"| {rows[0]['asset']} | {len(engs)} | {detail} |")
    lines.append("")
    lines.append(
        "*用途：同一资产在不同目标工作区的结论/口径差异一目了然；合并引用或统一处置前"
        "先核对各工作区 scope 是否一致。*"
    )
    return "\n".join(lines) + "\n"


def build_json(engagements, now):
    rows = build_rows(engagements, now)
    out = {
        "generated_at": now.isoformat(),
        "tool": "scripts/reporting/engagement_board.py",
        "readonly": True,
        "summary": dict(Counter(r["state"] for r in rows)),
        "total_open_operator_tasks": sum(r["open_tasks"] for r in rows),
        "total_open_ledger_items": sum(r["open_ledger"] for r in rows),
        "attention_queue": [],
        "engagements": [],
    }
    for r in sorted(rows, key=sort_key)[:5]:
        if r["state"] == "closed" and not r["open_tasks"]:
            continue
        streams_active = [
            f"{k}:{info['next_open'] or info['current_phase']}"
            for k, info in r["eng"]["streams"].items()
            if stream_state(info) == "active"
        ]
        out["attention_queue"].append(
            {
                "dir": r["eng"]["dir"],
                "state": r["state"],
                "idle_days": r["idle"],
                "hint": (
                    f"清 {r['open_tasks']} 条待办" if r["open_tasks"]
                    else ("推进 " + "；".join(streams_active) if streams_active else "决断推进或关停")
                ),
            }
        )
    for r in sorted(rows, key=sort_key):
        eng = r["eng"]
        entry = {
            "dir": eng["dir"],
            "path": eng["path"],
            "state": r["state"],
            "last_activity": r["last"].isoformat() if r["last"] else None,
            "idle_days": r["idle"],
            "streams": {},
            "open_operator_tasks": r["open_tasks"],
            "operator_tasks_done": eng["operator_tasks_done"],
            "ledger_open": r["open_ledger"],
            "ledger_confirmed": r["confirmed"],
            "findings": eng["findings"],
            "last_run": eng["last_run"][1] if eng["last_run"] else None,
            "next_actions": [],
        }
        for kind, info in eng["streams"].items():
            entry["streams"][kind] = {
                "state": stream_state(info),
                "current_phase": info["current_phase"],
                "next_open_phase": info["next_open"],
                "done": info["done"],
                "total": info["total"],
                "closed": info["closed"],
            }
            if stream_state(info) == "active" and info["open_phases"]:
                entry["next_actions"].append(
                    f"{kind}: 推进阶段 {info['open_phases'][0]['phase']}"
                )
        if r["open_tasks"]:
            entry["next_actions"].append(f"清 {r['open_tasks']} 条操作员待办（notes/operator_tasks.md）")
        if r["open_tasks"]:
            entry["task_digests"] = [
                _clamp(t["text"], 120) for t in eng["operator_tasks_open"][:8]
            ]
            if r["open_tasks"] > 8:
                entry["task_digests"].append(f"…其余 {r['open_tasks'] - 8} 条见 notes/operator_tasks.md")
        if eng["ledger"] and eng["ledger"]["open_items"]:
            prio_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
            entry["ledger_top"] = [
                {
                    "item_id": i["item_id"],
                    "priority": i["priority"],
                    "status": i["status"],
                    "summary": _clamp(i["summary"], 90),
                }
                for i in sorted(
                    eng["ledger"]["open_items"],
                    key=lambda i: (prio_order.get(i["priority"], 9), i["item_id"]),
                )[:5]
            ]
        out["engagements"].append(entry)
    return out


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def discover_engagements():
    if not os.path.isdir(ENGAGEMENTS_DIR):
        return []
    result = []
    for name in sorted(os.listdir(ENGAGEMENTS_DIR)):
        if name.startswith("_") or name.startswith("."):
            continue
        dirpath = os.path.join(ENGAGEMENTS_DIR, name)
        if os.path.isdir(dirpath) and os.path.isfile(os.path.join(dirpath, "engagement.json")):
            result.append(scan_engagement(dirpath))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="全目标作战台：跨 engagement 只读聚合状态板")
    parser.add_argument("--write", action="store_true", help="落盘对应产物（总板 engagements/_BOARD.md、--tasks _TASKS.md、--focus _FOCUS.md、--handoff/--submit 落目标 logs/）")
    parser.add_argument("--tasks", action="store_true", help="列出全部未闭环操作员待办")
    parser.add_argument("--runs", metavar="N", nargs="?", const="10", type=str, help="最近 N 个 run 的复核态概览（默认 10）")
    parser.add_argument("--focus", metavar="名称子串", help="单目标深看（目录名子串匹配，取最新）")
    parser.add_argument("--handoff", metavar="名称子串", help="生成自包含交接提示词骨架（配合 --stream）")
    parser.add_argument("--submit", metavar="名称子串", help="从台账 confirmed 条目生成 SRC 提交草稿")
    parser.add_argument("--assets", action="store_true", help="跨目标资产对账（台账 asset 聚合）")
    parser.add_argument("--stream", choices=("wz", "xcx"), help="交接目标流程（默认自动选未闭/最新流程）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--quiet", action="store_true", help="--write 时不回显全文，只打印落盘路径")
    args = parser.parse_args(argv)

    engagements = discover_engagements()
    now = _now()

    if args.focus:
        matches = [e for e in engagements if args.focus.lower() in e["dir"].lower()]
        if not matches:
            print(f"未找到匹配目标：{args.focus}（共 {len(engagements)} 个 engagement）")
            return 2
        matches.sort(key=lambda e: (engagement_last_activity(e) or datetime.min.replace(tzinfo=TZ_CN)), reverse=True)
        eng = matches[0]
        if args.json:
            print(json.dumps(build_json([eng], now), ensure_ascii=False, indent=2))
            return 0
        text = render_focus(eng, now, engagements)
        if args.write:
            out = os.path.join(matches[0]["path"], "_FOCUS.md")
            with io.open(out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"已写入：{out}")
            if not args.quiet:
                print(text)
        else:
            print(text)
        return 0

    if args.handoff:
        matches = [e for e in engagements if args.handoff.lower() in e["dir"].lower()]
        if not matches:
            print(f"未找到匹配目标：{args.handoff}（共 {len(engagements)} 个 engagement）")
            return 2
        matches.sort(
            key=lambda e: (engagement_last_activity(e) or datetime.min.replace(tzinfo=TZ_CN)),
            reverse=True,
        )
        eng = matches[0]
        stream_key, info = pick_handoff_stream(eng, args.stream)
        if info is None:
            print(f"目标 {eng['dir']} 没有{'指定的' if args.stream else '任何'}流程游标可交接")
            return 2
        text = render_handoff(eng, stream_key, info, now, engagements)
        if args.write:
            logs_dir = os.path.join(eng["path"], "logs")
            os.makedirs(logs_dir, exist_ok=True)
            stamp = now.strftime("%Y%m%d_%H%M")
            out = os.path.join(logs_dir, f"handoff_skeleton_{stream_key.lower()}_{stamp}.md")
            with io.open(out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"已写入：{out}")
            if not args.quiet:
                print(text)
        else:
            print(text)
        return 0

    if args.runs:
        try:
            limit = max(1, min(50, int(args.runs)))
        except ValueError:
            limit = 10
        text = render_runs(limit)
        if args.write:
            runs_path = os.path.join(ENGAGEMENTS_DIR, "_RUNS.md")
            with io.open(runs_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"已写入：{runs_path}")
            if not args.quiet:
                print(text)
        else:
            print(text)
        return 0

    if args.submit:
        matches = [e for e in engagements if args.submit.lower() in e["dir"].lower()]
        if not matches:
            print(f"未找到匹配目标：{args.submit}（共 {len(engagements)} 个 engagement）")
            return 2
        matches.sort(
            key=lambda e: (engagement_last_activity(e) or datetime.min.replace(tzinfo=TZ_CN)),
            reverse=True,
        )
        eng = matches[0]
        text = render_submit(eng, now)
        if args.write:
            logs_dir = os.path.join(eng["path"], "logs")
            os.makedirs(logs_dir, exist_ok=True)
            out = os.path.join(logs_dir, f"src_submit_draft_{now.strftime('%Y%m%d_%H%M')}.md")
            with io.open(out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"已写入：{out}")
            if not args.quiet:
                print(text)
        else:
            print(text)
        return 0

    if args.assets:
        text = render_assets(engagements)
        if args.write:
            assets_path = os.path.join(ENGAGEMENTS_DIR, "_ASSETS.md")
            with io.open(assets_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"已写入：{assets_path}")
            if not args.quiet:
                print(text)
        else:
            print(text)
        return 0

    if args.json:
        print(json.dumps(build_json(engagements, now), ensure_ascii=False, indent=2))
        return 0

    if args.tasks:
        text = render_tasks(engagements)
        if args.write:
            tasks_path = os.path.join(ENGAGEMENTS_DIR, "_TASKS.md")
            with io.open(tasks_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"已写入：{tasks_path}")
            if not args.quiet:
                print(text)
        else:
            print(text)
        return 0

    text = render_board(build_rows(engagements, now), now)
    if args.write:
        with io.open(BOARD_PATH, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"已写入：{BOARD_PATH}")
        if not args.quiet:
            print(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
