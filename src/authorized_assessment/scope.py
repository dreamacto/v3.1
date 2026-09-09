"""Shared, conservative host-scope classification.

This module deliberately separates *domain relationship* from *authorization*.
A suffix match is only an authorization match when the scope entry explicitly
represents a domain or wildcard authorization.  Exact host entries never widen
to sibling or child hosts.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, asdict


# Conservative list of public suffixes that are especially easy to misuse as
# an authorization anchor. Unknown multi-label suffixes fail closed elsewhere.
PUBLIC_SUFFIXES = frozenset({
    "com", "net", "org", "edu", "gov", "mil", "int", "io", "co",
    "uk", "us", "cn", "de", "fr", "jp", "au", "ca", "in", "ru",
    "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn", "mil.cn",
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
    "github.io", "appspot.com", "cloudfront.net",
})
KNOWN_MULTI_LABEL_SUFFIXES = frozenset({
    "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn", "mil.cn",
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
})
_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def registrable_parent(value: object) -> str:
    """Return a conservative eTLD+1 approximation for candidate grouping."""
    host = normalize_scope_host(value)
    if not host:
        return ""
    labels = host.split(".")
    if len(labels) < 2:
        return ""
    suffix = ".".join(labels[-2:])
    if suffix in KNOWN_MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    if len(labels) == 2:
        return suffix if suffix not in PUBLIC_SUFFIXES else ""
    if labels[-1] in PUBLIC_SUFFIXES:
        return suffix
    return suffix


@dataclass(frozen=True)
class ScopeMatch:
    scope_state: str
    matched_anchor: str = ""
    match_kind: str = ""
    domain_authorized: bool = False
    reason: str = ""
    scope_mode: str = ""
    input_host: str = ""
    derived_scope_anchor: str = ""
    derivation_method: str = ""
    derivation_version: str = "1"
    explicit_narrowing: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_scope_host(value: object) -> str:
    """Return an ASCII hostname, or an empty string for invalid/IP values."""
    raw = str(value or "").strip().lower().rstrip(".")
    if raw.startswith("*."):
        raw = raw[2:]
    if not raw or ":" in raw:
        return ""
    try:
        ipaddress.ip_address(raw)
        return ""
    except ValueError:
        pass
    try:
        host = raw.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    if len(host) > 253 or "." not in host:
        return ""
    labels = host.split(".")
    if any(not _LABEL_RE.fullmatch(label) for label in labels):
        return ""
    return host


def is_public_suffix(value: object) -> bool:
    host = normalize_scope_host(value)
    return bool(host and host in PUBLIC_SUFFIXES)


def is_registrable_domain_anchor(value: object) -> bool:
    """Whether *value* is safe enough to be used as a domain anchor.

    This is intentionally conservative without a PSL dependency: known public
    suffixes are rejected, and a two-label anchor must end in a normal TLD.
    """
    host = normalize_scope_host(value)
    if not host or is_public_suffix(host):
        return False
    labels = host.split(".")
    if len(labels) < 2:
        return False
    return True


def host_within_anchor(host: object, anchor: object) -> bool:
    candidate = normalize_scope_host(host)
    root = normalize_scope_host(anchor)
    return bool(candidate and root and (candidate == root or candidate.endswith("." + root)))


def scope_entry_for_host(host: object, *, mode: str = "default_domain", source: str = "") -> dict[str, object]:
    """Build a scope entry from a user-supplied host and explicit scope mode."""
    normalized = normalize_scope_host(host)
    if mode not in {"default_domain", "exact", "explicit_domain", "wildcard"}:
        mode = "default_domain"
    anchor = normalized
    domain = mode in {"default_domain", "explicit_domain", "wildcard"}
    if mode in {"default_domain", "explicit_domain", "wildcard"}:
        anchor = registrable_parent(normalized)
        if not anchor:
            mode = "exact"
            domain = False
            anchor = normalized
    return {
        "host": anchor,
        "input_host": normalized,
        "domain_authorized": domain,
        "scope_mode": mode,
        "scope_anchor": anchor,
        "derived_scope_anchor": anchor if anchor != normalized else "",
        "scope_source": source,
        "explicit_narrowing": mode == "exact",
        "derivation_method": "conservative_registrable_parent" if anchor != normalized else "identity",
        "derivation_version": "1",
    }


def classify_host(host: object, entries: list[object] | tuple[object, ...] | set[object] | None,
                  *, exclusions: set[str] | None = None,
                  third_party: set[str] | None = None,
                  platform_shared: set[str] | None = None) -> ScopeMatch:
    """Classify a host against explicit scope entries.

    Entry forms accepted for compatibility:
    - ``"abc.com"``: exact host (no widening);
    - ``"*.abc.com"``: explicit wildcard/domain authorization;
    - ``{"host": "abc.com", "domain_authorized": True}``: domain anchor;
    - ``{"asset": "abc.com", "scope_state": "in_scope", ...}``.
    """
    candidate = normalize_scope_host(host)
    if not candidate:
        return ScopeMatch("invalid", reason="invalid, IP, or unsupported host")
    if candidate in {normalize_scope_host(x) for x in (exclusions or set())}:
        return ScopeMatch("out_of_scope", reason="explicit scope exclusion")
    if candidate in {normalize_scope_host(x) for x in (platform_shared or set())}:
        return ScopeMatch("platform_shared", reason="platform/shared host takes precedence")
    if candidate in {normalize_scope_host(x) for x in (third_party or set())}:
        return ScopeMatch("third_party", reason="third-party attribution takes precedence")

    matches: list[tuple[int, str, str, bool]] = []
    for entry in entries or ():
        if isinstance(entry, dict):
            raw = entry.get("host") or entry.get("asset") or entry.get("domain") or ""
            explicit_state = str(entry.get("scope_state") or "").strip()
            raw_domain = entry.get("domain_authorized")
            domain = (raw_domain is True or str(raw_domain).strip().lower() in {"1", "true", "yes"}) or str(entry.get("match_kind") or "").lower() in {"domain_suffix", "wildcard"}
            wildcard = str(raw).strip().startswith("*.") or str(entry.get("match_kind") or "").lower() == "wildcard"
            if explicit_state in {"third_party", "platform_shared", "out_of_scope"}:
                if normalize_scope_host(raw) == candidate:
                    return ScopeMatch(explicit_state, reason=f"explicit {explicit_state} entry")
        else:
            raw = entry
            domain = False
            wildcard = str(raw or "").strip().startswith("*.")
        anchor = normalize_scope_host(raw)
        if not anchor:
            continue
        if candidate == anchor:
            matches.append((len(anchor), anchor, "exact_host", domain or wildcard))
        elif (domain or wildcard) and is_registrable_domain_anchor(anchor) and candidate.endswith("." + anchor):
            matches.append((len(anchor), anchor, "wildcard" if wildcard else "domain_suffix", True))
    if not matches:
        return ScopeMatch("confirmation_required", reason="host is not covered by an explicit scope entry")
    _, anchor, kind, domain = max(matches, key=lambda row: row[0])
    return ScopeMatch("in_scope", anchor, kind, domain, f"matched explicit {kind} authorization for {anchor}")


def classify_scope_entry(host: object, *, domain_authorized: bool = False,
                         wildcard: bool = False) -> ScopeMatch:
    """Classify an initial scope entry without treating a child host as a root."""
    normalized = normalize_scope_host(host)
    if not normalized:
        return ScopeMatch("invalid", reason="invalid host")
    if wildcard:
        if not is_registrable_domain_anchor(normalized):
            return ScopeMatch("confirmation_required", reason="wildcard anchor is not a registrable domain")
        return ScopeMatch("in_scope", normalized, "wildcard", True, "explicit wildcard authorization")
    if domain_authorized:
        if not is_registrable_domain_anchor(normalized):
            return ScopeMatch("confirmation_required", reason="domain anchor is not a registrable domain")
        return ScopeMatch("in_scope", normalized, "domain_suffix", True, "explicit domain authorization")
    return ScopeMatch("confirmation_required", normalized, "exact_host", False, "exact host requires scope confirmation")


__all__ = [
    "ScopeMatch", "PUBLIC_SUFFIXES", "normalize_scope_host", "is_public_suffix",
    "is_registrable_domain_anchor", "host_within_anchor", "classify_host",
    "classify_scope_entry", "registrable_parent", "scope_entry_for_host",
]
