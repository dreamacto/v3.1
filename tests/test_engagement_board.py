# -*- coding: utf-8 -*-
"""engagement_board（全目标作战台）离线单元测试。

只用 tmp_path 合成 engagement 工作区，不触真实 engagements/，不发网络请求。
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "reporting"
    / "engagement_board.py"
)
_spec = importlib.util.spec_from_file_location("engagement_board", _MODULE_PATH)
eb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eb)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _make_engagement(
    root: Path,
    name: str,
    *,
    wz=None,
    xcx=None,
    tasks_open=(),
    tasks_done=0,
    ledger_rows=(),
    with_eng_json=True,
):
    d = root / "engagements" / name
    (d / "notes").mkdir(parents=True, exist_ok=True)
    if with_eng_json:
        (d / "engagement.json").write_text(
            json.dumps({"created_at": "2026-09-01T10:00:00+08:00",
                        "authorization": {"status": "confirmed"}}, ensure_ascii=False),
            encoding="utf-8",
        )
    for kind, payload in (("phase_status.json", wz), ("phase_status.miniapp.json", xcx)):
        if payload is not None:
            (d / kind).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    task_lines = [f"- [ ] {t}" for t in tasks_open] + [f"- [x] done{i}" for i in range(tasks_done)]
    if task_lines:
        (d / "notes" / "operator_tasks.md").write_text("\n".join(task_lines) + "\n", encoding="utf-8")

    if ledger_rows:
        header = "item_id,active,priority,status,summary"
        lines = [header]
        for row in ledger_rows:
            lines.append(row if isinstance(row, str) else ",".join(row))
        (d / "review_ledger.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(eb, "ENGAGEMENTS_DIR", str(tmp_path / "engagements"))
    monkeypatch.setattr(eb, "RUNS_DIR", str(tmp_path / "runs"))
    return tmp_path


# ---------------------------------------------------------------------------
# phase_status 解析
# ---------------------------------------------------------------------------

def test_parse_modern_reporting_cursor(workspace):
    d = _make_engagement(
        workspace, "a.com",
        wz={"current_phase": "reporting", "last_completed_phase": "reporting",
            "phases": [{"phase": "scope", "status": "complete"},
                       {"phase": "reporting", "status": "complete"}]},
    )
    info = eb.parse_phase_file(str(d / "phase_status.json"))
    assert info is not None
    assert info["total"] == 2 and info["done"] == 2
    assert eb.stream_state(info) == "reporting"
    assert info["closed"] is False


def test_parse_active_cursor_finds_next_open(workspace):
    d = _make_engagement(
        workspace, "b.com",
        wz={"current_phase": "unauth", "phases": [
            {"phase": "scope", "status": "complete"},
            {"phase": "unauth", "status": "in_progress"},
            {"phase": "auth", "status": "pending"}]},
    )
    info = eb.parse_phase_file(str(d / "phase_status.json"))
    assert eb.stream_state(info) == "active"
    assert info["next_open"] == "unauth"
    assert info["done"] == 1 and info["total"] == 3


def test_parse_legacy_shape_without_current_phase(workspace):
    d = _make_engagement(
        workspace, "c.com",
        wz={"phases": [{"phase": "scope", "status": "complete"},
                       {"phase": "preflight", "status": "pending"}]},
    )
    info = eb.parse_phase_file(str(d / "phase_status.json"))
    assert info["current_phase"] == "preflight"
    assert eb.stream_state(info) == "active"


def test_closed_markers_none_end_and_text(workspace):
    cases = [
        ("none", "reporting", "closed"),
        ("end", "reporting", "closed"),
        ("reporting（完成，engagement 关闭态）", "reporting", "closed"),
        ("reporting", "reporting", "reporting"),
    ]
    for i, (cur, last, expected) in enumerate(cases):
        d = _make_engagement(
            workspace, f"x{i}.com",
            wz={"current_phase": cur, "last_completed_phase": last,
                "phases": [{"phase": "reporting", "status": "complete"}]},
        )
        info = eb.parse_phase_file(str(d / "phase_status.json"))
        assert eb.stream_state(info) == expected, (cur, expected)


# ---------------------------------------------------------------------------
# operator_tasks / ledger / 基名
# ---------------------------------------------------------------------------

def test_operator_task_parsing(workspace):
    d = _make_engagement(workspace, "d.com", tasks_open=("任务A", "任务B"), tasks_done=3)
    open_tasks, done = eb.parse_operator_tasks(str(d / "notes" / "operator_tasks.md"))
    assert done == 3
    assert [t["text"] for t in open_tasks] == ["任务A", "任务B"]


def test_ledger_open_filter_respects_active_column(workspace):
    rows = [
        ("L1,yes,P1,candidate,\"待验证\"",),
        ("L2,no,P2,candidate,\"已失效候选\"",),
        ("L3,yes,P1,confirmed,\"已确认\"",),
        ("L4,yes,P3,needs_manual_validation,\"待人工\"",),
    ]
    flat = [r[0] for r in rows]
    d = _make_engagement(workspace, "e.com", ledger_rows=flat)
    ledger = eb.parse_ledger(str(d / "review_ledger.csv"))
    assert ledger["counter"]["candidate"] == 2
    ids = {i["item_id"] for i in ledger["open_items"]}
    assert ids == {"L1", "L4"}


def test_engagement_base_name_strips_suffixes():
    assert eb.engagement_base_name("jlc.com") == "jlc.com"
    assert eb.engagement_base_name("little-galley-xcx-20260906") == "little-galley"
    assert eb.engagement_base_name("woyaoce.cn-20260830") == "woyaoce.cn"


# ---------------------------------------------------------------------------
# 聚合与输出
# ---------------------------------------------------------------------------

def test_discover_skips_non_engagement_dirs(workspace):
    _make_engagement(workspace, "f.com", wz={"current_phase": "reporting", "phases": []})
    (workspace / "engagements" / "evidence").mkdir(parents=True)
    (workspace / "engagements" / "_BOARD.md").write_text("x", encoding="utf-8")
    engs = eb.discover_engagements()
    assert [e["dir"] for e in engs] == ["f.com"]


def test_engagement_state_merges_streams(workspace):
    _make_engagement(
        workspace, "g.com",
        wz={"current_phase": "reporting", "phases": [{"phase": "reporting", "status": "complete"}]},
        xcx={"current_phase": "static_analysis", "phases": [
            {"phase": "identity", "status": "complete"},
            {"phase": "static_analysis", "status": "in_progress"}]},
    )
    engs = eb.discover_engagements()
    assert eb.engagement_state(engs[0]) == "active"


def test_board_render_and_json_totals(workspace, capsys):
    _make_engagement(
        workspace, "h.com",
        wz={"current_phase": "unauth", "phases": [{"phase": "unauth", "status": "in_progress"}]},
        tasks_open=("补抓分包", "归属决断"),
        ledger_rows=("h-L1,yes,P2,candidate,\"摘要\"",),
    )
    engs = eb.discover_engagements()
    rows = eb.build_rows(engs)
    board = eb.render_board(rows, eb._now())
    assert "全目标总表" in board
    assert "待操作员任务分布" in board
    assert "h.com" in board

    payload = eb.build_json(engs, eb._now())
    assert payload["total_open_operator_tasks"] == 2
    assert payload["total_open_ledger_items"] == 1
    entry = payload["engagements"][0]
    assert entry["state"] == "active"
    assert entry["streams"]["WZ"]["next_open_phase"] == "unauth"
    assert any("操作员待办" in a for a in entry["next_actions"])

    tasks_md = eb.render_tasks(engs)
    assert "补抓分包" in tasks_md and "归属决断" in tasks_md


def test_focus_renders_phase_table(workspace):
    _make_engagement(
        workspace, "i.com",
        wz={"current_phase": "scope", "phases": [
            {"phase": "authorization", "status": "complete"},
            {"phase": "scope", "status": "in_progress"}]},
        tasks_open=("确认窗口",),
    )
    engs = eb.discover_engagements()
    text = eb.render_focus(engs[0], eb._now())
    assert "authorization" in text and "确认窗口" in text


def test_main_json_runs_without_touching_real_workspace(workspace, capsys):
    _make_engagement(workspace, "j.com", xcx={"current_phase": "reporting", "phases": []})
    rc = eb.main(["--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["engagements"][0]["dir"] == "j.com"


# ---------------------------------------------------------------------------
# 交接骨架
# ---------------------------------------------------------------------------

def test_pick_handoff_stream_prefers_active_over_reporting(workspace):
    _make_engagement(
        workspace, "k.com",
        wz={"current_phase": "reporting", "phases": [{"phase": "reporting", "status": "complete"}]},
        xcx={"current_phase": "static_analysis", "phases": [
            {"phase": "static_analysis", "status": "in_progress"}]},
    )
    eng = eb.discover_engagements()[0]
    key, info = eb.pick_handoff_stream(eng)
    assert key == "XCX"
    assert eb.stream_state(info) == "active"
    # 显式指定覆盖自动选择
    key2, _ = eb.pick_handoff_stream(eng, "wz")
    assert key2 == "WZ"


def test_render_handoff_contains_facts_and_disclaimer(workspace):
    _make_engagement(
        workspace, "m.com",
        xcx={"current_phase": "host_classification", "phases": [
            {"phase": "identity", "status": "complete"},
            {"phase": "host_classification", "status": "in_progress"}]},
        tasks_open=("主体确认",),
        ledger_rows=("m-L1,yes,P1,candidate,\"待验证摘要\"",),
    )
    eng = eb.discover_engagements()[0]
    key, info = eb.pick_handoff_stream(eng)
    text = eb.render_handoff(eng, key, info, eb._now())
    assert "不得只凭本骨架总结" in text
    assert "phase_status.miniapp.json" in text
    assert "phase_status.json（WZ 游标）" not in text  # 不存在的不列
    assert "主体确认" in text
    assert "m-L1" in text
    assert "host_classification" in text


def test_main_handoff_matches_and_missing(workspace, capsys):
    _make_engagement(
        workspace, "n.com",
        wz={"current_phase": "scope", "phases": [{"phase": "scope", "status": "pending"}]},
    )
    assert eb.main(["--handoff", "n.com"]) == 0
    out = capsys.readouterr().out
    assert "n.com" in out and "WZ 流程" in out
    assert eb.main(["--handoff", "不存在的目标"]) == 2
    assert "未找到匹配目标" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# runs 复核态
# ---------------------------------------------------------------------------

def test_scan_run_row_states(workspace):
    runs_dir = workspace / "runs"
    # 未建复核区
    r1 = runs_dir / "20260901_000001_a.com_one_click"
    r1.mkdir(parents=True)
    (r1 / "run_summary.json").write_text("{}", encoding="utf-8")
    # 复核中
    r2 = runs_dir / "20260902_000000_b.com_one_click"
    (r2 / "postrun_review" / "verdicts").mkdir(parents=True)
    (r2 / "postrun_review" / "target_review_queue.csv").write_text(
        "target,disposition\nt1,pending\nt2,confirmed\n", encoding="utf-8"
    )
    (r2 / "postrun_review" / "verdicts" / "1.json").write_text("{}", encoding="utf-8")
    # 队列已清 + 审批门
    r3 = runs_dir / "20260903_000000_c.com_one_click"
    (r3 / "postrun_review").mkdir(parents=True)
    (r3 / "postrun_review" / "target_review_queue.csv").write_text(
        "target,disposition\nt1,rejected\n", encoding="utf-8"
    )
    (r3 / "phase_status.json").write_text(
        json.dumps({"cursor": "approval_gate"}), encoding="utf-8"
    )

    row1 = eb.scan_run_row("20260901_000001_a.com_one_click")
    assert row1["state"] == "未建复核区" and row1["date"] == "2026-09-01"
    row2 = eb.scan_run_row("20260902_000000_b.com_one_click")
    assert "pending 1/2" in row2["state"] and row2["verdicts"] == 1
    row3 = eb.scan_run_row("20260903_000000_c.com_one_click")
    assert "审批门" in row3["state"]
    assert eb.scan_run_row("not_a_run") is None

    text = eb.render_runs(10)
    assert "a.com_one_click" in text and "复核态以" in text or "权威" in text


def test_main_runs_mode(workspace, capsys):
    (workspace / "runs" / "20260904_000000_d.com_x").mkdir(parents=True)
    rc = eb.main(["--runs", "5"])
    assert rc == 0
    assert "20260904_000000_d.com_x" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# SRC 提交草稿
# ---------------------------------------------------------------------------

def test_submit_extracts_and_sorts_confirmed(workspace):
    rows = [
        "s-L2,yes,P2,confirmed,\"高危已确认\"",
        "s-L1,yes,P1,confirmed,\"严重已确认\"",
        "s-L3,yes,P3,candidate,\"候选不收录\"",
        "s-L4,no,P1,confirmed,\"失效不收录\"",
        "s-L5,yes,P3,needs_manual_validation,\"待人工不收录\"",
    ]
    _make_engagement(workspace, "p.com", ledger_rows=rows)
    eng = eb.discover_engagements()[0]
    items = eb.extract_confirmed_items(eng)
    assert [i["item_id"] for i in items] == ["s-L1", "s-L2"]
    assert items[0]["severity"] == "严重" and items[1]["severity"] == "高危"

    text = eb.render_submit(eng, eb._now())
    assert "提交前检查清单" in text
    assert "脱敏" in text
    assert "s-L1" in text and "s-L2" in text
    assert "候选不收录" not in text and "失效不收录" not in text and "待人工不收录" not in text


def test_submit_empty_ledger_renders_placeholder(workspace):
    _make_engagement(workspace, "q.com")
    eng = eb.discover_engagements()[0]
    text = eb.render_submit(eng, eb._now())
    assert "无 confirmed 条目" in text


def test_main_submit_missing(workspace, capsys):
    _make_engagement(workspace, "r.com")
    assert eb.main(["--submit", "不存在"]) == 2
    assert "未找到匹配目标" in capsys.readouterr().out
    assert eb.main(["--submit", "r.com"]) == 0
    assert "SRC 提交草稿" in capsys.readouterr().out


def test_handoff_and_submit_write_into_logs(workspace, capsys):
    ledger_rows = ("t-L1,yes,P2,confirmed,\"已确认摘要\"",)
    _make_engagement(
        workspace, "s.com",
        wz={"current_phase": "unauth", "phases": [{"phase": "unauth", "status": "in_progress"}]},
        tasks_open=("补会话凭证",),
        ledger_rows=ledger_rows,
    )
    assert eb.main(["--handoff", "s.com", "--write", "--quiet"]) == 0
    assert eb.main(["--submit", "s.com", "--write", "--quiet"]) == 0
    logs_dir = workspace / "engagements" / "s.com" / "logs"
    files = sorted(p.name for p in logs_dir.iterdir())
    assert any(n.startswith("handoff_skeleton_wz_") for n in files), files
    assert any(n.startswith("src_submit_draft_") for n in files), files


def test_scan_run_row_links_swept_state(workspace):
    runs_dir = workspace / "runs"
    (runs_dir / "20260905_000000_u.com_one_click").mkdir(parents=True)
    kb = workspace / "knowledge_base"
    kb.mkdir(parents=True)
    (kb / "last_sweep.json").write_text(
        json.dumps({"runs_covered": ["20260905_000000_u.com_one_click"]}), encoding="utf-8"
    )
    row = eb.scan_run_row("20260905_000000_u.com_one_click", eb._load_sweep_covered())
    assert "已沉淀" in row["state"]


# ---------------------------------------------------------------------------
# 跨目标资产对账
# ---------------------------------------------------------------------------

def test_render_assets_flags_cross_target(workspace):
    rows_v = ("v-L1,yes,P1,confirmed,\"A站确认\"",)
    rows_w = ("w-L1,yes,P2,rejected,\"B站否掉同一资产\"",)
    rows_x = ("x-L1,yes,P3,candidate,\"仅本目标\"",)
    d1 = _make_engagement(workspace, "v.com", ledger_rows=rows_v)
    d2 = _make_engagement(workspace, "w.com", ledger_rows=rows_w)
    _make_engagement(workspace, "x.com", ledger_rows=rows_x)
    for d, asset in ((d1, "api.shared.com"), (d2, "api.shared.com"), (None, None)):
        if d is None:
            continue
        path = d / "review_ledger.csv"
        text = path.read_text(encoding="utf-8")
        text = text.replace("v.com", "") .replace("w.com", "")
        rows = text.splitlines()
        rows[0] = rows[0] + ",asset"
        rows[1] = rows[1] + "," + asset
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    (workspace / "engagements" / "x.com" / "review_ledger.csv").write_text(
        "item_id,active,priority,status,summary,asset\n"
        "x-L1,yes,P3,candidate,\"仅本目标\",only-x.com\n",
        encoding="utf-8",
    )
    engs = eb.discover_engagements()
    text = eb.render_assets(engs)
    assert "api.shared.com" in text
    assert "跨 ≥2 个目标的资产 1 个" in text
    assert "v-L1" in text and "w-L1" in text
    assert "only-x.com" not in text  # 单目标资产不进表


# ---------------------------------------------------------------------------
# 解析器边界加固
# ---------------------------------------------------------------------------

def test_parse_edge_cases_are_tolerant(tmp_path):
    d = tmp_path / "e.com"
    d.mkdir(parents=True)
    # 空 phases + 无 current_phase
    (d / "phase_status.json").write_text("{}", encoding="utf-8")
    info = eb.parse_phase_file(str(d / "phase_status.json"))
    assert info is not None and info["total"] == 0 and info["current_phase"] == "(空游标)"
    # 坏 JSON
    (d / "phase_status.json").write_text("{not json", encoding="utf-8")
    assert eb.parse_phase_file(str(d / "phase_status.json")) is None
    # phase 条目缺 status/updated_at
    (d / "phase_status.json").write_text(
        json.dumps({"phases": [{"phase": "scope"}]}), encoding="utf-8"
    )
    info = eb.parse_phase_file(str(d / "phase_status.json"))
    assert info["total"] == 1 and eb.stream_state(info) == "active"
    # 只有表头的台账 + BOM/CRLF
    (d / "review_ledger.csv").write_bytes(
        b"\xef\xbb\xbfitem_id,active,priority,status,summary\r\n"
    )
    ledger = eb.parse_ledger(str(d / "review_ledger.csv"))
    assert ledger is not None and ledger["total"] == 0 and ledger["open_items"] == []


def test_collect_status_conflicts_requires_disjoint_workspaces(workspace):
    # 真冲突：甲工作区 confirmed，乙工作区 rejected
    (workspace / "engagements" / "v.com" / "notes").mkdir(parents=True)
    (workspace / "engagements" / "v.com" / "engagement.json").write_text("{}", encoding="utf-8")
    (workspace / "engagements" / "v.com" / "review_ledger.csv").write_text(
        "item_id,active,priority,status,summary,asset\n"
        "v-L1,yes,P1,confirmed,\"A站确认\",api.shared.com\n",
        encoding="utf-8",
    )
    (workspace / "engagements" / "w.com" / "notes").mkdir(parents=True)
    (workspace / "engagements" / "w.com" / "engagement.json").write_text("{}", encoding="utf-8")
    (workspace / "engagements" / "w.com" / "review_ledger.csv").write_text(
        "item_id,active,priority,status,summary,asset\n"
        "w-L1,yes,P2,rejected,\"B站否掉\",api.shared.com\n",
        encoding="utf-8",
    )
    # 同工作区混态：一 confirmed 一 rejected，不应报冲突
    (workspace / "engagements" / "x.com" / "notes").mkdir(parents=True)
    (workspace / "engagements" / "x.com" / "engagement.json").write_text("{}", encoding="utf-8")
    (workspace / "engagements" / "x.com" / "review_ledger.csv").write_text(
        "item_id,active,priority,status,summary,asset\n"
        "x-L1,yes,P1,confirmed,\"确认\",solo.x.com\n"
        "x-L2,yes,P2,rejected,\"否决\",solo.x.com\n",
        encoding="utf-8",
    )
    engs = eb.discover_engagements()
    conflicts = eb.collect_status_conflicts(engs)
    assert len(conflicts) == 1
    asset, c_dirs, r_dirs = conflicts[0]
    assert asset == "api.shared.com"
    assert c_dirs == ["v.com"] and r_dirs == ["w.com"]


def test_scan_engagement_without_optional_files(workspace):
    d = workspace / "engagements" / "bare.com"
    d.mkdir(parents=True)
    (d / "engagement.json").write_text("{}", encoding="utf-8")
    engs = eb.discover_engagements()
    assert len(engs) == 1
    eng = engs[0]
    assert eb.engagement_state(eng) == "init_only"
    assert eb.engagement_last_activity(eng) is not None  # 目录 mtime 兜底
