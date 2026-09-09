"""tests/test_app_static_engine.py —— APP 流 B5 静态引擎离线测试
（施工方案 §5.3/§7.1，批次 B5/W19 中段）。

覆盖：临时目录假 AndroidManifest/资源文件的 manifest 深解析与 IPC/deeplink 候选行
生成、secrets/SDK/API 模式提取（匹配值绝不入输出）、apktool/jadx 子进程封装
（mock 子进程：成功核验入口文件 / 非零退出 / 超时 → decoding-ledger 记账、stderr
落 logs/、输出截断）、工具路径 registry fail-closed（active+tools/managed/app 白名单
+config 交叉核对）、whitebox --scan 薄包装、离线性 AST 锁（无网络 import、无硬编码
绝对路径、docstring 含"只观察不绕过"）。

纯离线：子进程全部 mock，不执行任何真实工具、不发任何网络请求。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorized_assessment.app import static_extraction as sex  # noqa: E402

APP_PACKAGE_DIR = SRC / "authorized_assessment" / "app"

FAKE_MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.demo.app">
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.READ_PHONE_STATE"/>
    <permission android:name="com.demo.CUSTOM" android:protectionLevel="dangerous"/>
    <application android:allowBackup="true" android:debuggable="true"
        android:networkSecurityConfig="@xml/nsc" android:usesCleartextTraffic="true">
        <activity android:name="com.demo.app.MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
        <activity android:name="com.demo.app.LinkActivity">
            <intent-filter>
                <action android:name="android.intent.action.VIEW"/>
                <category android:name="android.intent.category.BROWSABLE"/>
                <data android:scheme="demoapp" android:host="item" android:pathPrefix="/p"/>
            </intent-filter>
        </activity>
        <service android:name="com.demo.app.SyncService" android:exported="false"/>
        <provider android:name="com.demo.app.DataProvider" android:exported="true"
            android:permission="com.demo.READ_DATA" android:authorities="com.demo.provider"/>
        <receiver android:name="com.demo.app.PushReceiver">
            <intent-filter>
                <action android:name="com.demo.PUSH"/>
            </intent-filter>
        </receiver>
    </application>
</manifest>
"""


# ---------------------------------------------------------------------------
# AndroidManifest 深解析
# ---------------------------------------------------------------------------

def test_parse_android_manifest_deep_fields(tmp_path):
    manifest_path = tmp_path / "AndroidManifest.xml"
    manifest_path.write_text(FAKE_MANIFEST, encoding="utf-8")
    parsed = sex.parse_android_manifest(manifest_path)
    assert parsed["package"] == "com.demo.app"
    assert "android.permission.INTERNET" in parsed["permissions"]
    assert "android.permission.READ_PHONE_STATE" in parsed["permissions"]
    assert parsed["custom_permissions"] == [
        {"name": "com.demo.CUSTOM", "protection_level": "dangerous"}
    ]
    assert parsed["application"]["allowBackup"] == "true"
    assert parsed["application"]["debuggable"] == "true"
    assert parsed["application"]["networkSecurityConfig"] == "@xml/nsc"
    assert parsed["application"]["usesCleartextTraffic"] == "true"
    by_name = {component["name"]: component for component in parsed["components"]}
    assert by_name["com.demo.app.MainActivity"]["exported"] == "true"
    assert by_name["com.demo.app.SyncService"]["exported"] == "false"
    assert by_name["com.demo.app.LinkActivity"]["exported"] == ""
    link = by_name["com.demo.app.LinkActivity"]
    assert link["intent_filters"][0]["actions"] == ["android.intent.action.VIEW"]
    assert link["intent_filters"][0]["data"] == [
        {"scheme": "demoapp", "host": "item", "pathPrefix": "/p"}
    ]


