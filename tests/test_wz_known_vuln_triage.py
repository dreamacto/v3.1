"""wz skill known_vuln_triage 阶段接线测试（2026-09-07 P0，方案 §3 W-1）。

覆盖：
  - init_engagement.py：PHASES 在 application_mapping 之后插入 known_vuln_triage、
    三 substatus（template_detect/product_screen/takeover_check）空串种子、
    artifacts/known-vuln/ 预建；
  - audit_engagement.py：完成判据（三 substatus 非空 + nuclei-detect.jsonl 存在）、
    非法 substatus/未知子阶段负例、not_applicable 须理由；
  - 兼容性硬要求：旧 workspace 的 phase_status.json 没有该阶段行 → 审计不判违例、
    resume 不补插阶段行（只对新 seed 的 engagement 生效）。

skill 脚本自包含（不 import src 包），通过 importlib 按路径加载 canonical 脚本。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

INIT_SCRIPT = ROOT / ".agents" / "skills" / "wz" / "scripts" / "init_engagement.py"
AUDIT_SCRIPT = ROOT / ".agents" / "skills" / "wz" / "scripts" / "audit_engagement.py"

KNOWN_VULN_SUBPHASES = ("template_detect", "product_screen", "takeover_check")
KNOWN_VULN_ARTIFACT = ROOT / "wordlists" / "nuclei_detect_include.ids"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def init_mod():
    return _load_module("wz_init_engagement_kvt", INIT_SCRIPT)


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module("wz_audit_engagement_kvt", AUDIT_SCRIPT)


def _run_init(init_mod, tmp_path: Path, *extra: str) -> Path:
    out = tmp_path / "engagement"
    old_argv = sys.argv
    sys.argv = [str(INIT_SCRIPT), "example.com", "--output", str(out), *extra]
    try:
        code = init_mod.main()
    finally:
        sys.argv = old_argv
    assert code == 0, f"init failed with exit code {code}"
    return out


def _phase_row(root: Path, phase: str) -> dict:
    payload = json.loads((root / "phase_status.json").read_text(encoding="utf-8-sig"))
    return next(row for row in payload["phases"] if row["phase"] == phase)


def _write_phase(root: Path, phase: str, remove: tuple[str, ...] = (), **fields) -> None:
    path = root / "phase_status.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    for row in payload["phases"]:
        if row["phase"] == phase:
            row.update(fields)
            for key in remove:
                row.pop(key, None)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _drop_phase(root: Path, phase: str) -> None:
    """模拟旧 workspace：phase_status.json 里没有该阶段行（2026-09-07 前 seed）。"""
    path = root / "phase_status.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    payload["phases"] = [row for row in payload["phases"] if row["phase"] != phase]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _kvt_issues(result: dict) -> list[str]:
    return [issue for issue in result["issues"] if issue.startswith("known_vuln_triage")]


# ---------------------------------------------------------------------------
# init：阶段插入位置 / substatus 种子 / artifacts 预建
# ---------------------------------------------------------------------------

def test_init_inserts_known_vuln_triage_after_application_mapping(init_mod):
    phases = init_mod.PHASES
    assert "known_vuln_triage" in phases
    assert phases.index("known_vuln_triage") == phases.index("application_mapping") + 1
    assert phases[phases.index("known_vuln_triage") + 1] == "unauthenticated_testing"


def test_init_seeds_three_empty_substatuses(init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    row = _phase_row(out, "known_vuln_triage")
    assert row["substatuses"] == {name: "" for name in KNOWN_VULN_SUBPHASES}
    assert row["status"] == "pending"


def test_init_precreates_known_vuln_artifacts_dir(init_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    assert (out / "artifacts" / "known-vuln").is_dir()


def test_init_and_audit_subphase_constants_match(init_mod, audit_mod):
    assert tuple(init_mod.KNOWN_VULN_TRIAGE_SUBPHASES) == KNOWN_VULN_SUBPHASES
    assert tuple(audit_mod.KNOWN_VULN_TRIAGE_SUBPHASES) == KNOWN_VULN_SUBPHASES
    assert audit_mod.KNOWN_VULN_TRIAGE_ARTIFACT == "artifacts/known-vuln/nuclei-detect.jsonl"


# ---------------------------------------------------------------------------
# audit：完成判据 + 负例
# ---------------------------------------------------------------------------

def test_audit_fresh_workspace_reports_no_known_vuln_issues(init_mod, audit_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    result = audit_mod.audit(out)
    assert _kvt_issues(result) == []
    assert result["known_vuln_triage_substatuses"] == {name: "" for name in KNOWN_VULN_SUBPHASES}
    # 新 seed 的 workspace：该阶段 pending → 计入核心未完成
    assert "known_vuln_triage" in result["incomplete_core_phases"]


def test_audit_complete_without_substatuses_is_flagged(init_mod, audit_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _write_phase(out, "known_vuln_triage", status="complete", remove=("substatuses",))
    result = audit_mod.audit(out)
    assert any("substatuses are not recorded" in i for i in _kvt_issues(result))


def test_audit_complete_with_missing_substatus_or_artifact_is_flagged(init_mod, audit_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    # 三 substatus 只落盘一个 + 无 nuclei-detect.jsonl → 两条违例
    _write_phase(
        out,
        "known_vuln_triage",
        status="complete",
        substatuses={
            "template_detect": "tested",
            "product_screen": "",
            "takeover_check": "",
        },
    )
    result = audit_mod.audit(out)
    issues = _kvt_issues(result)
    assert sum("has no recorded substatus" in i for i in issues) == 2
    assert any("nuclei-detect.jsonl" in i and "is missing" in i for i in issues)
    assert "known_vuln_triage" not in result["incomplete_core_phases"]


def test_audit_complete_with_all_substatuses_and_artifact_passes(init_mod, audit_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    artifact = out / "artifacts" / "known-vuln" / "nuclei-detect.jsonl"
    artifact.write_text('{"template": "tech-detect"}\n', encoding="utf-8")
    _write_phase(
        out,
        "known_vuln_triage",
        status="complete",
        substatuses={name: "tested" for name in KNOWN_VULN_SUBPHASES},
    )
    result = audit_mod.audit(out)
    assert _kvt_issues(result) == []
    assert "known_vuln_triage" not in result["incomplete_core_phases"]


def test_audit_invalid_substatus_value_and_unknown_subphase_flagged(init_mod, audit_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _write_phase(
        out,
        "known_vuln_triage",
        substatuses={"template_detect": "definitely_vulnerable", "ghost_check": "tested"},
    )
    result = audit_mod.audit(out)
    issues = _kvt_issues(result)
    assert any("invalid substatus" in i for i in issues)
    assert any("unknown subphase" in i for i in issues)


def test_audit_not_applicable_without_reason_is_flagged(init_mod, audit_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _write_phase(out, "known_vuln_triage", status="not_applicable", reason="")
    result = audit_mod.audit(out)
    assert any(
        "not_applicable requires a reason" in i for i in result["issues"]
    )


# ---------------------------------------------------------------------------
# 兼容性硬要求：旧 workspace（无该阶段行）不判违例，resume 不补插
# ---------------------------------------------------------------------------

def test_audit_legacy_workspace_without_phase_is_not_flagged(init_mod, audit_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _drop_phase(out, "known_vuln_triage")
    result = audit_mod.audit(out)
    assert _kvt_issues(result) == []
    assert result["known_vuln_triage_substatuses"] == {}
    # 旧 workspace：无该阶段 → 不计入核心未完成（不得判既有 engagement 违例）
    assert "known_vuln_triage" not in result["incomplete_core_phases"]


def test_resume_does_not_insert_phase_into_legacy_workspace(init_mod, audit_mod, tmp_path):
    out = _run_init(init_mod, tmp_path)
    _drop_phase(out, "known_vuln_triage")
    assert _run_init(init_mod, tmp_path, "--resume") == out
    payload = json.loads((out / "phase_status.json").read_text(encoding="utf-8-sig"))
    assert all(row["phase"] != "known_vuln_triage" for row in payload["phases"])
    result = audit_mod.audit(out)
    assert _kvt_issues(result) == []


def test_resume_upgrades_existing_kvt_row_missing_substatuses(init_mod, tmp_path):
    """防御性：已含该阶段行但缺 substatuses 的文件，resume 补三键种子。"""
    out = _run_init(init_mod, tmp_path)
    _write_phase(out, "known_vuln_triage", remove=("substatuses",))
    assert _run_init(init_mod, tmp_path, "--resume") == out
    row = _phase_row(out, "known_vuln_triage")
    assert row["substatuses"] == {name: "" for name in KNOWN_VULN_SUBPHASES}


# ---------------------------------------------------------------------------
# 盘上事实：Tier A 白名单存在（ROE 授权边界的载体）
# ---------------------------------------------------------------------------

def test_tier_a_whitelist_files_present():
    assert KNOWN_VULN_ARTIFACT.is_file(), "wordlists/nuclei_detect_include.ids 必须在盘上"
    header = (ROOT / "wordlists" / "nuclei_detect_include.txt").read_text(
        encoding="utf-8", errors="ignore"
    ).splitlines()[:4]
    assert any("policy" in line.lower() for line in header), "人读版必须保留政策头注释"
