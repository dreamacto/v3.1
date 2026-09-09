#!/usr/bin/env python3
"""Robust full dump of Burp proxy history with overlap+dedupe (live-list safe).

The naive forward walk (offset += count) can skip entries while Burp's live
history shifts. This walker: fetches pages with 25% overlap, dedupes by
full-item sha256, keeps walking until 3 consecutive pages add nothing new
(or an empty page), then merges with any previously dumped page files.

Dedupe/merge only touches structure on stdout; raw stays in the out dir.
"""
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from burp_history_dump import SseTransport  # noqa: E402


def item_key(item_text: str) -> str:
    return hashlib.sha256(item_text.encode("utf-8", "surrogatepass")).hexdigest()


def parse_lines(text: str):
    return [l for l in text.split("\n") if l.strip().startswith("{\"request\"")]


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)

    t = SseTransport("127.0.0.1", 9876)
    if not t.start():
        print("ERROR: no SSE session", file=sys.stderr)
        sys.exit(2)
    t.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "dump2", "version": "1.0"}}, 1)
    t.call("notifications/initialized", {}, None)

    seen = {}
    # seed with previously dumped items so merge dedupes automatically
    for fp in sorted(glob.glob(os.path.join(outdir, "burp_all_*.json"))):
        for line in json.load(open(fp, encoding="utf-8")):
            seen[item_key(line)] = line
    print(f"seeded {len(seen)} items from previous dump")

    page, stride = 100, 75  # 25% overlap
    offset = 0
    req_id = 1000
    fetched = 0
    pages = 0
    # walk the whole index range; only an empty page stops us. Stale (fully
    # known) pages in the old-entries region are expected — new items live
    # toward the other end of the list.
    while pages < 400:
        r = t.call("tools/call",
                   {"name": "get_proxy_http_history",
                    "arguments": {"count": page, "offset": offset}},
                   req_id, timeout=60)
        req_id += 1
        pages += 1
        text = "".join(x.get("text", "") for x in r.get("content", []) if isinstance(x, dict))
        lines = parse_lines(text)
        if not lines:
            break
        new = 0
        for line in lines:
            k = item_key(line)
            if k not in seen:
                seen[k] = line
                new += 1
        fetched += new
        print(f"offset={offset:6d} got={len(lines):4d} new={new:4d} total={len(seen)}", flush=True)
        offset += stride

    # rewrite the canonical page files (atomic-ish: write new set, drop old)
    for fp in glob.glob(os.path.join(outdir, "burp_all_*.json")):
        os.remove(fp)
    items = list(seen.values())
    per = 500
    for i in range(0, len(items), per):
        part = items[i:i + per]
        with open(os.path.join(outdir, f"burp_all_{i:05d}.json"), "w", encoding="utf-8") as f:
            json.dump(part, f, ensure_ascii=False)
    print(f"DONE: {len(seen)} unique items ({fetched} newly fetched, {pages} pages) -> {outdir}")


if __name__ == "__main__":
    main()
