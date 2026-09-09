import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import metrics_weekly


class MetricsLineageTests(unittest.TestCase):
    def test_same_dedup_key_counts_latest_run_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("run_a", "run_b"):
                d = root / name
                d.mkdir()
                (d / "candidates.jsonl").write_text('{"candidate":1}\n', encoding="utf-8")
                (d / "run_summary.json").write_text(json.dumps({"dedup_key": "same", "run_id": name}), encoding="utf-8")
            runs, incomplete = metrics_weekly.scan_runs(root, 99999, datetime.now(timezone.utc).astimezone(metrics_weekly.CST))
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["dir"], "run_b")
            self.assertEqual(incomplete, [])

    def test_scan_engagements_reads_deep_snapshot_and_normalizes_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "engagements"
            d = root / "site-a"
            (d / "notes").mkdir(parents=True)
            (d / "evidence" / "redacted").mkdir(parents=True)
            (d / "engagement.json").write_text("{}", encoding="utf-8")
            (d / "phase_status.json").write_text(json.dumps({"current_phase":"api", "next_phase":"review", "phases":[{"phase":"api","status":"complete"}]}), encoding="utf-8")
            (d / "phase_status.miniapp.json").write_text(json.dumps({"current_phase":"inventory", "phases":[{"phase":"inventory","status":"blocked","reason":"材料不足"}]}), encoding="utf-8")
            (d / "notes" / "target-model.md").write_text("# Host map\n## Coverage\n", encoding="utf-8")
            (d / "evidence" / "redacted" / "e1.json").write_text("{}", encoding="utf-8")
            (d / "evidence" / "index.csv").write_text("evidence_id,finding_id,captured_at,sha256,sensitivity,redacted_path\nEV1,F1,2026-09-03T00:00:00+00:00,abc,report_eligible,evidence/redacted/e1.json\nEV2,F2,,,restricted_local_only,evidence/raw/e2.body\n", encoding="utf-8")
            (d / "review_ledger.csv").write_text("item_id,status,updated_at\nL1,confirmed,2026-09-03T00:00:00+00:00\nL2,rejected,2026-09-03T00:00:00+00:00\nL3,candidate,2026-09-03T00:00:00+00:00\nL4,signal,2026-09-03T00:00:00+00:00\nL5,approval_required,2026-09-03T00:00:00+00:00\n", encoding="utf-8")
            now = datetime(2026, 9, 3, tzinfo=metrics_weekly.CST)
            stats = metrics_weekly.collect_engagements(root, 7, now)
            self.assertEqual(stats["dirs"], 1)
            self.assertEqual(stats["ledger_rows"], 5)
            self.assertEqual(stats["updated_rows"], 5)
            self.assertEqual(stats["by_status"]["confirmed"], 1)
            self.assertEqual(stats["by_status"]["rejected"], 1)
            self.assertEqual(stats["by_status"]["open"], 2)
            self.assertEqual(stats["by_status"]["blocked"], 1)
            record = stats["records"][0]
            self.assertEqual(record["phases"]["wz"]["current_phase"], "api")
            self.assertEqual(record["phases"]["xcx"]["counts"]["blocked"], 1)
            self.assertEqual(record["meta"]["target_model"]["sections"], 2)
            self.assertEqual(record["meta"]["evidence"]["report_eligible_count"], 1)

    def test_scan_engagements_excludes_shared_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            (root / "evidence" / "review_ledger.csv").write_text("item_id,status\nX,confirmed\n", encoding="utf-8")
            self.assertEqual(metrics_weekly.scan_engagements(root, 99999, datetime.now(metrics_weekly.CST)), [])

    def test_weekly_sweep_writes_engagement_cursor_and_report(self):
        import weekly_sweep
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            engagements = root / "engagements"
            kb = root / "kb"
            reports = root / "reports"
            (runs / "r1").mkdir(parents=True)
            (runs / "r1" / "run_summary.json").write_text("{}", encoding="utf-8")
            (engagements / "site-a").mkdir(parents=True)
            (engagements / "site-a" / "engagement.json").write_text("{}", encoding="utf-8")
            (engagements / "site-a" / "review_ledger.csv").write_text("item_id,status,updated_at\nL1,confirmed,2026-09-03T00:00:00+00:00\n", encoding="utf-8")
            old_root = weekly_sweep.ROOT
            weekly_sweep.ROOT = root
            try:
                result = weekly_sweep.sweep(99999, "runs", "engagements", "kb", "reports")
            finally:
                weekly_sweep.ROOT = old_root
            cursor = json.loads((kb / "last_sweep.json").read_text(encoding="utf-8"))
            self.assertEqual(cursor["runs_scanned"], 1)
            self.assertEqual(cursor["engagements_scanned"], 1)
            self.assertEqual(cursor["engagement_rows_covered"]["site-a"], 1)
            self.assertTrue(Path(result["report"]).is_file())
            self.assertIn("engagements/", Path(result["report"]).read_text(encoding="utf-8"))

    def test_legacy_runs_remain_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("run_a", "run_b"):
                d = root / name
                d.mkdir()
                (d / "run_summary.json").write_text("{}", encoding="utf-8")
            runs, _ = metrics_weekly.scan_runs(root, 99999, datetime.now(timezone.utc).astimezone(metrics_weekly.CST))
            self.assertEqual(len(runs), 2)

    def test_status_bucket_keeps_open_states_out_of_terminal_counts(self):
        self.assertEqual(metrics_weekly._status_bucket("candidate"), "open")
        self.assertEqual(metrics_weekly._status_bucket("needs_manual_validation"), "open")
        self.assertEqual(metrics_weekly._status_bucket("signal"), "open")
        self.assertEqual(metrics_weekly._status_bucket("rejected"), "rejected")


if __name__ == "__main__":
    unittest.main()