def test_manifest_ipc_component_and_deeplink_rows(tmp_path):
    manifest_path = tmp_path / "AndroidManifest.xml"
    manifest_path.write_text(FAKE_MANIFEST, encoding="utf-8")
    parsed = sex.parse_android_manifest(manifest_path)
    rows = sex.manifest_ipc_component_rows(parsed)
    by_name = {row["component_name"]: row for row in rows}
    exported_activity = by_name["com.demo.app.MainActivity"]
    assert exported_activity["component_kind"] == "activity"
    assert exported_activity["exported"] == "true"
    assert exported_activity["intent_actions"].startswith("android.intent.action.MAIN")
    link_activity = by_name["com.demo.app.LinkActivity"]
    assert link_activity["exported"] == "unknown"
    assert "implicit_export_candidate" in link_activity["notes"]
    assert link_activity["scheme"] == "demoapp"
    assert link_activity["authority"] == "item"
    provider = by_name["com.demo.app.DataProvider"]
    assert provider["component_kind"] == "provider"
    assert provider["permission"] == "com.demo.READ_DATA"
    assert provider["exported"] == "true"
    deeplinks = sex.manifest_deeplink_rows(parsed)
    patterns = [row["deep_link_pattern"] for row in deeplinks]
    assert "demoapp://item/p" in patterns
    link_row = next(row for row in deeplinks if row["scheme_type"] == "custom_scheme")
    assert link_row["component_ref"] == "com.demo.app.LinkActivity"
    assert link_row["jump_target"] == "in_app"


# ---------------------------------------------------------------------------
# secrets / SDK / API 模式提取（值不进输出）
# ---------------------------------------------------------------------------

def test_scan_source_tree_secret_sdk_api_hits(tmp_path):
    source = tmp_path / "unpacked" / "com.demo.app"
    (source / "com" / "demo").mkdir(parents=True)
    (source / "com" / "demo" / "Config.java").write_text(
        "\n".join(
            [
                "package com.demo;",
                "import com.umeng.analytics.MobclickAgent;",
                "public class Config {",
                '    public static final String APP_SECRET = "s3cretValue987654";',
                '    public static final String OSS_KEY = "LTAI4GExampleKey0000aa";',
                "    public static final String PRIVATE = \"-----BEGIN RSA PRIVATE KEY-----\";",
                '    public static final String API = "https://api.demo.com/v1/user?token=abc";',
                '    public static final String PATH = "/api/user/profile";',
                "}",
            ]
        ),
        encoding="utf-8",
    )
    result = sex.scan_source_tree(tmp_path / "unpacked")
    pattern_ids = {hit["pattern_id"] for hit in result["secret_hits"]}
    assert {"appsecret_assignment", "aliyun_access_key_id", "private_key_header"} <= pattern_ids
    # 红线：匹配值本身绝不进返回值（secret_candidate 只是线索，值不外泄）。
    dumped = json.dumps(result, ensure_ascii=False)
    assert "s3cretValue987654" not in dumped
    assert "LTAI4GExampleKey0000aa" not in dumped
    for hit in result["secret_hits"]:
        assert set(hit) == {"pattern_id", "file", "line"}
        assert hit["file"].endswith("Config.java")
        assert hit["line"] >= 1
    assert "umeng" in result["sdks_detected"]
    assert any(sdk["sdk"] == "umeng" for sdk in result["sdk_markers"])
    api_values = [hit["value"] for hit in result["api_hits"]]
    assert "https://api.demo.com/v1/user" in api_values  # query 剥离
    assert "/api/user/profile" in api_values
    assert not any("token=abc" in value for value in api_values)


def test_scan_source_tree_skips_binary_and_oversize(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\x00\x01LTAIABCDEFGHijklmn\x00")
    oversize = tmp_path / "big.java"
    oversize.write_text("// LTAIABCDEFGHijklmn\n" * 200000, encoding="utf-8")
    result = sex.scan_source_tree(tmp_path)
    assert result["secret_hits"] == []


# ---------------------------------------------------------------------------
# 子进程封装（mock）：成功核验 / 失败 / 超时 → decoding-ledger
# ---------------------------------------------------------------------------

class MockRunner:
    """mock subprocess.run：按命令参数创建假产物文件，可注入退出码/stderr/超时。"""

    def __init__(self, layout="apktool", returncode=0, stdout="ok line", stderr="",
                 raise_timeout=False):
        self.layout = layout
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.raise_timeout = raise_timeout
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), dict(kwargs)))
        if self.raise_timeout:
            raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout"))
        out_dir = None
        for index, token in enumerate(command):
            if token in ("-o", "-d") and index + 1 < len(command):
                out_dir = Path(command[index + 1])
        if out_dir is not None and self.returncode == 0:
            out_dir.mkdir(parents=True, exist_ok=True)
            if self.layout == "apktool":
                (out_dir / "AndroidManifest.xml").write_text(FAKE_MANIFEST, encoding="utf-8")
                (out_dir / "apktool.yml").write_text("apkVersion: 3.0.3\n", encoding="utf-8")
            elif self.layout == "jadx":
                java = out_dir / "sources" / "com" / "demo"
                java.mkdir(parents=True, exist_ok=True)
                (java / "Main.java").write_text("package com.demo;\n", encoding="utf-8")
        return subprocess.CompletedProcess(
            command, self.returncode, stdout=self.stdout, stderr=self.stderr
        )


