from src.authorized_assessment.scope import (
    classify_host,
    classify_scope_entry,
    normalize_scope_host,
)


def test_domain_anchor_includes_child_hosts_but_not_similar_suffixes():
    entries = [{"host": "abc.com", "domain_authorized": True}]
    assert classify_host("abc.com", entries).scope_state == "in_scope"
    child = classify_host("123.abc.com", entries)
    assert child.scope_state == "in_scope"
    assert child.match_kind == "domain_suffix"
    assert classify_host("deep.123.abc.com", entries).scope_state == "in_scope"
    assert classify_host("evilabc.com", entries).scope_state == "confirmation_required"
    assert classify_host("abc.com.evil.com", entries).scope_state == "confirmation_required"


def test_exact_host_does_not_widen_to_children_or_siblings():
    entries = [{"host": "www.abc.com", "domain_authorized": False}]
    assert classify_host("www.abc.com", entries).scope_state == "in_scope"
    assert classify_host("api.abc.com", entries).scope_state == "confirmation_required"


def test_wildcard_and_public_suffix_are_conservative():
    assert classify_host("api.abc.com", ["*.abc.com"]).match_kind == "wildcard"
    assert classify_host("api.co.uk", ["*.co.uk"]).scope_state == "confirmation_required"
    assert classify_scope_entry("co.uk", wildcard=True).scope_state == "confirmation_required"
    assert normalize_scope_host("ABC.COM.") == "abc.com"
    assert normalize_scope_host("127.0.0.1") == ""


def test_platform_and_third_party_take_precedence():
    entries = [{"host": "abc.com", "domain_authorized": True}]
    assert classify_host("login.abc.com", entries, platform_shared={"login.abc.com"}).scope_state == "platform_shared"
    assert classify_host("vendor.abc.com", entries, third_party={"vendor.abc.com"}).scope_state == "third_party"


def test_longest_domain_anchor_wins():
    result = classify_host(
        "api.dev.abc.com",
        [
            {"host": "abc.com", "domain_authorized": True},
            {"host": "dev.abc.com", "domain_authorized": True},
        ],
    )
    assert result.matched_anchor == "dev.abc.com"
