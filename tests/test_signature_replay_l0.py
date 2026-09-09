"""tests/test_signature_replay_l0.py —— P2 ⑧（X-2）L0 受控重放执行器专属测试。

正例：plan 生成（约束回显/纯数据零执行）、ingest 三窗口解析与确定性派生。
负例：write_risk_ack=true 拒绝（红线）、ack 缺失 fail-closed、写方法/业务型
端点拒绝、每 host 超端点预算拒绝、同窗口重复观测拒绝（单请求重放 1 次）、
凭证类键拒绝、confirmed 永不产生、窗口不齐全 inconclusive。
契约锁定：模块常量 ↔ contracts/miniapp_auth_schema.json l0_executor 段。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for candidate in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from authorized_assessment.miniapp import signature_replay_l0 as srl  # noqa: E402


GOOD_CONFIG = {
    "authorization_basis": "operator_supplied_material",
    "write_risk_ack": False,
    "evidence_ref": "artifacts/miniapp/auth/signature-replay-review.json",
    "endpoints": [
        {
            "url": "https://api-a.example.com/v1/user/info?sign=abc&nonce=n1",
            "method": "GET",
            "endpoint_class": "read_only_data",
            "evidence_ref": "artifacts/miniapp/traffic/case-0001.md",
        },
        {
            "url": "https://api-b.example.com/v1/order/detail?sign=def&nonce=n2",
            "method": "GET",
            "endpoint_class": "read_only_data",
            "evidence_ref": "artifacts/miniapp/traffic/case-0002.md",
        },
    ],
}


def observation(url: str, window: str, status: int, fingerprint: str, **extra) -> dict:
    row = {
        "url": url,
        "window": window,
        "http_status": status,
        "body_fingerprint": fingerprint,
        "body_len": 512,
        "evidence_ref": "artifacts/miniapp/auth/l0-runbook.md",
    }
    row.update(extra)
    return row


# ---------- plan ----------

def test_plan_generates_constrained_runbook():
    plan, violations = srl.build_signature_replay_l0_plan(GOOD_CONFIG)
    assert violations == []
    assert plan["executable"] is True
    assert plan["plan_only"] is True
    assert plan["module_executes"] is False
    assert plan["write_risk_ack"] is False
    assert len(plan["endpoints"]) == 2
    for endpoint in plan["endpoints"]:
        assert endpoint["method"] == "GET"
        assert endpoint["endpoint_class"] == "read_only_data"
        labels = [step["label"] for step in endpoint["replay_steps"]]
        assert labels == ["t_plus_5s", "t_plus_60s"]
        for step in endpoint["replay_steps"]:
            assert step["replays"] == 1
            assert step["delay_floor_seconds"] >= 3.0
    assert plan["constraints"]["max_endpoints_per_host"] == 3
    assert plan["constraints"]["write_risk_ack_must_be"] is False
    assert any("永不重放" in line for line in plan["red_lines"])


def test_plan_rejects_write_risk_ack_true():
    config = json.loads(json.dumps(GOOD_CONFIG))
    config["write_risk_ack"] = True
    plan, violations = srl.build_signature_replay_l0_plan(config)
    assert plan["executable"] is False
    assert any("write_risk_ack=true 被拒绝" in v for v in violations)
    assert all(not endpoint["replay_steps"] for endpoint in plan["endpoints"])


def test_plan_rejects_missing_write_risk_ack_fail_closed():
    config = json.loads(json.dumps(GOOD_CONFIG))
    del config["write_risk_ack"]
    plan, violations = srl.build_signature_replay_l0_plan(config)
    assert plan["executable"] is False
    assert any("fail-closed" in v for v in violations)


def test_plan_rejects_write_method_and_business_endpoint():
    config = json.loads(json.dumps(GOOD_CONFIG))
    config["endpoints"][0]["method"] = "POST"
    config["endpoints"][1]["endpoint_class"] = "business_action"
    _, violations = srl.build_signature_replay_l0_plan(config)
    assert any("只读 GET 型端点" in v for v in violations)
    assert any("business_action" in v and "被拒绝" in v for v in violations)
    config["endpoints"][1]["endpoint_class"] = "write"
    _, violations = srl.build_signature_replay_l0_plan(config)
    assert any("'write'" in v for v in violations)


def test_plan_rejects_endpoint_budget_exceeded():
    config = json.loads(json.dumps(GOOD_CONFIG))
    for index in range(3, 6):
        config["endpoints"].append(
            {
                "url": f"https://api-a.example.com/v1/item/{index}?sign=x&nonce=n{index}",
                "method": "GET",
                "endpoint_class": "read_only_data",
            }
        )
    plan, violations = srl.build_signature_replay_l0_plan(config)
    assert plan["executable"] is False
    assert any("超预算" in v for v in violations)
    assert any("api-a.example.com" in v for v in violations)


def test_plan_rejects_duplicate_url():
    config = json.loads(json.dumps(GOOD_CONFIG))
    config["endpoints"][1]["url"] = config["endpoints"][0]["url"]
    _, violations = srl.build_signature_replay_l0_plan(config)
    assert any("url 重复" in v for v in violations)


def test_plan_rejects_bad_authorization_basis():
    config = json.loads(json.dumps(GOOD_CONFIG))
    config["authorization_basis"] = "operator_guess"
    _, violations = srl.build_signature_replay_l0_plan(config)
    assert any("authorization_basis 非法" in v for v in violations)


# ---------- ingest ----------

URL_A = GOOD_CONFIG["endpoints"][0]["url"]
URL_B = GOOD_CONFIG["endpoints"][1]["url"]


def test_ingest_derives_all_outcomes():
    results = [
        # A：双窗接受 → candidate
        observation(URL_A, "original", 200, "fp-a"),
        observation(URL_A, "t_plus_5s", 200, "fp-a"),
        observation(URL_A, "t_plus_60s", 200, "fp-a"),
        # B：T+5s 接受、T+60s 拒绝 → signal（有窗口控制）
        observation(URL_B, "original", 200, "fp-b"),
        observation(URL_B, "t_plus_5s", 200, "fp-b"),
        observation(URL_B, "t_plus_60s", 401, "fp-err"),
    ]
    rows, violations = srl.ingest_signature_replay_l0_results(results)
    assert violations == []
    assert len(rows) == 2
    by_url = {row["url"]: row for row in rows}
    assert by_url[URL_A]["status"] == "candidate"
    assert by_url[URL_A]["replay_outcome"] == "accepted_both_windows"
    assert by_url[URL_A]["branch"] == "replay_window"
    assert by_url[URL_B]["status"] == "signal"
    assert by_url[URL_B]["replay_outcome"] == "accepted_t5_only"


def test_ingest_rejected_both_windows_is_signal_and_200_with_error_is_rejection():
    results = [
        observation(URL_A, "original", 200, "fp-a"),
        # 200 但业务错误类别 → 不算接受（200-with-error 形态）
        observation(URL_A, "t_plus_5s", 200, "fp-a", response_class="business_error"),
        observation(URL_A, "t_plus_60s", 403, "fp-deny"),
    ]
    rows, violations = srl.ingest_signature_replay_l0_results(results)
    assert violations == []
    assert rows[0]["status"] == "signal"
    assert rows[0]["replay_outcome"] == "rejected_both_windows"


def test_ingest_rejects_duplicate_window_rows():
    results = [
        observation(URL_A, "original", 200, "fp-a"),
        observation(URL_A, "t_plus_5s", 200, "fp-a"),
        observation(URL_A, "t_plus_5s", 200, "fp-a"),
        observation(URL_A, "t_plus_60s", 200, "fp-a"),
    ]
    _, violations = srl.ingest_signature_replay_l0_results(results)
    assert any("单请求重放 1 次" in v for v in violations)


def test_ingest_incomplete_windows_are_inconclusive():
    results = [
        observation(URL_A, "original", 200, "fp-a"),
        observation(URL_A, "t_plus_5s", 200, "fp-a"),
    ]
    rows, violations = srl.ingest_signature_replay_l0_results(results)
    assert any("缺少 t_plus_60s" in v for v in violations)
    assert rows[0]["status"] == "inconclusive"


def test_ingest_rejects_credential_keys():
    results = [
        observation(URL_A, "original", 200, "fp-a", cookie="SESSIONID=xyz"),
        observation(URL_A, "t_plus_5s", 200, "fp-a"),
        observation(URL_A, "t_plus_60s", 200, "fp-a"),
    ]
    _, violations = srl.ingest_signature_replay_l0_results(results)
    assert any("credential-like key" in v for v in violations)


def test_ingest_rejects_unknown_window_and_missing_url():
    _, violations = srl.ingest_signature_replay_l0_results(
        [observation(URL_A, "t_plus_120s", 200, "fp-a"), {"window": "original"}]
    )
    assert any("window 非法" in v for v in violations)
    assert any("缺少 url" in v for v in violations)


# ---------- 行校验 ----------

def test_row_validation_rejects_confirmed_and_bad_outcome():
    row = {
        "row_id": "srl0-0001",
        "url": URL_A,
        "http_method": "GET",
        "branch": "replay_window",
        "status": "confirmed",
        "replay_outcome": "accepted_both_windows",
        "windows": {w: {"http_status": 200, "body_fingerprint": "fp"} for w in srl.L0_WINDOW_LABELS},
        "source": "signature_replay_l0_ingest",
        "evidence_ref": "e.md",
        "reason": "r",
    }
    violations = srl.validate_signature_replay_l0_row(row)
    assert any("confirmed" in v for v in violations)
    row["status"] = "candidate"
    row["replay_outcome"] = "rejected_both_windows"
    violations = srl.validate_signature_replay_l0_row(row)
    assert any("candidate 只能来自 accepted_both_windows" in v for v in violations)


def test_row_validation_requires_candidate_evidence_ref():
    row = {
        "row_id": "srl0-0001",
        "url": URL_A,
        "http_method": "GET",
        "branch": "replay_window",
        "status": "candidate",
        "replay_outcome": "accepted_both_windows",
        "windows": {w: {} for w in srl.L0_WINDOW_LABELS},
        "source": "signature_replay_l0_ingest",
        "evidence_ref": "",
        "reason": "r",
    }
    violations = srl.validate_signature_replay_l0_row(row)
    assert any("evidence_ref" in v for v in violations)


def test_ingest_never_produces_confirmed():
    results = [
        observation(URL_A, "original", 200, "fp-a", evidence_ref="run.md"),
        observation(URL_A, "t_plus_5s", 200, "fp-a", evidence_ref="run.md"),
        observation(URL_A, "t_plus_60s", 200, "fp-a", evidence_ref="run.md"),
    ]
    rows, _ = srl.ingest_signature_replay_l0_results(results)
    assert all(row["status"] in ("signal", "candidate", "inconclusive") for row in rows)


# ---------- 契约锁定 ----------

def test_module_constants_locked_to_contract():
    contract = json.loads(
        (PROJECT_ROOT / "contracts" / "miniapp_auth_schema.json").read_text(encoding="utf-8")
    )
    l0 = contract["l0_executor"]
    assert l0["artifact"] == srl.SIGNATURE_REPLAY_L0_ARTIFACT
    constraints = l0["constraints"]
    assert constraints["allowed_methods"] == list(srl.L0_ALLOWED_METHODS) == ["GET"]
    assert constraints["allowed_endpoint_class"] == srl.L0_ALLOWED_ENDPOINT_CLASS
    assert constraints["endpoint_classes"] == list(srl.L0_ENDPOINT_CLASSES)
    assert constraints["max_endpoints_per_host"] == srl.L0_MAX_ENDPOINTS_PER_HOST == 3
    assert constraints["min_delay_seconds"] == srl.L0_MIN_DELAY_SECONDS == 3.0
    assert constraints["time_window_offsets_seconds"] == list(srl.L0_TIME_WINDOW_OFFSETS_SECONDS) == [5, 60]
    assert constraints["replays_per_window"] == srl.L0_REPLAYS_PER_WINDOW == 1
    assert constraints["write_risk_ack_must_be"] is srl.L0_WRITE_RISK_ACK_MUST_BE is False
    assert l0["replay_outcomes"] == list(srl.L0_REPLAY_OUTCOMES)
    assert l0["row_statuses"] == list(srl.L0_ROW_STATUSES)
    assert "confirmed" not in l0["row_statuses"]
    assert l0["row_branch"] == srl.L0_ROW_BRANCH == "replay_window"


def test_constraints_are_hardcoded_red_lines():
    # 双保险：约束常量即红线语义，任何放宽（方法/预算/延迟/窗口数）都是契约漂移。
    assert srl.L0_ALLOWED_METHODS == ("GET",)
    assert srl.L0_MAX_ENDPOINTS_PER_HOST == 3
    assert srl.L0_MIN_DELAY_SECONDS >= 3.0
    assert srl.L0_TIME_WINDOW_OFFSETS_SECONDS == (5, 60)
    assert srl.L0_REPLAYS_PER_WINDOW == 1
    assert srl.L0_WRITE_RISK_ACK_MUST_BE is False
    assert "永不重放" in srl.L0_NEVER_REPLAY_RULE
