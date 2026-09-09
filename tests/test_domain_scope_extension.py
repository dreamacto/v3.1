from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_wz_append_subdomain_requires_confirmed_domain_anchor(tmp_path):
    mod = load("wz_scope_extension_test", ROOT / ".agents/skills/wz/scripts/init_engagement.py")
    path = tmp_path / "scope.csv"
    fields = list(mod.SCOPE_FIELDS)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        row = {field: "" for field in fields}
        row.update({"asset": "abc.com", "scope_state": "in_scope", "domain_authorized": "true"})
        writer.writerow(row)
    assert mod.append_domain_authorized_subdomain(path, "123.abc.com")
    assert not mod.append_domain_authorized_subdomain(path, "123.abc.com")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    child = next(row for row in rows if row["asset"] == "123.abc.com")
    assert child["scope_state"] == "in_scope"
    assert child["matched_scope_anchor"] == "abc.com"
    assert child["source"] == "domain_authorized_subdomain"
    assert not mod.append_domain_authorized_subdomain(path, "evilabc.com")


def test_xcx_append_subdomain_requires_confirmed_domain_anchor(tmp_path):
    mod = load("xcx_scope_extension_test", ROOT / ".agents/skills/xcx/scripts/init_miniapp_engagement.py")
    path = tmp_path / "hosts.csv"
    fields = list(mod.HOST_FIELDS)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        row = {field: "" for field in fields}
        row.update({"host": "abc.com", "scope_state": "in_scope", "domain_authorized": "true"})
        writer.writerow(row)
    assert mod.append_domain_authorized_host(path, "123.abc.com")
    assert not mod.append_domain_authorized_host(path, "123.abc.com")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    child = next(row for row in rows if row["host"] == "123.abc.com")
    assert child["scope_state"] == "in_scope"
    assert child["matched_scope_anchor"] == "abc.com"
    assert not mod.append_domain_authorized_host(path, "abc.com.evil.com")
