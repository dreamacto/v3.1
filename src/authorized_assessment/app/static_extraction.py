"""APP 静态提取编排（施工方案 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §5.3 + §7.1，
批次 B5/W19 中段；操作手册 .agents/skills/app/references/package-analysis.md §2-§6）。

只观察不绕过（红线）：本模块只解码操作员提供的本地包副本（registry active 的
apktool/jadx 管理内工具）；任何脱壳、反调试 patch、SSL pinning bypass、frida 注入、
重打包 = device_instrumentation/app_hardened_unpack 审批门（双钥匙），本模块不提供
任何此类能力。壳包解包失败记 blocked（decoding-ledger failed 行），不自动脱壳
（FRIDA-DEXDump/BlackDex 等在 registry 保持 unavailable，操作者放置前不接入）。

子进程纪律（方案 §7.1 / package-analysis.md §2，逐条落实）：
- 超时：默认 600s/包（DEFAULT_TIMEOUT_SECONDS），超时即终止并按 failed 记账；
- 输出上限：返回值/账本 notes 只携带截断摘录（MAX_CAPTURE_LINES/MAX_CAPTURE_CHARS），
  完整 stderr 只落盘 `<ws>/logs/`（工具名+时间戳命名），原始输出不进对话；
- 失败写账：任何失败（退出码非 0、超时、预期入口文件缺失）追加
  `artifacts/decoding-ledger.csv` 一行（status=failed + 原因），成功尝试也记账
  （一行一次尝试），不静默；
- 成功核验：退出码 0 不是成功证明——apktool 核验 AndroidManifest.xml 与
  apktool.yml，jadx 核验 sources/ 下非空 .java 树（package-analysis.md §2 末条）。

工具路径纪律（不硬编码绝对路径）：仅接受 tools/tool_registry.json 中 status=active
且相对路径位于 tools/managed/app/ 之下的登记项，并与 gov_exercise_config.json
tools 白名单（{base} 模板）交叉核对；任一不符即拒绝执行（fail-closed）。

敏感值纪律：secrets 扫描只记录 pattern_id + file:line，不记录匹配值本身；
本模块不接触凭证文件，stderr/日志只含工具输出与路径。
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]

# 子进程纪律常量（方案 §7.1；J-B5 验收锚点）。
DEFAULT_TIMEOUT_SECONDS = 600
MAX_CAPTURE_LINES = 200
MAX_CAPTURE_CHARS = 4000
MAX_LEDGER_NOTES_CHARS = 300

# 工具纪律常量：仅允许 registry active 且位于本仓 tools/managed/app/ 下的管理内
# 路径（不硬编码绝对路径，从 registry/config 解析）。
APKTOOL_TOOL_ID = "apktool"
JADX_TOOL_ID = "jadx"
ALLOWED_MANAGED_TOOL_PREFIX = "tools/managed/app"

# decoding-ledger（app init 种子 DECODING_FIELDS 同源；tests/test_app_contract_sync
# 锁定）。错误摘要（退出码/原因/截断 stderr）并入 notes 列，满足 package-analysis
# §6 的"command/exit_code/error_summary 留痕"语义（命令由调用方输入可复现）。
DECODING_LEDGER_CSV = "artifacts/decoding-ledger.csv"
DECODING_LEDGER_FIELDS: tuple[str, ...] = (
    "decoding_id",
    "material_id",
    "input_type",
    "input_ref",
    "input_sha256",
    "tool",
    "tool_version",
    "mode",
    "status",
    "output_path",
    "recovered_clues",
    "notes",
)

LEDGER_STATUS_OK = "ok"
LEDGER_STATUS_FAILED = "failed"

# 白盒薄包装目标（仓库根 whitebox_triage.py，方案 §7.1 第三条命令）。
WHITEBOX_TRIAGE_SCRIPT = "whitebox_triage.py"

# secrets / SDK / API 路径模式（方案 §5.3 static_extraction 行 + package-analysis
# §9 索引）。secrets 只记 pattern_id + file:line，匹配值不进任何输出（契约红线：
# 发现密钥字符串但无法证明有效性时只能是 secret_candidate）。
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("private_key_header", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("aliyun_access_key_id", r"\bLTAI[0-9A-Za-z]{12,30}\b"),
    ("aws_access_key_id", r"\bAKIA[0-9A-Z]{16}\b"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("appsecret_assignment", r"(?i)\b(app[_-]?secret|appsecret)\b\s*[:=]\s*['\"][0-9A-Za-z]{8,}['\"]"),
    ("access_key_assignment", r"(?i)\b(access[_-]?key[_-]?(id)?|secret[_-]?key|ak|sk)\b\s*[:=]\s*['\"][0-9A-Za-z+/=]{12,}['\"]"),
    ("jpush_appkey", r"(?i)\b(jpush|jiguang)[_\-]?(app[_-]?key|master[_-]?secret)\b\s*[:=]\s*['\"][0-9A-Za-z]{16,}['\"]"),
    ("umeng_appkey", r"(?i)\bumeng\b.*\b(app[_-]?key|appkey)\b\s*[:=]\s*['\"][0-9A-Za-z]{10,}['\"]"),
    ("maps_api_key_assignment", r"(?i)\b(amap|baidu|tencent|google)[_\-]?maps?[_\-]?(api)?[_-]?key\b\s*[:=]\s*['\"][0-9A-Za-z_\-]{16,}['\"]"),
    ("token_assignment_literal", r"(?i)\b(api[_-]?token|auth[_-]?token|bearer)\b\s*[:=]\s*['\"][0-9A-Za-z._\-]{16,}['\"]"),
)
_SECRET_PATTERN_COMPILED = tuple(
    (pattern_id, re.compile(pattern)) for pattern_id, pattern in SECRET_PATTERNS
)

# 常见三方 SDK 包前缀（package-analysis §9 "第三方 SDK 与云能力"索引）。
SDK_MARKERS: tuple[tuple[str, str], ...] = (
    ("umeng", r"(?i)\bcom\.umeng\."),
    ("jpush", r"(?i)\bcn\.jpush\."),
    ("wechat_open_sdk", r"(?i)\bcom\.tencent\.mm\.opensdk\."),
    ("alipay", r"(?i)\bcom\.alipay\."),
    ("amap_maps", r"(?i)\bcom\.amap\.api\."),
    ("baidu_maps", r"(?i)\bcom\.baidu\.mapapi\."),
    ("tencent_maps", r"(?i)\bcom\.tencent\.map\."),
    ("bugly", r"(?i)\bcom\.tencent\.bugly\."),
    ("firebase", r"(?i)\bcom\.google\.firebase\."),
    ("sentry", r"(?i)\bio\.sentry\."),
    ("getui", r"(?i)\bcom\.igexin\."),
    ("aliyun_oss", r"(?i)\bcom\.aliyun\.oss\."),
)
_SDK_MARKER_COMPILED = tuple(
    (sdk_name, re.compile(marker)) for sdk_name, marker in SDK_MARKERS
)

# API/端点线索：URL 只保留 scheme+host+path（query 可能带 token，剥离不入输出）。
_API_URL_PATTERN = re.compile(r"https?://[A-Za-z0-9.\-]+(?::\d+)?(?:/[A-Za-z0-9._\-/%]*)?")
_API_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9])/(?:api|v\d|gateway|rest|app|h5|open)/[A-Za-z0-9._\-/]{1,120}")
_TEXT_SUFFIXES = {
    ".java", ".kt", ".xml", ".properties", ".json", ".smali", ".gradle", ".pro", ".txt", ".html", ".js",
}
_SCAN_MAX_FILE_BYTES = 2 * 1024 * 1024


def repo_root() -> Path:
    """本模块所属仓库根（工具/registry/whitebox_triage.py 解析基准）。"""
    return _REPO_ROOT


# ---------------------------------------------------------------------------
# 工具解析（registry active + tools/managed/app 白名单 + config 交叉核对）
# ---------------------------------------------------------------------------

class ToolResolutionError(RuntimeError):
    """工具解析失败（registry 缺失/非 active/越界路径/config 不一致）。fail-closed。"""


def resolve_managed_tool(
    tool_id: str,
    root: Path | None = None,
    registry_path: Path | None = None,
    config_path: Path | None = None,
) -> tuple[Path, dict]:
    """解析 apktool/jadx 执行路径：只接受 registry 中 status=active、相对路径位于
    tools/managed/app/ 之下的登记项，并与 gov_exercise_config.json tools 白名单
    （{base} 模板）交叉核对；磁盘不存在同样拒绝。返回 (绝对路径, registry 条目)。

    硬约束（B5）：不硬编码工具绝对路径——一切来自 registry/config 解析；
    审批门工具（frida/objection/FRIDA-DEXDump/BlackDex）在 registry 为
    unavailable，天然被本函数拒绝。
    """
    from authorized_assessment.tools import registry as tool_registry

    base = Path(root) if root is not None else repo_root()
    reg_path = Path(registry_path) if registry_path is not None else base / "tools" / "tool_registry.json"
    data, err = tool_registry.load_registry(reg_path)
    if err:
        raise ToolResolutionError(f"{tool_id}: {err}")
    entry = tool_registry.get_tool(data, tool_id)
    if entry is None:
        raise ToolResolutionError(f"{tool_id}: not registered in {reg_path.name}")
    if entry.get("status") != "active":
        raise ToolResolutionError(
            f"{tool_id}: registry status is {entry.get('status')!r} (only active tools may run)"
        )
    rel = str(entry.get("path") or "")
    normalized = rel.replace("\\", "/")
    if not normalized.startswith(ALLOWED_MANAGED_TOOL_PREFIX + "/"):
        raise ToolResolutionError(
            f"{tool_id}: registry path {rel!r} is outside {ALLOWED_MANAGED_TOOL_PREFIX}/"
        )
    resolved = tool_registry.resolve_tool_path(rel, base)
    if not resolved.is_file():
        raise ToolResolutionError(f"{tool_id}: resolved tool file missing: {resolved}")

    cfg_path = Path(config_path) if config_path is not None else base / "gov_exercise_config.json"
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolResolutionError(f"{tool_id}: cannot load tool whitelist {cfg_path.name}: {exc}") from exc
    allowed = list((config.get("tools") or {}).get(tool_id, []))
    expected_templates = {f"{{base}}/{normalized}", normalized}
    if allowed and not any(str(item).replace("\\", "/") in expected_templates for item in allowed):
        raise ToolResolutionError(
            f"{tool_id}: gov_exercise_config.json tools whitelist mismatch for {rel!r}"
        )
    return resolved, entry


# ---------------------------------------------------------------------------
# decoding-ledger（失败/成功都记账，不静默）
# ---------------------------------------------------------------------------

def append_decoding_ledger_row(workspace: Path, row: Mapping[str, object]) -> dict:
    """向 artifacts/decoding-ledger.csv 追加一行（表头缺失时按 DECODING_LEDGER_FIELDS
    建；追加行按现有行数自增 decoding_id）。notes 超长截断（MAX_LEDGER_NOTES_CHARS）。"""
    ledger_path = Path(workspace) / DECODING_LEDGER_CSV
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, str]] = []
    if ledger_path.is_file():
        with ledger_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            existing = [dict(item) for item in csv.DictReader(handle)]
    record = {field: str(row.get(field, "") or "") for field in DECODING_LEDGER_FIELDS}
    if not record.get("decoding_id").strip():
        record["decoding_id"] = f"DEC-{len(existing) + 1:04d}"
    if len(record.get("notes", "")) > MAX_LEDGER_NOTES_CHARS:
        record["notes"] = record["notes"][:MAX_LEDGER_NOTES_CHARS] + "…[truncated]"
    new_file = not ledger_path.is_file()
    with ledger_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DECODING_LEDGER_FIELDS))
        if new_file:
            writer.writeheader()
        writer.writerow(record)
    return record


def _capture_excerpt(text: str) -> str:
    """输出上限：截断到 MAX_CAPTURE_LINES 行 / MAX_CAPTURE_CHARS 字符并留标记。"""
    if not text:
        return ""
    lines = text.splitlines()
    excerpt = "\n".join(lines[:MAX_CAPTURE_LINES])
    if len(excerpt) > MAX_CAPTURE_CHARS:
        excerpt = excerpt[:MAX_CAPTURE_CHARS]
    truncated = []
    if len(lines) > MAX_CAPTURE_LINES:
        truncated.append(f"{len(lines) - MAX_CAPTURE_LINES} more lines")
    if len(text) > MAX_CAPTURE_CHARS:
        truncated.append(f"{len(text) - MAX_CAPTURE_CHARS} more chars")
    if truncated:
        excerpt = excerpt + "\n…[truncated: " + ", ".join(truncated) + "]"
    return excerpt


def _write_stderr_log(workspace: Path, tool: str, text: str, timestamp: str) -> Path:
    """完整 stderr 落 <ws>/logs/<tool>-<timestamp>.log（只落盘不进对话）。"""
    logs_dir = Path(workspace) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    safe_tool = re.sub(r"[^A-Za-z0-9_.-]", "_", tool)
    log_path = logs_dir / f"{safe_tool}-{timestamp}.log"
    log_path.write_text(text or "", encoding="utf-8", errors="replace")
    return log_path


def _sha256_of(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ExtractionResult:
    """一次解包/反编译尝试的结果（成功与失败都记账；失败原因必填）。"""

    status: str  # "ok" | "failed"
    tool: str
    tool_version: str
    output_dir: str
    exit_code: int | None
    duration_seconds: float
    reason: str  # 失败原因（timeout / non-zero exit / entry-file check / …）
    stderr_log: str
    ledger_row: dict


def _run_decode_tool(
    *,
    tool_id: str,
    command: Sequence[str],
    workspace: Path,
    output_dir: Path,
    entry_check: Callable[[Path], tuple[bool, str]],
    material_id: str,
    input_type: str,
    input_ref: Path,
    mode: str,
    timeout_seconds: int,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    root: Path | None = None,
    registry_path: Path | None = None,
    config_path: Path | None = None,
) -> ExtractionResult:
    """子进程纪律的单一实现：registry 解析 → 超时执行 → stderr 落盘 → 入口核验 →
    账本行（成功失败都写）。"""
    resolved, entry = resolve_managed_tool(tool_id, root=root, registry_path=registry_path, config_path=config_path)
    version = str(entry.get("version") or "")
    run = runner or subprocess.run
    started = datetime.now()
    timestamp = started.strftime("%Y%m%d-%H%M%S")
    input_sha = _sha256_of(input_ref)
    exit_code: int | None = None
    reason = ""
    stderr_text = ""
    stdout_text = ""
    try:
        completed = run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stderr_text = completed.stderr or ""
        stdout_text = completed.stdout or ""
        if exit_code != 0:
            reason = f"non-zero exit {exit_code}"
    except subprocess.TimeoutExpired as exc:
        reason = f"timeout after {timeout_seconds}s"
        stderr_text = (exc.stderr or b"") if isinstance(exc.stderr, (bytes, bytearray)) else (exc.stderr or "")
        stderr_text = stderr_text.decode("utf-8", errors="replace") if isinstance(stderr_text, (bytes, bytearray)) else str(stderr_text)
    stderr_log_rel = ""
    try:
        log_path = _write_stderr_log(workspace, tool_id, stderr_text, timestamp)
        stderr_log_rel = str(log_path.relative_to(Path(workspace)))
    except ValueError:
        stderr_log_rel = str(log_path)

    status = "ok"
    recovered = ""
    if not reason:
        entry_ok, entry_note = entry_check(output_dir)
        if not entry_ok:
            status = "failed"
            reason = f"entry-file check failed: {entry_note}"
        else:
            recovered = entry_note
    if reason:
        status = "failed"
    notes_parts = [f"exit_code={exit_code}"] if exit_code is not None else []
    if reason:
        notes_parts.append(f"reason={reason}")
        stderr_excerpt = _capture_excerpt(stderr_text)
        if stderr_excerpt:
            notes_parts.append(f"stderr={stderr_excerpt.splitlines()[0][:120]}")
    else:
        stdout_excerpt = _capture_excerpt(stdout_text)
        if stdout_excerpt:
            notes_parts.append(f"stdout_first={stdout_excerpt.splitlines()[0][:120]}")
    ledger_row = append_decoding_ledger_row(
        workspace,
        {
            "material_id": material_id,
            "input_type": input_type,
            "input_ref": str(input_ref),
            "input_sha256": input_sha,
            "tool": tool_id,
            "tool_version": version,
            "mode": mode,
            "status": LEDGER_STATUS_OK if status == "ok" else LEDGER_STATUS_FAILED,
            "output_path": str(output_dir),
            "recovered_clues": recovered,
            "notes": "; ".join(notes_parts),
        },
    )
    duration = (datetime.now() - started).total_seconds()
    return ExtractionResult(
        status=status,
        tool=tool_id,
        tool_version=version,
        output_dir=str(output_dir),
        exit_code=exit_code,
        duration_seconds=duration,
        reason=reason,
        stderr_log=stderr_log_rel,
        ledger_row=ledger_row,
    )


def _check_apktool_output(out_dir: Path) -> tuple[bool, str]:
    """apktool 成功核验：AndroidManifest.xml + apktool.yml（package-analysis §2）。"""
    manifest = out_dir / "AndroidManifest.xml"
    if not manifest.is_file():
        return False, "AndroidManifest.xml missing"
    if not (out_dir / "apktool.yml").is_file():
        return False, "apktool.yml missing"
    return True, "AndroidManifest.xml+apktool.yml"


def _check_jadx_output(out_dir: Path) -> tuple[bool, str]:
    """jadx 成功核验：sources/ 下存在至少一个 .java 文件。"""
    sources = out_dir / "sources"
    if not sources.is_dir():
        return False, "sources/ directory missing"
    for _ in sources.rglob("*.java"):
        return True, "sources/*.java tree"
    return False, "no .java files under sources/"


def run_apktool(
    apk_path: Path,
    workspace: Path,
    package_name: str,
    *,
    material_id: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    root: Path | None = None,
    registry_path: Path | None = None,
    config_path: Path | None = None,
) -> ExtractionResult:
    """apktool 标准命令（方案 §7.1，实测参数 d -f -o）：
    java -jar <registry:apktool jar> d -f -o <ws>/artifacts/app/apktool/<pkg> <apk>。"""
    jar, _ = resolve_managed_tool(APKTOOL_TOOL_ID, root=root, registry_path=registry_path, config_path=config_path)
    out_dir = Path(workspace) / "artifacts" / "app" / "apktool" / package_name
    command = ["java", "-jar", str(jar), "d", "-f", "-o", str(out_dir), str(apk_path)]
    return _run_decode_tool(
        tool_id=APKTOOL_TOOL_ID,
        command=command,
        workspace=Path(workspace),
        output_dir=out_dir,
        entry_check=_check_apktool_output,
        material_id=material_id,
        input_type="package",
        input_ref=Path(apk_path),
        mode="apktool_d",
        timeout_seconds=timeout_seconds,
        runner=runner,
        root=root,
        registry_path=registry_path,
        config_path=config_path,
    )


def run_jadx(
    apk_path: Path,
    workspace: Path,
    package_name: str,
    *,
    material_id: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    root: Path | None = None,
    registry_path: Path | None = None,
    config_path: Path | None = None,
) -> ExtractionResult:
    """jadx 标准命令（方案 §7.1，实测参数 --deobf-min 3 --deobf-max 9）：
    <registry:jadx.bat> -d <ws>/artifacts/app/unpacked/<pkg> --deobf-min 3 --deobf-max 9 <apk>。"""
    jadx_bat, _ = resolve_managed_tool(JADX_TOOL_ID, root=root, registry_path=registry_path, config_path=config_path)
    out_dir = Path(workspace) / "artifacts" / "app" / "unpacked" / package_name
    command = [str(jadx_bat), "-d", str(out_dir), "--deobf-min", "3", "--deobf-max", "9", str(apk_path)]
    return _run_decode_tool(
        tool_id=JADX_TOOL_ID,
        command=command,
        workspace=Path(workspace),
        output_dir=out_dir,
        entry_check=_check_jadx_output,
        material_id=material_id,
        input_type="package",
        input_ref=Path(apk_path),
        mode="jadx_d",
        timeout_seconds=timeout_seconds,
        runner=runner,
        root=root,
        registry_path=registry_path,
        config_path=config_path,
    )


# ---------------------------------------------------------------------------
# AndroidManifest 深解析（权限/exported/intent-filter/allowBackup/debuggable/
# networkSecurityConfig/cleartext；package-analysis §9 索引）
# ---------------------------------------------------------------------------

_ANDROID_NS = "http://schemas.android.com/apk/res/android"
_COMPONENT_TAGS = ("activity", "activity-alias", "service", "receiver", "provider")


def parse_android_manifest(manifest_path: Path) -> dict:
    """解析 apktool 解码后的 AndroidManifest.xml（ElementTree，android: 命名空间）。
    输出结构化 dict：package/permissions/custom_permissions/components（exported/
    permission/intent_filters 含 data scheme/host/authority）/application 标志
    （allowBackup/debuggable/networkSecurityConfig/usesCleartextTraffic）。"""
    tree = ET.parse(Path(manifest_path))
    root = tree.getroot()

    def attr(element: ET.Element, name: str) -> str:
        return element.get(f"{{{_ANDROID_NS}}}{name}", "") or ""

    permissions: list[str] = []
    for node in root.findall("uses-permission"):
        name = attr(node, "name")
        if name:
            permissions.append(name)
    for node in root.findall("uses-permission-sdk-23"):
        name = attr(node, "name")
        if name and name not in permissions:
            permissions.append(name)
    custom_permissions: list[dict] = []
    for node in root.findall("permission"):
        name = attr(node, "name")
        if name:
            custom_permissions.append(
                {
                    "name": name,
                    "protection_level": attr(node, "protectionLevel") or "normal",
                }
            )

    components: list[dict] = []
    application = root.find("application")
    if application is not None:
        for tag in _COMPONENT_TAGS:
            for node in application.findall(tag):
                exported_attr = attr(node, "exported")
                exported = exported_attr if exported_attr in ("true", "false") else ""
                intent_filters: list[dict] = []
                for filt in node.findall("intent-filter"):
                    actions = [attr(action, "name") for action in filt.findall("action") if attr(action, "name")]
                    categories = [
                        attr(category, "name") for category in filt.findall("category") if attr(category, "name")
                    ]
                    data_specs: list[dict] = []
                    for data in filt.findall("data"):
                        spec = {
                            key: attr(data, key)
                            for key in ("scheme", "host", "port", "path", "pathPrefix", "pathPattern", "mimeType")
                            if attr(data, key)
                        }
                        if spec:
                            data_specs.append(spec)
                    intent_filters.append(
                        {"actions": actions, "categories": categories, "data": data_specs}
                    )
                components.append(
                    {
                        "kind": "activity" if tag == "activity-alias" else tag,
                        "name": attr(node, "name"),
                        "exported": exported,
                        "permission": attr(node, "permission"),
                        "intent_filters": intent_filters,
                    }
                )

    application_flags: dict = {}
    if application is not None:
        for key in ("allowBackup", "debuggable", "networkSecurityConfig", "usesCleartextTraffic", "name"):
            value = attr(application, key)
            if value:
                application_flags[key] = value

    return {
        "package": root.get("package", ""),
        "permissions": permissions,
        "custom_permissions": custom_permissions,
        "components": components,
        "application": application_flags,
    }


def manifest_ipc_component_rows(manifest: Mapping[str, object]) -> list[dict]:
    """manifest 组件 → ipc component-inventory 候选行（IPC 引擎 CSV 字段子集）。
    exported 属性缺省记 "unknown"（隐式导出判定归复核会话，本引擎不做推断）；
    带 intent-filter 的组件在 notes 标注 implicit_export_candidate 供人工判定。"""
    rows: list[dict] = []
    for component in manifest.get("components") or []:
        kind = str(component.get("kind") or "")
        name = str(component.get("name") or "")
        if not name:
            continue
        intent_filters = list(component.get("intent_filters") or [])
        schemes: list[str] = []
        authorities: list[str] = []
        actions: list[str] = []
        for filt in intent_filters:
            actions.extend(str(action) for action in filt.get("actions") or [])
            for data in filt.get("data") or []:
                if data.get("scheme"):
                    schemes.append(str(data["scheme"]))
                if data.get("host"):
                    authorities.append(str(data["host"]))
        rows.append(
            {
                "component_kind": kind if kind in ("activity", "service", "receiver", "provider") else "other",
                "component_name": name,
                "exported": str(component.get("exported") or "") or "unknown",
                "permission": str(component.get("permission") or ""),
                "intent_actions": ";".join(dict.fromkeys(actions)),
                "scheme": ";".join(dict.fromkeys(schemes)),
                "authority": ";".join(dict.fromkeys(authorities)),
                "source_material": "AndroidManifest.xml",
                "source_location": f"application/{kind}[@name={name}]",
                "notes": (
                    "implicit_export_candidate (intent-filter present, exported not declared)"
                    if intent_filters and not str(component.get("exported") or "")
                    else ""
                ),
            }
        )
    return rows


def manifest_deeplink_rows(manifest: Mapping[str, object]) -> list[dict]:
    """manifest intent-filter data → deeplink 复核队列候选行（scheme 声明只来自
    manifest，不发起任何拉起验证——契约红线）。"""
    rows: list[dict] = []
    for component in manifest.get("components") or []:
        name = str(component.get("name") or "")
        for filt in component.get("intent_filters") or []:
            for data in filt.get("data") or []:
                scheme = str(data.get("scheme") or "")
                if not scheme:
                    continue
                host = str(data.get("host") or "")
                path = str(data.get("pathPrefix") or data.get("path") or "")
                pattern = f"{scheme}://{host}{path}" if host else f"{scheme}://<host>{path}"
                rows.append(
                    {
                        "deep_link_pattern": pattern,
                        "scheme_type": "custom_scheme" if scheme not in ("http", "https") else "https_link",
                        "sensitive_params": "",
                        "component_ref": name,
                        "jump_target": "in_app",
                        "source_material": "AndroidManifest.xml",
                        "source_location": f"application/{component.get('kind')}[@name={name}]/intent-filter/data",
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# secrets / SDK / API 路径模式提取（值不进输出）
# ---------------------------------------------------------------------------

def scan_source_tree(source_dir: Path) -> dict:
    """遍历解包源码树提取三类索引（package-analysis §9）：
    - secret_hits：{pattern_id, file, line}——匹配值本身绝不入返回值（契约红线：
      密钥字符串无法证明有效性时只是 secret_candidate 线索，值不外泄）；
    - sdk_markers：{sdk, file, line}；
    - api_hits：URL（剥离 query）与 API 路径模式 {value, file, line}。"""
    source = Path(source_dir)
    secret_hits: list[dict] = []
    sdk_hits: list[dict] = []
    api_hits: list[dict] = []
    seen_api: set[tuple[str, str, str]] = set()
    for file_path in sorted(p for p in source.rglob("*") if p.is_file()):
        if file_path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            if file_path.stat().st_size > _SCAN_MAX_FILE_BYTES:
                continue
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(file_path.relative_to(source))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for pattern_id, compiled in _SECRET_PATTERN_COMPILED:
                if compiled.search(line):
                    secret_hits.append({"pattern_id": pattern_id, "file": rel, "line": line_no})
            for sdk_name, compiled in _SDK_MARKER_COMPILED:
                if compiled.search(line):
                    sdk_hits.append({"sdk": sdk_name, "file": rel, "line": line_no})
            for match in _API_URL_PATTERN.finditer(line):
                value = match.group(0).rstrip(".")
                key = (value, rel, str(line_no))
                if key not in seen_api:
                    seen_api.add(key)
                    api_hits.append({"value": value, "file": rel, "line": line_no})
            for match in _API_PATH_PATTERN.finditer(line):
                value = match.group(0).rstrip("/.")
                key = (value, rel, str(line_no))
                if key not in seen_api:
                    seen_api.add(key)
                    api_hits.append({"value": value, "file": rel, "line": line_no})
    return {
        "secret_hits": secret_hits,
        "sdk_markers": sdk_hits,
        "api_hits": api_hits,
        "sdks_detected": sorted({str(hit["sdk"]) for hit in sdk_hits}),
    }


# ---------------------------------------------------------------------------
# whitebox_triage.py --scan 薄包装（复用现有 62 条 sink 库，不重写扫描器）
# ---------------------------------------------------------------------------

def whitebox_scan_command(
    source_dir: Path,
    out_dir: Path,
    python_exe: str | None = None,
    root: Path | None = None,
) -> tuple[list[str], Path]:
    """构造 whitebox_triage --scan 命令（方案 §7.1 第三条）。返回 (命令, 脚本路径)。"""
    base = Path(root) if root is not None else repo_root()
    script = base / WHITEBOX_TRIAGE_SCRIPT
    command = [
        python_exe or sys.executable,
        str(script),
        "--source-dir",
        str(source_dir),
        "--out-dir",
        str(out_dir),
        "--scan",
    ]
    return command, script


def run_whitebox_scan(
    source_dir: Path,
    out_dir: Path,
    *,
    python_exe: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    root: Path | None = None,
) -> dict:
    """whitebox_triage.py --scan 薄包装：校验脚本在场 → 子进程执行（同款超时/输出
    上限纪律）→ 返回 {status, command, stdout_excerpt, stderr_excerpt}。"""
    command, script = whitebox_scan_command(source_dir, out_dir, python_exe=python_exe, root=root)
    if not script.is_file():
        return {
            "status": "failed",
            "command": command,
            "reason": f"whitebox triage script missing: {script}",
            "stdout_excerpt": "",
            "stderr_excerpt": "",
        }
    run = runner or subprocess.run
    try:
        completed = run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "command": command,
            "reason": f"timeout after {timeout_seconds}s",
            "stdout_excerpt": "",
            "stderr_excerpt": "",
        }
    status = "ok" if completed.returncode == 0 else "failed"
    return {
        "status": status,
        "command": command,
        "reason": "" if status == "ok" else f"non-zero exit {completed.returncode}",
        "stdout_excerpt": _capture_excerpt(completed.stdout or ""),
        "stderr_excerpt": _capture_excerpt(completed.stderr or ""),
    }


def _cli() -> int:
    """离线 CLI：tool-path / apktool / jadx / manifest / scan / whitebox 子命令。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline static extraction orchestration for app assessments "
        "(registry-gated apktool/jadx, manifest deep parse, secret/sdk scan)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    tool_parser = sub.add_parser("tool-path", help="Resolve a managed tool path from the registry")
    tool_parser.add_argument("tool_id", choices=[APKTOOL_TOOL_ID, JADX_TOOL_ID])
    tool_parser.add_argument("--root", default=None)

    apktool_parser = sub.add_parser("apktool", help="Decode a local APK copy (managed apktool)")
    apktool_parser.add_argument("--apk", required=True)
    apktool_parser.add_argument("--workspace", required=True)
    apktool_parser.add_argument("--package", required=True)
    apktool_parser.add_argument("--material-id", default="")
    apktool_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    jadx_parser = sub.add_parser("jadx", help="Decompile dex to java (managed jadx)")
    jadx_parser.add_argument("--apk", required=True)
    jadx_parser.add_argument("--workspace", required=True)
    jadx_parser.add_argument("--package", required=True)
    jadx_parser.add_argument("--material-id", default="")
    jadx_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    manifest_parser = sub.add_parser("manifest", help="Deep-parse a decoded AndroidManifest.xml")
    manifest_parser.add_argument("--manifest", required=True)

    scan_parser = sub.add_parser("scan", help="Scan an unpacked tree for secret/sdk/api markers")
    scan_parser.add_argument("--source-dir", required=True)

    whitebox_parser = sub.add_parser("whitebox", help="Thin wrapper: whitebox_triage.py --scan")
    whitebox_parser.add_argument("--source-dir", required=True)
    whitebox_parser.add_argument("--out-dir", required=True)
    whitebox_parser.add_argument("--python-exe", default=None)
    whitebox_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    args = parser.parse_args()
    if args.command == "tool-path":
        root = Path(args.root) if args.root else None
        try:
            resolved, entry = resolve_managed_tool(args.tool_id, root=root)
        except ToolResolutionError as exc:
            print(f"ERROR: {exc}", flush=True)
            return 2
        print(json.dumps({"path": str(resolved), "version": entry.get("version"), "status": entry.get("status")}, ensure_ascii=False))
        return 0
    if args.command in ("apktool", "jadx"):
        runner = run_apktool if args.command == "apktool" else run_jadx
        result = runner(
            Path(args.apk),
            Path(args.workspace),
            args.package,
            material_id=args.material_id,
            timeout_seconds=args.timeout,
        )
        print(
            json.dumps(
                {
                    "status": result.status,
                    "tool": result.tool,
                    "output_dir": result.output_dir,
                    "exit_code": result.exit_code,
                    "reason": result.reason,
                    "stderr_log": result.stderr_log,
                    "ledger_row": result.ledger_row,
                },
                ensure_ascii=False,
            )
        )
        return 0 if result.status == "ok" else 1
    if args.command == "manifest":
        print(json.dumps(parse_android_manifest(Path(args.manifest)), ensure_ascii=False, indent=2))
        return 0
    if args.command == "scan":
        print(json.dumps(scan_source_tree(Path(args.source_dir)), ensure_ascii=False, indent=2))
        return 0
    result = run_whitebox_scan(
        Path(args.source_dir),
        Path(args.out_dir),
        python_exe=args.python_exe,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
