"""tests/test_input_testing_probe_budget.py —— W-4 input_testing 注入面受限
probe 预算制测试（2026-09-07 P1，方案 §3 W-4；tool_strategy input_testing notes
与 src/authorized_assessment/triage/input_testing.py 同源）。

覆盖三个规格用例 + 边界：
  - 预算内通过：白名单脚本、每 host ≤10 参数、单发、arjun 单 host ≤1 次；
  - 超预算拒绝：每 host >10 参数 / 单参数多发 / arjun 同 host 二次运行；
  - 非白名单脚本拒绝：sqlmap 及一切白名单外工具必须被拒（负例保留）；
  - 空台账 = 零 probe（纯离线管线）合法；audit 端到端把台账违例并入总体违例。

纯离线，不发任何网络请求。
"""
from __future__ import annotations

import json
from pathlib import Path

from authorized_assessment.triage import input_testing as itp


def _probe_row(host: str, tool: str, params: list[str], requests: int = 1) -> dict:
    return {
        "host": host,
        "tool": tool,
        "params": params,
        "requests_per_param": requests,
        "evidence_ref": "artifacts/input-testing/probe-evidence.md",
        "reason": "budgeted whitelist marker",
    }


def _write_ledger(workspace: Path, rows: list[dict]) -> None:
    path = workspace / itp.INPUT_TESTING_ARTIFACTS["probe_ledger_jsonl"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def test_probe_budget_within_limits_passes(tmp_path):
    """用例 1（预算内通过）：单 host 10 参数（两白名单脚本分摊、去重并集=10）、
    全部单发、arjun 恰好 1 次。"""
    rows = [
        _probe_row("api.example.com", "sqli_triage.py", ["id", "sort", "page", "kw"]),
        _probe_row("api.example.com", "xss_candidate_triage.py", ["name", "q", "nick", "title", "desc", "callback"]),
        _probe_row("api.example.com", "arjun", ["discovery-run"]),
    ]
    assert itp.validate_probe_ledger(rows) == []


def test_probe_budget_over_params_per_host_rejected(tmp_path):
    """用例 2a（超预算拒绝）：单 host 去重参数 11 个 > 上限 10。"""
    rows = [
        _probe_row("api.example.com", "sqli_triage.py", [f"p{i}" for i in range(6)]),
        _probe_row("api.example.com", "xss_candidate_triage.py", [f"q{i}" for i in range(5)]),
    ]
    violations = itp.validate_probe_ledger(rows)
    assert any("超预算" in v and "11" in v and "api.example.com" in v for v in violations)


def test_probe_budget_multi_shot_per_param_rejected(tmp_path):
    """用例 2b（超预算拒绝）：单参数 2 发 > 单发上限 1。"""
    rows = [_probe_row("api.example.com", "sqli_triage.py", ["id"], requests=2)]
    violations = itp.validate_probe_ledger(rows)
    assert any("超预算" in v and "单参数请求 2 次" in v for v in violations)


def test_probe_budget_second_discovery_run_rejected(tmp_path):
    """用例 2c（超预算拒绝）：arjun 同 host 第二次运行。"""
    rows = [
        _probe_row("api.example.com", "arjun", ["discovery-run-1"]),
        _probe_row("api.example.com", "arjun", ["discovery-run-2"]),
    ]
    violations = itp.validate_probe_ledger(rows)
    assert any("超预算" in v and "2 次" in v and "arjun" in v for v in violations)


def test_probe_non_whitelist_tool_rejected(tmp_path):
    """用例 3（非白名单脚本拒绝）：sqlmap 与一切白名单外工具必须被拒。"""
    for tool in ("sqlmap", "dalfox", "xsstrike", "nuclei"):
        rows = [_probe_row("api.example.com", tool, ["id"])]
        violations = itp.validate_probe_ledger(rows)
        assert any("非白名单" in v and tool in v for v in violations), tool


def test_probe_budget_is_per_host_not_global(tmp_path):
    """预算按 host 计：两个 host 各 10 参数不互占预算。"""
    rows = [
        _probe_row("a.example.com", "sqli_triage.py", [f"p{i}" for i in range(5)]),
        _probe_row("a.example.com", "xss_candidate_triage.py", [f"q{i}" for i in range(5)]),
        _probe_row("b.example.com", "sqli_triage.py", [f"p{i}" for i in range(5)]),
        _probe_row("b.example.com", "xss_candidate_triage.py", [f"q{i}" for i in range(5)]),
        _probe_row("a.example.com", "arjun", ["discovery-run"]),
        _probe_row("b.example.com", "arjun", ["discovery-run"]),
    ]
    assert itp.validate_probe_ledger(rows) == []


def test_probe_ledger_empty_means_zero_probes_and_is_valid(tmp_path):
    """空台账 = 零 probe（纯离线管线形态，batch6_4 语义保留）。"""
    assert itp.validate_probe_ledger([]) == []


def test_probe_row_contract_negatives(tmp_path):
    """行契约负例：缺字段/空 host/空 params/空参数名/非整数请求数。"""
    bad_rows = [
        {"tool": "sqli_triage.py", "params": ["id"], "requests_per_param": 1},
        _probe_row("", "sqli_triage.py", ["id"]),
        _probe_row("api.example.com", "sqli_triage.py", []),
        {**_probe_row("api.example.com", "sqli_triage.py", ["id"]), "params": ["id", " "]},
        {**_probe_row("api.example.com", "sqli_triage.py", ["id"]), "requests_per_param": "1"},
    ]
    for rows in ([row] for row in bad_rows):
        assert itp.validate_probe_ledger(rows) != []


def test_audit_input_testing_integrates_probe_ledger(tmp_path):
    """audit 端到端：骨架产物 + 预算内台账 → 通过；非白名单/超预算台账 → 违例。"""
    itp.init_input_testing_artifacts(tmp_path)
    _write_ledger(
        tmp_path,
        [
            _probe_row("api.example.com", "sqli_triage.py", ["id", "sort"]),
            _probe_row("api.example.com", "arjun", ["discovery-run"]),
        ],
    )
    ok, violations = itp.audit_input_testing(tmp_path)
    assert ok, violations

    _write_ledger(tmp_path, [_probe_row("api.example.com", "sqlmap", ["id"])])
    ok, violations = itp.audit_input_testing(tmp_path)
    assert not ok
    assert any("非白名单" in v for v in violations)

    _write_ledger(
        tmp_path,
        [
            _probe_row("api.example.com", "sqli_triage.py", [f"p{i}" for i in range(6)]),
            _probe_row("api.example.com", "xss_candidate_triage.py", [f"q{i}" for i in range(5)]),
        ],
    )
    ok, violations = itp.audit_input_testing(tmp_path)
    assert not ok
    assert any("超预算" in v and "11" in v for v in violations)


def test_probe_constants_match_strategy_contract():
    """白名单与预算常量单一来源（tool_strategy input_testing notes 文案同源）：
    三个白名单脚本 + 每 host 10 参数 + 单发 + arjun 单 host 1 次。"""
    assert set(itp.PROBE_TOOL_WHITELIST) == {
        "sqli_triage.py",
        "xss_candidate_triage.py",
        "arjun",
    }
    assert itp.PROBE_TOOL_WHITELIST["arjun"]["kind"] == "discovery"
    assert itp.PROBE_BUDGET_MAX_PARAMS_PER_HOST == 10
    assert itp.PROBE_BUDGET_MAX_REQUESTS_PER_PARAM == 1
    assert itp.PROBE_DISCOVERY_MAX_RUNS_PER_HOST == 1
    assert (
        itp.INPUT_TESTING_ARTIFACTS["probe_ledger_jsonl"]
        == "artifacts/input-testing/probe-ledger.jsonl"
    )
