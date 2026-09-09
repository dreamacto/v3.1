#!/usr/bin/env python3
"""Dump Burp MCP Server proxy history to a local file (read-only).

Talks only to the local Burp MCP extension (legacy SSE transport) — zero traffic
to any assessment target. Raw history contains cookies/tokens: the output file
belongs in restricted local storage (engagements/ or runs/, git-excluded) and
must never be committed, pasted, or summarized into reports/prompts.

Legacy SSE transport: JSON-RPC requests are POSTed to /?sessionId=<uuid> and the
server answers with 202 Accepted; the actual JSON-RPC responses arrive as events
on the open GET stream, matched by request id.

Per docs/BURP_MCP_USAGE.md section 4 (manual SSE handshake, mcporter fallback).

Usage:
  python scripts/burp_history_dump.py --tool get_proxy_http_history_regex \
      --arg count=300 --arg offset=0 --arg "regex=servicewechat" \
      --out engagements/<ws>/artifacts/raw/burp_wx_p0.json
"""
import argparse
import http.client
import json
import queue
import re
import sys
import threading


class SseTransport:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.responses = queue.Queue()
        self.session_id = None
        self.ready = threading.Event()

    def _reader(self):
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=600)
            conn.request("GET", "/", headers={"Accept": "text/event-stream"})
            resp = conn.getresponse()
        except OSError as e:
            print(f"ERROR: cannot reach Burp MCP at {self.host}:{self.port} ({e}); "
                  f"is Burp running with the MCP Server extension enabled?", file=sys.stderr)
            self.ready.set()
            return
        event_data = []
        while True:
            try:
                # read via the HTTPResponse wrapper so chunked transfer decoding applies;
                # resp.fp.readline() would expose raw chunk framing and corrupt large events
                raw = resp.readline()
            except (OSError, http.client.HTTPException):
                break
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line == "":
                if event_data:
                    payload = "\n".join(event_data)
                    event_data = []
                    m = re.search(r"[?&]sessionId=([A-Za-z0-9\-]+)", payload)
                    if m and not self.session_id:
                        self.session_id = m.group(1)
                        self.ready.set()
                        continue
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict) and ("id" in obj or "method" in obj):
                        self.responses.put(obj)
                continue
            if line.startswith("data:"):
                event_data.append(line[5:].lstrip())

    def start(self):
        threading.Thread(target=self._reader, daemon=True).start()
        return self.ready.wait(15) and self.session_id is not None

    def call(self, method, params, req_id, timeout=300):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if req_id is not None:
            payload["id"] = req_id
        conn = http.client.HTTPConnection(self.host, self.port, timeout=120)
        conn.request("POST", f"/?sessionId={self.session_id}", body=json.dumps(payload),
                     headers={"Content-Type": "application/json",
                              "Accept": "application/json, text/event-stream"})
        resp = conn.getresponse()
        resp.read()
        if resp.status not in (200, 202):
            raise RuntimeError(f"POST {method} -> HTTP {resp.status}")
        if req_id is None:
            return None
        while True:
            obj = self.responses.get(timeout=timeout)
            if obj.get("id") == req_id:
                if "error" in obj:
                    raise RuntimeError(f"{method} JSON-RPC error: {obj['error']}")
                return obj.get("result", {})


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9876)
    ap.add_argument("--tool", required=True,
                    help="e.g. get_proxy_http_history / get_proxy_http_history_regex")
    ap.add_argument("--arg", action="append", default=[],
                    help="tool argument key=value (repeatable; digits become ints)")
    ap.add_argument("--out", required=True, help="output file (restricted local storage)")
    a = ap.parse_args()

    t = SseTransport(a.host, a.port)
    if not t.start():
        print("ERROR: no sessionId received from SSE stream", file=sys.stderr)
        sys.exit(2)

    t.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "burp-history-dump", "version": "1.0"}}, 1)
    t.call("notifications/initialized", {}, None)

    args = {}
    for kv in a.arg:
        k, v = kv.split("=", 1)
        args[k] = int(v) if re.fullmatch(r"\d+", v) else v
    result = t.call("tools/call", {"name": a.tool, "arguments": args}, 2)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    is_err = result.get("isError")
    texts = result.get("content", [])
    total = sum(len(x.get("text", "")) for x in texts if isinstance(x, dict))
    print(f"saved {len(json.dumps(result, ensure_ascii=False))} bytes "
          f"({len(texts)} content parts, {total} text chars) -> {a.out} (isError={is_err})")


if __name__ == "__main__":
    main()