def _fake_apk(tmp_path: Path) -> Path:
    apk = tmp_path / "demo.apk"
    apk.write_bytes(b"PK\x03\x04fake-package-bytes")
    return apk


def _read_ledger(workspace: Path) -> list[dict]:
    import csv

    with (workspace / sex.DECODING_LEDGER_CSV).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def test_run_apktool_success_records_ok_ledger(tmp_path):
    apk = _fake_apk(tmp_path)
    workspace = tmp_path / "ws"
    runner = MockRunner(layout="apktool")
    result = sex.run_apktool(apk, workspace, "com.demo.app", material_id="MAT-0001", runner=runner)
    assert result.status == "ok"
    assert result.reason == ""
    assert result.exit_code == 0
    # 命令形态锁定（方案 §7.1）：java -jar <jar> d -f -o <out> <apk>。
    command = runner.calls[0][0]
    assert command[0] == "java" and command[1] == "-jar"
    assert command[3:6] == ["d", "-f", "-o"]
    assert command[-1] == str(apk)
    jar = Path(command[2])
    assert jar.is_absolute() and "tools" in jar.parts and "managed" in jar.parts and "app" in jar.parts
    # 子进程纪律：超时默认 600s。
    assert runner.calls[0][1]["timeout"] == 600
    ledger = _read_ledger(workspace)
    assert len(ledger) == 1
    assert ledger[0]["status"] == sex.LEDGER_STATUS_OK
    assert ledger[0]["tool"] == "apktool"
    assert ledger[0]["tool_version"] == "3.0.3"
    assert ledger[0]["material_id"] == "MAT-0001"
    assert ledger[0]["decoding_id"] == "DEC-0001"
    assert ledger[0]["recovered_clues"].startswith("AndroidManifest.xml")


def test_run_apktool_failure_writes_failed_ledger_and_stderr_log(tmp_path):
    apk = _fake_apk(tmp_path)
    workspace = tmp_path / "ws"
    runner = MockRunner(layout="apktool", returncode=1, stderr="boom: bad dex")
    result = sex.run_apktool(apk, workspace, "com.demo.app", runner=runner)
    assert result.status == "failed"
    assert result.reason == "non-zero exit 1"
    ledger = _read_ledger(workspace)
    assert ledger[0]["status"] == sex.LEDGER_STATUS_FAILED
    assert "exit_code=1" in ledger[0]["notes"]
    assert "reason=non-zero exit 1" in ledger[0]["notes"]
    # stderr 完整落 <ws>/logs/apktool-*.log。
    logs = list((workspace / "logs").glob("apktool-*.log"))
    assert len(logs) == 1
    assert "boom: bad dex" in logs[0].read_text(encoding="utf-8")


def test_run_decode_timeout_records_ledger_without_exit_code(tmp_path):
    apk = _fake_apk(tmp_path)
    workspace = tmp_path / "ws"
    runner = MockRunner(layout="apktool", raise_timeout=True)
    result = sex.run_apktool(apk, workspace, "com.demo.app", runner=runner)
    assert result.status == "failed"
    assert result.reason == "timeout after 600s"
    assert result.exit_code is None
    ledger = _read_ledger(workspace)
    assert ledger[0]["status"] == sex.LEDGER_STATUS_FAILED
    assert "timeout after 600s" in ledger[0]["notes"]
    assert "exit_code" not in ledger[0]["notes"]


