from exercise_runtime import Target
from policy_engine import PolicyEngine


def test_default_domain_mode_from_child_host_allows_root_and_sibling():
    engine = PolicyEngine({"blocked_actions": []}, targets=[Target(url="https://www.example.com", host="www.example.com")])
    assert engine.authorize_target("https://example.com").allowed
    assert engine.authorize_target("https://api.example.com").allowed
    assert engine.authorize_target("https://deep.api.example.com").allowed
    assert not engine.authorize_target("https://evil-example.com").allowed
    assert not engine.authorize_target("https://example.com.evil.net").allowed


def test_exact_mode_keeps_scope_narrow():
    target = Target(url="https://www.example.com", host="www.example.com", scope_mode="exact", explicit_narrowing=True)
    engine = PolicyEngine({"blocked_actions": []}, targets=[target])
    assert engine.authorize_target("https://www.example.com").allowed
    assert not engine.authorize_target("https://api.example.com").allowed
