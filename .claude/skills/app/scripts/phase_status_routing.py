"""Route app phase state away from co-located wz/xcx phase cursors."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

APP_PHASE_STATUS_FILENAME = "phase_status.app.json"
APP_STREAM = "app"

# app 游标的独有阶段名集合（方案 §7.4）。APP 无 xcx 的 legacy 单流回退，本集合只用于
# 一个防御性判定：stream 字段缺失时，若 phases 里只见 wz/xcx 独有名而没有任何 app
# 独有名，说明该文件是被误复制的外流游标，拒绝解析而不是默认当作 app。
_APP_PHASE_HINTS = {
    "package_integrity_hardening_review",
    "ipc_component_boundary",
    "third_party_sdk_platform_boundary",
    "dynamic_setup",
    "material_acquisition",
    "package_unpack_decompile",
}
_FOREIGN_STREAM_HINTS = {
    # wz 独有
    "scope",
    "subdomain_enumeration",
    "alive_probe",
    "fingerprint",
    "application_mapping",
    "unauthenticated_testing",
    "authenticated_testing",
    "known_vuln_triage",
    "content_discovery",
    # xcx 独有（含历史行名）
    "authentication_session",
    "client_storage_crypto",
    "package_integrity_update_review",
    "plugins_cloud_third_party",
    "third_party_platform_boundary",
}


@dataclass(frozen=True)
class PhaseStatusRoute:
    path: Path | None
    stream: str | None
    error: str | None = None


def _payload(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _phase_names(payload: dict[str, Any]) -> set[str]:
    phases = payload.get("phases")
    if not isinstance(phases, list):
        return set()
    return {
        str(row.get("phase", "")).strip()
        for row in phases
        if isinstance(row, dict)
    }


def _looks_like_foreign_cursor(payload: dict[str, Any]) -> bool:
    """stream 缺失时判断游标是否明显属于 wz/xcx（误复制），只做防御不回退。"""
    names = _phase_names(payload)
    if not names:
        return False
    return bool(names & _FOREIGN_STREAM_HINTS) and not (names & _APP_PHASE_HINTS)


def resolve_phase_status(root: Path, *, for_write: bool = False) -> PhaseStatusRoute:
    """Resolve the app cursor without ever falling back to a wz/xcx cursor."""
    root = Path(root)
    app_path = root / APP_PHASE_STATUS_FILENAME
    if app_path.is_file():
        payload = _payload(app_path)
        stream = str(payload.get("stream") or "").strip()
        if stream and stream != APP_STREAM:
            return PhaseStatusRoute(
                None,
                None,
                "APP_PHASE_STATUS_STREAM_MISMATCH: "
                f"{APP_PHASE_STATUS_FILENAME} declares stream={stream!r}; expected {APP_STREAM!r}",
            )
        if not stream and _looks_like_foreign_cursor(payload):
            return PhaseStatusRoute(
                None,
                None,
                "APP_PHASE_STATUS_INVALID: "
                f"{APP_PHASE_STATUS_FILENAME} carries wz/xcx phase names and no stream field; "
                "a copied foreign cursor will not be used as the app cursor",
            )
        return PhaseStatusRoute(app_path, APP_STREAM)
    if for_write:
        return PhaseStatusRoute(app_path, APP_STREAM)
    return PhaseStatusRoute(
        None,
        None,
        "APP_PHASE_STATUS_MISSING: phase_status.app.json is required; "
        "phase_status.json (wz) and phase_status.miniapp.json (xcx) belong to other "
        "streams and will not be used",
    )


def route_metadata(route: PhaseStatusRoute) -> dict[str, Any]:
    return {
        "phase_status_file": route.path.name if route.path else None,
        "stream": route.stream,
        "error": route.error,
    }
