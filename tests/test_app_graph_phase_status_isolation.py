"""APP graph cursor-isolation tests (batch B9/W21; mirrors and hardens
tests/test_xcx_graph_phase_status_isolation.py).

工单硬性要求：证明 app graph 在共址工作区绝不读写 wz/xcx 游标。四层证据：
① 全节点只绑 phase_status.app.json，序列化产物无任何 wz/xcx/run_status 游标字样；
② 篡改节点游标为 wz/xcx 游标 → fail-closed 拒绝；
③ 共址工作区实盘证明：同目录放三流游标，app graph 全生命周期（构建/校验/往返/
   序列化）前后 wz/xcx 游标字节级不变；
④ 源码级零 I/O 断言：app_graph 模块不含任何文件读写或网络调用路径；
⑤ 三流共存：共享基座登记 app 后，wz/xcx 图在同一进程仍各自校验通过（无回归）。
"""
from __future__ import annotations

import hashlib
import inspect
import json

from authorized_assessment.orchestration.app_graph import (
    APP_CURSOR_FILE,
    build_app_graph,
    validate_app_graph,
)
from authorized_assessment.orchestration.wz_graph import build_wz_specialized_graph, validate_wz_graph
from authorized_assessment.orchestration.xcx_graph import build_xcx_graph, validate_xcx_graph

FORBIDDEN_CURSORS = ("phase_status.json", "phase_status.miniapp.json", "run_status.json")


def test_every_app_node_is_bound_to_app_cursor_only():
    graph = build_app_graph(created_at="fixed")
    assert all(node.cursor_file == APP_CURSOR_FILE for node in graph.nodes)
    planning = str(graph.to_planning_dict())
    assert "phase_status.json" not in planning.replace(APP_CURSOR_FILE, "")
    assert "phase_status.miniapp.json" not in planning
    assert "run_status.json" not in planning


def test_cross_stream_node_and_metadata_are_rejected():
    for foreign in ("phase_status.json", "phase_status.miniapp.json", "run_status.json"):
        graph = build_app_graph(created_at="fixed").to_dict()
        graph["nodes"][0]["cursor_file"] = foreign
        assert any("cursor" in error.lower() or "APP" in error for error in validate_app_graph(graph)), foreign


def test_invalid_graph_type_and_missing_nodes_fail_closed():
    assert validate_app_graph(None)
    assert validate_app_graph({"workflow": "app", "nodes": []})


def test_co_located_workspace_cursors_are_never_touched(tmp_path):
    # 共址工作区：三流游标同目录在场（内容含各流阶段名，任何误读写都会改变字节）。
    wz_cursor = tmp_path / "phase_status.json"
    xcx_cursor = tmp_path / "phase_status.miniapp.json"
    app_cursor = tmp_path / "phase_status.app.json"
    wz_cursor.write_text(json.dumps({"stream": "wz", "current_phase": "fingerprint"}), encoding="utf-8")
    xcx_cursor.write_text(json.dumps({"stream": "miniapp_xcx", "current_phase": "static_analysis"}), encoding="utf-8")
    app_cursor.write_text(json.dumps({"stream": "app", "current_phase": "preflight"}), encoding="utf-8")

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    before = {path.name: digest(path) for path in (wz_cursor, xcx_cursor, app_cursor)}

    # app graph 全生命周期都在共址目录之上执行；graph 是纯编排声明，不触任何游标文件。
    from authorized_assessment.orchestration.app_graph import graph_from_dict

    graph = build_app_graph(created_at="fixed")
    assert validate_app_graph(graph) == []
    restored = graph_from_dict(graph.to_dict())
    assert validate_app_graph(restored) == []
    assert json.dumps(restored.to_planning_dict(), ensure_ascii=False)
    assert str(tmp_path.resolve()) not in str(graph.to_dict())

    after = {path.name: digest(path) for path in (wz_cursor, xcx_cursor, app_cursor)}
    assert before == after  # wz/xcx（连同 app）游标字节级不变：绝不读写。


def test_app_graph_module_has_no_io_code_paths():
    source = inspect.getsource(__import__("authorized_assessment.orchestration.app_graph", fromlist=["__doc__"]))
    for marker in (
        "open(",
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "os.remove",
        "os.rename",
        "requests",
        "urllib",
        "socket",
        "http.client",
        "subprocess",
    ):
        assert marker not in source, marker


def test_wz_and_xcx_graphs_still_validate_after_app_registration():
    wz = build_wz_specialized_graph(created_at="fixed")
    assert validate_wz_graph(wz) == []
    xcx = build_xcx_graph(created_at="fixed")
    assert validate_xcx_graph(xcx) == []
    app = build_app_graph(created_at="fixed")
    assert validate_app_graph(app) == []
    # 三流互不串游标：wz 图无 miniapp/app 游标，xcx 图无 wz/app 游标，app 图只有 app 游标。
    assert "phase_status.miniapp.json" not in str(wz.to_planning_dict())
    assert "phase_status.app.json" not in str(wz.to_planning_dict())
    assert "phase_status.app.json" not in str(xcx.to_planning_dict())
    assert {node.cursor_file for node in app.nodes} == {APP_CURSOR_FILE}
