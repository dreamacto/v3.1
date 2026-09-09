import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from authenticated_session_review import approved_url, build_manual_auth_handoff, origin_of, run_authenticated_review


class AuthenticatedSessionReviewTests(unittest.TestCase):
    def test_handoff_detects_login_and_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "reports").mkdir()
            (run_dir / "fingerprints.jsonl").write_text(
                json.dumps({"url": "https://example.test", "categories": ["login"]}) + "\n",
                encoding="utf-8",
            )
            (run_dir / "api_candidates.jsonl").write_text(
                json.dumps({
                    "base_url": "https://example.test",
                    "url": "https://example.test/api/user/register",
                    "tags": ["api"],
                }) + "\n",
                encoding="utf-8",
            )
            result = build_manual_auth_handoff(run_dir)
            queue = json.loads((run_dir / "manual_auth_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(result["count"], 1)
            self.assertTrue(queue["items"][0]["registration_candidate"])

    def test_handoff_merges_wechat_login_domains(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            (run_dir / "fingerprints.jsonl").write_text("", encoding="utf-8")
            (run_dir / "api_candidates.jsonl").write_text("", encoding="utf-8")
            (run_dir / "api_discovery.jsonl").write_text("", encoding="utf-8")
            (run_dir / "wechat_auth_domains.json").write_text(json.dumps({"items": [{
                "base_url": "https://mini.hospital.test",
                "login_urls": ["https://mini.hospital.test/api/login"],
                "registration_candidate": False,
                "scope_state": "in_current_scope",
            }]}), encoding="utf-8")
            build_manual_auth_handoff(run_dir)
            queue = json.loads((run_dir / "manual_auth_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(queue["count"], 1)
            self.assertEqual(queue["items"][0]["host"], "mini.hospital.test")
            self.assertEqual(queue["items"][0]["scope_state"], "in_current_scope")

    def test_missing_or_unsuccessful_preflight_blocks_before_session_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            cookie_file = run_dir / "auth_sessions.local.json"
            cookie_file.write_text(json.dumps({"sessions": [{"base_url": "https://example.test", "cookie": "secret"}]}), encoding="utf-8")
            with patch("authenticated_session_review.load_sessions") as load, patch(
                "authenticated_session_review.run_authenticated_review_with_sessions"
            ) as review:
                result = run_authenticated_review(run_dir, cookie_file, 0, 5, 3, 5)
            self.assertEqual(result, {"status": "pending", "reason": "auth_preflight_missing", "credential_values_persisted": False})
            load.assert_not_called()
            review.assert_not_called()

            (run_dir / "auth_preflight.json").write_text(
                json.dumps({"status": "mcp_unavailable", "raw_history_persisted": False}), encoding="utf-8"
            )
            with patch("authenticated_session_review.load_sessions") as load, patch(
                "authenticated_session_review.run_authenticated_review_with_sessions"
            ) as review:
                result = run_authenticated_review(run_dir, cookie_file, 0, 5, 3, 5)
            self.assertEqual(result["reason"], "auth_preflight_not_found")
            load.assert_not_called()
            review.assert_not_called()

    def test_successful_preflight_forwards_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            cookie_file = run_dir / "auth_sessions.local.json"
            cookie_file.write_text(json.dumps({"sessions": []}), encoding="utf-8")
            (run_dir / "auth_preflight.json").write_text(
                json.dumps({"status": "found", "raw_history_persisted": False}), encoding="utf-8"
            )
            with patch("authenticated_session_review.load_sessions", return_value=[{"base_url": "https://example.test"}]) as load, patch(
                "authenticated_session_review.run_authenticated_review_with_sessions", return_value={"status": "complete"}
            ) as review:
                result = run_authenticated_review(run_dir, cookie_file, 3, 7, 2, 4)
            self.assertEqual(result, {"status": "complete"})
            load.assert_called_once_with(cookie_file)
            review.assert_called_once()
            self.assertEqual(review.call_args.kwargs["delay"], 3)
            self.assertEqual(review.call_args.kwargs["timeout"], 7)
            self.assertEqual(review.call_args.kwargs["max_js"], 2)
            self.assertEqual(review.call_args.kwargs["max_endpoints"], 4)

    def test_origin_validation_requires_http_scheme_exact_host_port_and_no_userinfo(self):
        allowed = {("https", "example.test", 443)}
        self.assertEqual(origin_of("https://example.test/path"), ("https", "example.test", 443))
        self.assertTrue(approved_url("https://example.test/api", allowed))
        for url in (
            "http://example.test/api",
            "https://example.test:8443/api",
            "https://sub.example.test/api",
            "https://user:pass@example.test/api",
            "file:///tmp/x",
            "//example.test/api",
        ):
            self.assertFalse(approved_url(url, allowed))

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "targets.json").write_text(json.dumps({
                "count": 1,
                "targets": [{"url": "https://example.test"}],
            }), encoding="utf-8")
            (run_dir / "api_candidates.jsonl").write_text("", encoding="utf-8")
            (run_dir / "auth_preflight.json").write_text(
                json.dumps({"status": "found", "raw_history_persisted": False}), encoding="utf-8"
            )
            cookie_file = run_dir / "auth_sessions.local.json"
            cookie_file.write_text(json.dumps({"sessions": [{
                "base_url": "https://example.test",
                "entry_url": "https://example.test/dashboard",
                "cookie": "SESSION=super-secret-cookie",
            }]}), encoding="utf-8")

            def fake_fetch(url, headers, timeout, max_bytes=131072):
                base = {
                    "checked_at": "now", "url": url, "status": 200, "final_url": url,
                    "content_type": "text/html", "declared_content_length": "", "sample_length": 10,
                    "sample_sha256": "abc", "elapsed_seconds": 0.01, "set_cookie_present": False, "error": "",
                }
                if url.endswith("/dashboard"):
                    return base, '<html><script src="/app.js"></script><h1>Dashboard</h1></html>'
                if url.endswith("/app.js"):
                    return base, 'const endpoint="/api/data/list";'
                base["content_type"] = "application/json"
                return base, json.dumps({"records": [{"realName": "private-value", "mobile": "13800000000"}]})

            with patch("authenticated_session_review.fetch_metadata", side_effect=fake_fetch), patch(
                "authenticated_session_review.time.sleep", return_value=None
            ):
                result = run_authenticated_review(run_dir, cookie_file, 0, 5, 3, 5)

            combined = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in run_dir.iterdir()
                if path.name not in {cookie_file.name, "targets.json"}
            )
            self.assertEqual(result["impact_count"], 1)
            self.assertNotIn("super-secret-cookie", combined)
            self.assertNotIn("private-value", combined)
            self.assertIn("realName", combined)
            self.assertIn("mobile", combined)


if __name__ == "__main__":
    unittest.main()
