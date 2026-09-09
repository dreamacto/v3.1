"""Regression tests for the app phase cursor routing (plan §7.4, batch B2/W17).

锁定方案 §7.4 已验证的四用例：
① 共址 wz+xcx 游标、缺 app 游标 → APP_PHASE_STATUS_MISSING 且不返回任何路径；
② for_write=True 只提议 phase_status.app.json；
③ app 游标在场 → 解析自身 stream，不读 wz；
④ stream 字段缺失时防御性默认 app。
另锁两条防御分支：stream 声明为外流值 → 拒绝；无 stream 且 phases 只见外流
独有名（误复制游标）→ 拒绝。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents" / "skills" / "app" / "scripts" / "phase_status_routing.py"

WZ_CURSOR = "phase_status.json"
XCX_CURSOR = "phase_status.miniapp.json"


def load_module():
    spec = importlib.util.spec_from_file_location("app_phase_status_routing_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_cursor(path: Path, phases: list[dict], *, stream: str | None = None) -> None:
    payload: dict = {"schema_version": "1.0", "phases": phases}
    if stream is not None:
        payload["stream"] = stream
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_colocated_wz_xcx(root: Path) -> None:
    write_cursor(root / WZ_CURSOR, [{"phase": "application_mapping", "status": "complete"}])
    write_cursor(
        root / XCX_CURSOR,
        [{"phase": "platform_login_exchange", "status": "pending"}],
        stream="miniapp_xcx",
    )


# ① 共址 wz+xcx 游标、缺 app 游标 → fail-closed，绝不回落 wz/xcx 游标。
def test_colocated_wz_xcx_without_app_cursor_fails_closed(tmp_path):
    mod = load_module()
    seed_colocated_wz_xcx(tmp_path)
    route = mod.resolve_phase_status(tmp_path)
    assert route.path is None
    assert route.stream is None
    assert "APP_PHASE_STATUS_MISSING" in route.error
    assert "phase_status.app.json" in route.error
    assert "wz" in route.error and "xcx" in route.error


# ② for_write=True 只提议 phase_status.app.json（共址 wz/xcx 游标在场也不读）。
def test_for_write_proposes_only_app_cursor(tmp_path):
    mod = load_module()
    seed_colocated_wz_xcx(tmp_path)
    route = mod.resolve_phase_status(tmp_path, for_write=True)
    assert route.path == tmp_path / mod.APP_PHASE_STATUS_FILENAME
    assert route.stream == mod.APP_STREAM
    assert route.error is None
    # 空目录同样只提议 app 游标，且不产生任何 wz/xcx 游标文件。
    empty = tmp_path / "empty-ws"
    empty.mkdir()
    route_empty = mod.resolve_phase_status(empty, for_write=True)
    assert route_empty.path == empty / mod.APP_PHASE_STATUS_FILENAME
    assert not (empty / WZ_CURSOR).exists()
    assert not (empty / XCX_CURSOR).exists()


# ③ app 游标在场 → 解析自身 stream，不读 wz。
def test_app_cursor_resolves_own_stream_without_reading_wz(tmp_path):
    mod = load_module()
    seed_colocated_wz_xcx(tmp_path)
    wz_before = (tmp_path / WZ_CURSOR).read_bytes()
    xcx_before = (tmp_path / XCX_CURSOR).read_bytes()
    write_cursor(
        tmp_path / mod.APP_PHASE_STATUS_FILENAME,
        [{"phase": "package_integrity_hardening_review", "status": "pending"}],
        stream=mod.APP_STREAM,
    )
    route = mod.resolve_phase_status(tmp_path)
    assert route.path == tmp_path / mod.APP_PHASE_STATUS_FILENAME
    assert route.stream == mod.APP_STREAM
    assert route.error is None
    # 读取过程中 wz/xcx 游标未被改动。
    assert (tmp_path / WZ_CURSOR).read_bytes() == wz_before
    assert (tmp_path / XCX_CURSOR).read_bytes() == xcx_before


# ④ stream 字段缺失时防御性默认 app。
def test_missing_stream_defaults_to_app(tmp_path):
    mod = load_module()
    write_cursor(
        tmp_path / mod.APP_PHASE_STATUS_FILENAME,
        [{"phase": "ipc_component_boundary", "status": "pending"}],
    )
    route = mod.resolve_phase_status(tmp_path)
    assert route.path == tmp_path / mod.APP_PHASE_STATUS_FILENAME
    assert route.stream == mod.APP_STREAM


# 防御：app 游标声明了外流 stream 值（误复制）→ 拒绝解析。
def test_foreign_stream_value_is_rejected(tmp_path):
    mod = load_module()
    write_cursor(
        tmp_path / mod.APP_PHASE_STATUS_FILENAME,
        [{"phase": "package_inventory", "status": "pending"}],
        stream="miniapp_xcx",
    )
    route = mod.resolve_phase_status(tmp_path)
    assert route.path is None
    assert "APP_PHASE_STATUS_STREAM_MISMATCH" in route.error


# 防御：无 stream 且 phases 只见 wz/xcx 独有名（整文件误复制）→ 拒绝解析。
def test_copied_foreign_cursor_without_stream_is_rejected(tmp_path):
    mod = load_module()
    write_cursor(
        tmp_path / mod.APP_PHASE_STATUS_FILENAME,
        [
            {"phase": "scope", "status": "complete"},
            {"phase": "application_mapping", "status": "pending"},
        ],
    )
    route = mod.resolve_phase_status(tmp_path)
    assert route.path is None
    assert "APP_PHASE_STATUS_INVALID" in route.error


def test_route_metadata_shape(tmp_path):
    mod = load_module()
    write_cursor(
        tmp_path / mod.APP_PHASE_STATUS_FILENAME,
        [{"phase": "cleanup", "status": "pending"}],
        stream=mod.APP_STREAM,
    )
    route = mod.resolve_phase_status(tmp_path)
    metadata = mod.route_metadata(route)
    assert metadata == {
        "phase_status_file": mod.APP_PHASE_STATUS_FILENAME,
        "stream": mod.APP_STREAM,
        "error": None,
    }
    missing = mod.resolve_phase_status(tmp_path / "nowhere")
    assert mod.route_metadata(missing)["phase_status_file"] is None
    assert mod.route_metadata(missing)["error"] == missing.error
