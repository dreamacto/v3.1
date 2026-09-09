"""Regression tests for wz/xcx/app triple-stream cursor isolation (plan §3, batch B2/W17).

共址工作区（同一目录承载三流游标）下：每个流只解析/读写自己的游标文件，绝不
读写另外两流的游标。app 侧由 .agents/skills/app/scripts/phase_status_routing.py
与 init_app_engagement.py 保证；xcx 侧加载其 phase_status_routing 对照验证。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP_ROUTING = ROOT / ".agents" / "skills" / "app" / "scripts" / "phase_status_routing.py"
APP_INIT = ROOT / ".agents" / "skills" / "app" / "scripts" / "init_app_engagement.py"
XCX_ROUTING = ROOT / ".agents" / "skills" / "xcx" / "scripts" / "phase_status_routing.py"

WZ_CURSOR = "phase_status.json"
XCX_CURSOR = "phase_status.miniapp.json"
APP_CURSOR = "phase_status.app.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_cursor(path: Path, stream: str, phases: list[dict]) -> None:
    path.write_text(
        json.dumps({"schema_version": "1.0", "stream": stream, "phases": phases}, ensure_ascii=False),
        encoding="utf-8",
    )


def seed_colocated_workspace(root: Path) -> None:
    write_cursor(root / WZ_CURSOR, "wz", [{"phase": "application_mapping", "status": "complete"}])
    write_cursor(root / XCX_CURSOR, "miniapp_xcx", [{"phase": "package_inventory", "status": "pending"}])
    write_cursor(root / APP_CURSOR, "app", [{"phase": "ipc_component_boundary", "status": "pending"}])


def test_app_resolver_reads_only_app_cursor_in_colocated_workspace(tmp_path):
    app_mod = load_module("tsi_app_routing", APP_ROUTING)
    seed_colocated_workspace(tmp_path)
    route = app_mod.resolve_phase_status(tmp_path)
    assert route.path == tmp_path / APP_CURSOR
    assert route.stream == app_mod.APP_STREAM == "app"
    assert route.error is None


def test_xcx_resolver_still_reads_xcx_cursor_when_app_cursor_present(tmp_path):
    xcx_mod = load_module("tsi_xcx_routing", XCX_ROUTING)
    seed_colocated_workspace(tmp_path)
    route = xcx_mod.resolve_phase_status(tmp_path)
    assert route.path == tmp_path / XCX_CURSOR
    assert route.stream == xcx_mod.MINIAPP_STREAM
    assert route.path != tmp_path / APP_CURSOR


def test_app_missing_cursor_in_colocated_workspace_never_falls_back(tmp_path):
    app_mod = load_module("tsi_app_routing_missing", APP_ROUTING)
    write_cursor(tmp_path / WZ_CURSOR, "wz", [{"phase": "scope", "status": "complete"}])
    write_cursor(tmp_path / XCX_CURSOR, "miniapp_xcx", [{"phase": "identity", "status": "pending"}])
    route = app_mod.resolve_phase_status(tmp_path)
    assert route.path is None
    assert route.stream is None
    assert "APP_PHASE_STATUS_MISSING" in route.error


def test_app_for_write_in_colocated_workspace_proposes_only_app_cursor(tmp_path):
    app_mod = load_module("tsi_app_routing_write", APP_ROUTING)
    write_cursor(tmp_path / WZ_CURSOR, "wz", [{"phase": "scope", "status": "complete"}])
    write_cursor(tmp_path / XCX_CURSOR, "miniapp_xcx", [{"phase": "identity", "status": "pending"}])
    route = app_mod.resolve_phase_status(tmp_path, for_write=True)
    assert route.path == tmp_path / APP_CURSOR
    assert not (tmp_path / APP_CURSOR).exists()  # 只提议，不落盘
    # 写路径也不得指向另外两流。
    assert route.path.name not in {WZ_CURSOR, XCX_CURSOR}


def test_app_init_resume_leaves_foreign_cursors_untouched(tmp_path):
    init_mod = load_module("tsi_app_init", APP_INIT)
    root = tmp_path / "engagement"
    old_argv = sys.argv
    sys.argv = [str(APP_INIT), "com.example.smoke", "--output", str(root), "--platform", "android"]
    try:
        assert init_mod.main() == 0
    finally:
        sys.argv = old_argv

    # 共址：wz/xcx 会话把各自游标放进同一工作区。
    write_cursor(root / WZ_CURSOR, "wz", [{"phase": "fingerprint", "status": "complete"}])
    write_cursor(root / XCX_CURSOR, "miniapp_xcx", [{"phase": "webview_bridge_links", "status": "pending"}])
    wz_before = (root / WZ_CURSOR).read_bytes()
    xcx_before = (root / XCX_CURSOR).read_bytes()
    app_before = (root / APP_CURSOR).read_bytes()

    old_argv = sys.argv
    sys.argv = [str(APP_INIT), "com.example.smoke", "--output", str(root), "--resume"]
    try:
        assert init_mod.main() == 0
    finally:
        sys.argv = old_argv

    assert (root / WZ_CURSOR).read_bytes() == wz_before
    assert (root / XCX_CURSOR).read_bytes() == xcx_before
    # app 游标未被 resume 重置（种子的 authorization complete 等仍在）。
    app_after = json.loads((root / APP_CURSOR).read_text(encoding="utf-8-sig"))
    assert app_after["stream"] == "app"
    assert [row["phase"] for row in app_after["phases"]][0] == "authorization"
    assert app_after["phases"][0]["status"] == "complete"


def test_app_init_refuses_colocated_directory_without_resume(tmp_path):
    init_mod = load_module("tsi_app_init_refuse", APP_INIT)
    root = tmp_path / "engagement"
    root.mkdir()
    write_cursor(root / WZ_CURSOR, "wz", [{"phase": "scope", "status": "complete"}])
    old_argv = sys.argv
    sys.argv = [str(APP_INIT), "com.example.smoke", "--output", str(root)]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 3
    # 未 resume 的失败路径同样不得写任何文件。
    assert (root / WZ_CURSOR).read_bytes()
    assert not (root / APP_CURSOR).exists()
    assert not (root / "engagement.json").exists()
