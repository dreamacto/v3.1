import json
from pathlib import Path

from policy_engine import PolicyEngine
from exercise_runtime import Target


def test_policy_requires_context_for_tools():
    import toolkit_integration as toolkit
    ok, message = toolkit.run_tool("rscan", url="https://example.test")
    assert not ok
    assert "PolicyEngine" in message


def test_policy_default_denies_unknown_and_blocked(tmp_path: Path):
    engine = PolicyEngine(
        {"blocked_actions": ["password_spray"]},
        targets=[Target(url="https://example.test", host="example.test", scheme="https", port=None)],
        run_dir=tmp_path,
        entrypoint="test",
    )
    assert not engine.authorize_action("password_spray").allowed
    assert not engine.authorize_target("https://other.test").allowed
    assert engine.authorize_action("probe", "https://example.test").allowed
    assert (tmp_path / "policy_decisions.jsonl").is_file()


def test_policy_invalid_config_fails_closed():
    engine = PolicyEngine({"blocked_actions": "not-a-list"})
    assert not engine.valid
    assert not engine.authorize_action("probe").allowed


def test_domain_root_authorizes_child_host_and_records_match(tmp_path: Path):
    engine = PolicyEngine(
        {"blocked_actions": []},
        targets=[Target(url="https://abc.com", host="abc.com", scheme="https", port=None)],
        run_dir=tmp_path,
        entrypoint="test",
    )
    decision = engine.authorize_target("https://123.abc.com/api")
    assert decision.allowed
    assert decision.matched_scope_anchor == "abc.com"
    assert decision.scope_match_kind == "domain_suffix"
    assert decision.domain_authorized is True
    audit = (tmp_path / "policy_decisions.jsonl").read_text(encoding="utf-8")
    assert "domain_suffix" in audit and "abc.com" in audit


def test_exact_child_target_does_not_authorize_sibling(tmp_path: Path):
    engine = PolicyEngine(
        {"blocked_actions": []},
        targets=[Target(url="https://www.abc.com", host="www.abc.com", scope_mode="exact", explicit_narrowing=True)],
        run_dir=tmp_path,
        entrypoint="test",
    )
    assert not engine.authorize_target("https://api.abc.com").allowed
    assert not engine.authorize_target("https://evilabc.com").allowed