def test_run_jadx_success_and_entry_file_check(tmp_path):
    apk = _fake_apk(tmp_path)
    workspace = tmp_path / "ws"
    # 退出码 0 但未产出 sources/*.java → 成功核验失败，记 failed（不静默）。
    broken_runner = MockRunner(layout="none", returncode=0)
    result = sex.run_jadx(apk, workspace, "com.demo.app", runner=broken_runner)
    assert result.status == "failed"
    assert "entry-file check failed" in result.reason
    ledger = _read_ledger(workspace)
    assert ledger[0]["status"] == sex.LEDGER_STATUS_FAILED
    # 正常成功：sources 树存在 → ok；命令形态锁定（方案 §7.1 反编译参数）。
    workspace2 = tmp_path / "ws2"
    runner = MockRunner(layout="jadx")
    result2 = sex.run_jadx(apk, workspace2, "com.demo.app", runner=runner)
    assert result2.status == "ok"
    command = runner.calls[0][0]
    assert command[1] == "-d"
    assert command[2].endswith("com.demo.app")
    assert command[command.index("--deobf-min") + 1] == "3"
    assert command[command.index("--deobf-max") + 1] == "9"
    assert "--scan" not in command


def test_ledger_notes_truncated_and_id_increments(tmp_path):
    workspace = tmp_path / "ws"
    long_error = "E: " + "x" * 5000
    runner = MockRunner(layout="apktool", returncode=2, stderr=long_error)
    apk = _fake_apk(tmp_path)
    sex.run_apktool(apk, workspace, "com.demo.app", runner=runner)
    sex.run_apktool(apk, workspace, "com.demo.app", runner=runner)
    ledger = _read_ledger(workspace)
    assert [row["decoding_id"] for row in ledger] == ["DEC-0001", "DEC-0002"]
    for row in ledger:
        assert len(row["notes"]) <= sex.MAX_LEDGER_NOTES_CHARS + 20  # 截断标记余量
        assert row["notes"].endswith("…[truncated]") or len(row["notes"]) <= sex.MAX_LEDGER_NOTES_CHARS


def test_capture_excerpt_output_cap():
    many_lines = "\n".join(f"line-{i}" for i in range(sex.MAX_CAPTURE_LINES + 50))
    excerpt = sex._capture_excerpt(many_lines)
    assert excerpt.count("\n") <= sex.MAX_CAPTURE_LINES
    assert "truncated" in excerpt
    big = "x" * (sex.MAX_CAPTURE_CHARS + 1000)
    assert len(sex._capture_excerpt(big)) <= sex.MAX_CAPTURE_CHARS + 60


# ---------------------------------------------------------------------------
# 工具解析：registry active + tools/managed/app 白名单 + config 交叉核对
# ---------------------------------------------------------------------------

def test_resolve_managed_tool_real_repo():
    for tool_id, suffix in (("apktool", "apktool_3.0.3.jar"), ("jadx", "jadx.bat")):
        resolved, entry = sex.resolve_managed_tool(tool_id)
        assert entry["status"] == "active"
        parts = Path(resolved).parts
        assert "tools" in parts and "managed" in parts and "app" in parts
        assert resolved.name == suffix


