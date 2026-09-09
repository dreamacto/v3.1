"""tests/test_xcx_backend_component_screening.py —— X-1 backend_web_api_testing
组件筛查 substatus 接线 + X-4 passive_leak_dork 分支的 skill 层测试
（2026-09-07 P1，方案 §4；init/audit 三镜像一致性由 check_skill_drift 锁定，此处
测 canonical .agents 副本）。

覆盖：
  - X-1 常量：init/audit 的 BACKEND_COMPONENT_REVIEW_BRANCHES 与产物路径同源；
  - X-1 阶段种子：新 workspace 的 backend_web_api_testing 行带
    {"component_nday_screening": ""}（空串=未记录）；artifacts/backend-component/
    目录预建但不种空 nday-screen.jsonl（tested 完成判据要求真实扫描输出在盘）；
  - X-1 游标隔离：init 只写 phase_status.miniapp.json，全程不产生 WZ 的
    phase_status.json；
  - X-1 audit：pending 正例；complete 未记录/非法值/未知分支/tested 缺产物/
    not_applicable 缺理由 负例；tested + 产物在盘正例；
  - X-1 legacy 容忍：行不带 substatuses 键（既有工作区形态）→ 零违例；
  - X-4 crypto 五分支种子（passive_leak_dork 空串在列）；
  - X-4 legacy 容忍：crypto complete 且行内 substatuses 缺 passive_leak_dork 键
    （zjlyxy 既有形态）→ 该分支零新违例。

纯离线，不发任何网络请求。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

INIT_SCRIPT = ROOT / ".agents" / "skills" / "xcx" / "scripts" / "init_miniapp_engagement.py"
AUDIT_SCRIPT = ROOT / ".agents" / "skills" / "xcx" / "scripts" / "audit_miniapp_engagement.py"
CONTRACT_PATH = ROOT / "contracts" / "miniapp_storage_package_schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def init_mod():
    return _load_module("xcx_init_miniapp_p1x1", INIT_SCRIPT)


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module("xcx_audit_miniapp_p1x1", AUDIT_SCRIPT)


@pytest.fixture(scope="module")
def contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8-sig"))


def _run_init(init_mod, tmp_path: Path) -> Path:
    out = tmp_path / "engagement"
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "demo-miniapp", "--output", str(out)]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 0
    return out


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _phase_row(root: Path, phase: str) -> dict:
    return next(
        row for row in _load_json(root / "phase_status.miniapp.json")["phases"]
        if row["phase"] == phase
    )


def _update_phase(root: Path, phase: str, **fields) -> dict:
    payload = _load_json(root / "phase_status.miniapp.json")
    row = next(r for r in payload["phases"] if r["phase"] == phase)
    row.update(fields)
    (root / "phase_status.miniapp.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return row


# ---------------------------------------------------------------------------
# X-1 常量同源（init ↔ audit）
# ---------------------------------------------------------------------------

def test_backend_component_constants_match_between_init_and_audit(init_mod, audit_mod):
    assert (
        init_mod.BACKEND_COMPONENT_REVIEW_BRANCHES
        == audit_mod.BACKEND_COMPONENT_REVIEW_BRANCHES
    )
    assert (
        init_mod.BACKEND_COMPONENT_SCREEN_ARTIFACT
        == audit_mod.BACKEND_COMPONENT_SCREEN_ARTIFACT
        == "artifacts/backend-component/nday-screen.jsonl"
    )
    assert init_mod.BACKEND_COMPONENT_REVIEW_BRANCHES["backend_web_api_testing"] == (
        "component_nday_screening",
    )


# ---------------------------------------------------------------------------
# X-1 阶段种子 + 游标隔离
# ---------------------------------------------------------------------------

def test_init_seeds_backend_component_substatus(init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    row = _phase_row(out, "backend_web_api_testing")
    assert row["status"] == "pending"
    assert row["substatuses"] == {"component_nday_screening": ""}


def test_init_precreates_backend_component_dir_without_empty_artifact(init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    assert (out / "artifacts" / "backend-component").is_dir()
    # 空壳扫描输出不算覆盖证据：不预建 nday-screen.jsonl
    assert not (out / init_mod.BACKEND_COMPONENT_SCREEN_ARTIFACT).is_file()


def test_init_writes_only_miniapp_cursor(init_mod, tmp_path):
    """游标隔离（X-1 红线）：xcx 只写 phase_status.miniapp.json，不产生 WZ 的
    phase_status.json。"""
    out = _run_init(init_mod, tmp_path)
    assert (out / "phase_status.miniapp.json").is_file()
    assert not (out / "phase_status.json").exists()


# ---------------------------------------------------------------------------
# X-1 audit 规则
# ---------------------------------------------------------------------------

def _screen_issues(audit_mod, root: Path, row: dict) -> list[str]:
    return audit_mod.backend_component_screening_issues(root, row)


def test_audit_pending_row_with_seed_key_is_clean(audit_mod, init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    assert _screen_issues(audit_mod, out, _phase_row(out, "backend_web_api_testing")) == []


def test_audit_complete_without_recorded_substatus_rejected(audit_mod, init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _update_phase(out, "backend_web_api_testing", status="complete")
    issues = _screen_issues(audit_mod, out, _phase_row(out, "backend_web_api_testing"))
    assert any("has no recorded substatus" in issue for issue in issues)


def test_audit_invalid_substatus_and_unknown_branch_rejected(audit_mod, init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _update_phase(
        out,
        "backend_web_api_testing",
        substatuses={"component_nday_screening": "maybe"},
    )
    issues = _screen_issues(audit_mod, out, _phase_row(out, "backend_web_api_testing"))
    assert any("invalid substatus" in issue for issue in issues)
    _update_phase(
        out,
        "backend_web_api_testing",
        substatuses={"component_nday_screening": "", "nuclei_full_sweep": "tested"},
    )
    issues = _screen_issues(audit_mod, out, _phase_row(out, "backend_web_api_testing"))
    assert any("unknown review branch" in issue for issue in issues)


def test_audit_complete_tested_requires_artifact(audit_mod, init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _update_phase(
        out,
        "backend_web_api_testing",
        status="complete",
        substatuses={"component_nday_screening": "tested"},
    )
    issues = _screen_issues(audit_mod, out, _phase_row(out, "backend_web_api_testing"))
    assert any("nday-screen.jsonl" in issue and "missing" in issue for issue in issues)

    artifact = out / audit_mod.BACKEND_COMPONENT_SCREEN_ARTIFACT
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"template": "demo-detect", "host": "api.example.com"}\n', encoding="utf-8")
    assert _screen_issues(audit_mod, out, _phase_row(out, "backend_web_api_testing")) == []


def test_audit_complete_not_applicable_requires_reason(audit_mod, init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _update_phase(
        out,
        "backend_web_api_testing",
        status="complete",
        reason="",
        substatuses={"component_nday_screening": "not_applicable"},
    )
    issues = _screen_issues(audit_mod, out, _phase_row(out, "backend_web_api_testing"))
    assert any("not_applicable lacks a phase reason" in issue for issue in issues)

    _update_phase(
        out,
        "backend_web_api_testing",
        reason="no in-scope own-backend host after host classification",
    )
    assert _screen_issues(audit_mod, out, _phase_row(out, "backend_web_api_testing")) == []


def test_audit_legacy_row_without_substatuses_key_tolerated(audit_mod, init_mod, tmp_path):
    """legacy 容忍：既有工作区的行不带 substatuses 键（X-1 seed 之前），审计零违例。"""
    out = _run_init(init_mod, tmp_path)
    row = _update_phase(out, "backend_web_api_testing", status="complete")
    row.pop("substatuses", None)
    payload = _load_json(out / "phase_status.miniapp.json")
    for item in payload["phases"]:
        if item["phase"] == "backend_web_api_testing":
            item.pop("substatuses", None)
    (out / "phase_status.miniapp.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert _screen_issues(audit_mod, out, row) == []


# ---------------------------------------------------------------------------
# X-4 crypto passive_leak_dork（skill 层：种子 + legacy 容忍）
# ---------------------------------------------------------------------------

def test_init_seeds_crypto_five_branches_including_passive_leak_dork(
    init_mod, contract, tmp_path
):
    out = _run_init(init_mod, tmp_path)
    row = _phase_row(out, "crypto_and_secret_handling")
    expected = tuple(contract["phases"]["crypto_and_secret_handling"]["branches"])
    assert tuple(row["substatuses"]) == expected
    assert row["substatuses"]["passive_leak_dork"] == ""


def test_audit_crypto_legacy_row_without_leak_branch_key_tolerated(
    audit_mod, init_mod, tmp_path
):
    """X-4 legacy 容忍：crypto complete 且行内 substatuses 缺 passive_leak_dork 键
    （zjlyxy 等既有工作区形态）——新分支零违例（旧四分支语义不受影响）。"""
    out = _run_init(init_mod, tmp_path)
    legacy_substatuses = {
        "hardcoded_secrets": "tested",
        "custom_crypto": "not_applicable",
        "weak_random_key_derivation": "not_applicable",
        "debug_config_env_keys": "tested",
    }
    _update_phase(
        out,
        "crypto_and_secret_handling",
        status="complete",
        substatuses=dict(legacy_substatuses),
    )
    row = _phase_row(out, "crypto_and_secret_handling")
    issues = audit_mod.storage_package_review_issues(
        out, "crypto_and_secret_handling", row
    )
    assert not any("passive_leak_dork" in issue for issue in issues)


def test_audit_crypto_new_seed_complete_enforces_leak_branch(audit_mod, init_mod, tmp_path):
    """新 seed 键集含 passive_leak_dork：complete 时空串仍被强制（不得借 legacy
    语义静默漏检）。"""
    out = _run_init(init_mod, tmp_path)
    _update_phase(out, "crypto_and_secret_handling", status="complete")
    row = _phase_row(out, "crypto_and_secret_handling")
    issues = audit_mod.storage_package_review_issues(
        out, "crypto_and_secret_handling", row
    )
    assert any(
        "crypto_and_secret_handling: phase complete but branch passive_leak_dork "
        "has no recorded substatus" in issue
        for issue in issues
    )