def _write_fake_registry_root(tmp_path: Path, *, status="active", rel_path=None, include_config=True, config_entries=None):
    rel = rel_path or "tools/managed/app/fake/1.0/fake.exe"
    tool_file = tmp_path / Path(rel)
    tool_file.parent.mkdir(parents=True, exist_ok=True)
    tool_file.write_bytes(b"fake")
    registry = {
        "schema_version": "1.0",
        "tools": [
            {
                "tool_id": "apktool",
                "display_name": "Fake",
                "path": rel,
                "version": "1.0",
                "status": status,
                "runtime": "native",
                "dependencies": [],
                "known_limitations": "test",
            }
        ],
    }
    (tmp_path / "tools" / "tool_registry.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "tool_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    if include_config:
        entries = config_entries if config_entries is not None else [f"{{base}}/{rel}"]
        config = {"tools": {"apktool": entries}}
        (tmp_path / "gov_exercise_config.json").write_text(json.dumps(config), encoding="utf-8")


def test_resolve_managed_tool_fail_closed(tmp_path):
    # 非 active（unavailable，如审批门工具）→ 拒绝。
    _write_fake_registry_root(tmp_path, status="unavailable")
    with pytest.raises(sex.ToolResolutionError, match="unavailable"):
        sex.resolve_managed_tool("apktool", root=tmp_path)
    # 路径越界（tools/managed/app 之外）→ 拒绝。
    tmp2 = tmp_path / "case2"
    _write_fake_registry_root(tmp2, rel_path="tools/managed/web/evil/evil.exe")
    with pytest.raises(sex.ToolResolutionError, match="outside"):
        sex.resolve_managed_tool("apktool", root=tmp2)
    # config 白名单不一致 → 拒绝。
    tmp3 = tmp_path / "case3"
    _write_fake_registry_root(
        tmp3,
        rel_path="tools/managed/app/fake/1.0/fake.exe",
        config_entries=["{base}/tools/managed/app/other/thing.exe"],
    )
    with pytest.raises(sex.ToolResolutionError, match="whitelist mismatch"):
        sex.resolve_managed_tool("apktool", root=tmp3)
    # 未登记的 tool_id → 拒绝。
    with pytest.raises(sex.ToolResolutionError, match="not registered"):
        sex.resolve_managed_tool("frida", root=tmp_path / "case3")
    # 合成正例：active + 白名单内 + 磁盘存在。
    tmp4 = tmp_path / "case4"
    _write_fake_registry_root(tmp4)
    resolved, entry = sex.resolve_managed_tool("apktool", root=tmp4)
    assert entry["status"] == "active"
    assert resolved.is_file()


def test_resolve_managed_tool_missing_registry(tmp_path):
    with pytest.raises(sex.ToolResolutionError, match="missing registry"):
        sex.resolve_managed_tool("apktool", root=tmp_path)


def test_no_hardcoded_absolute_tool_paths():
    source = (APP_PACKAGE_DIR / "static_extraction.py").read_text(encoding="utf-8")
    import re

    assert not re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", source), "static_extraction 不得硬编码盘符绝对路径"
    assert "/Users/" not in source and "/home/" not in source


# ---------------------------------------------------------------------------
# whitebox --scan 薄包装
# ---------------------------------------------------------------------------

def test_whitebox_scan_command_shape(tmp_path):
    command, script = sex.whitebox_scan_command(
        tmp_path / "unpacked" / "demo", tmp_path / "out"
    )
    assert script == ROOT / "whitebox_triage.py"
    assert command[-1] == "--scan"
    assert "--source-dir" in command and "--out-dir" in command


def test_run_whitebox_scan_mocked(tmp_path):
    runner = MockRunner(layout="none")
    result = sex.run_whitebox_scan(
        tmp_path / "unpacked", tmp_path / "out", runner=runner
    )
    assert result["status"] == "ok"
    assert runner.calls[0][0][-1] == "--scan"
    missing = sex.run_whitebox_scan(
        tmp_path / "unpacked", tmp_path / "out", root=tmp_path
    )
    assert missing["status"] == "failed"
    assert "missing" in missing["reason"]
    timed_out = sex.run_whitebox_scan(
        tmp_path / "unpacked", tmp_path / "out", runner=MockRunner(layout="none", raise_timeout=True)
    )
    assert timed_out["status"] == "failed"
    assert "timeout" in timed_out["reason"]


# ---------------------------------------------------------------------------
# 离线性与红线锚点（AST/源码结构锁）
# ---------------------------------------------------------------------------

_NETWORK_MODULES = {"socket", "http", "http.client", "requests", "urllib", "urllib.request", "aiohttp", "httpx"}


def test_app_b5_modules_have_no_network_imports():
    for module_name in ("app_review_common", "hardening_integrity_review", "static_extraction", "webview_bridge_review", "ipc_component_review"):
        tree = ast.parse((APP_PACKAGE_DIR / f"{module_name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in _NETWORK_MODULES, f"{module_name}: 禁止网络 import {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in _NETWORK_MODULES, f"{module_name}: 禁止网络 import from {node.module}"


def test_subprocess_only_in_static_extraction():
    for module_name in ("app_review_common", "hardening_integrity_review", "webview_bridge_review", "ipc_component_review"):
        source = (APP_PACKAGE_DIR / f"{module_name}.py").read_text(encoding="utf-8")
        assert "subprocess" not in source, f"{module_name} 不应使用子进程"


def test_observe_only_docstring_anchors():
    for module_name in ("hardening_integrity_review", "static_extraction"):
        source = (APP_PACKAGE_DIR / f"{module_name}.py").read_text(encoding="utf-8")
        assert "只观察不绕过" in source, f"{module_name} docstring 必须含只观察不绕过红线"
    hardening_source = (APP_PACKAGE_DIR / "hardening_integrity_review.py").read_text(encoding="utf-8")
    assert "APP_NO_REPACKING_RULE" in hardening_source
    static_source = (APP_PACKAGE_DIR / "static_extraction.py").read_text(encoding="utf-8")
    assert "600" in static_source and "decoding-ledger" in static_source
