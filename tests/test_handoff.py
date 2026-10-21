"""Synthetic, offline contract tests; none inspect a real host or broker."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from epiphany_trace import Record, TraceStore
from epiphany_trace.handoff import (
    MAX_BYTES, assess_report, import_report, load_report, main, validate_report,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/observer_health.synthetic.json"
NOW = "2026-01-01T15:00:30Z"


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads(EXAMPLE.read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = TraceStore(self.root / "trace.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def load(self, raw):
        path = self.root / "packet.json"
        path.write_bytes(raw if isinstance(raw, bytes) else raw.encode())
        return load_report(path)

    def test_valid_packet_detached_from_input(self):
        validated = validate_report(self.packet)
        self.packet["evidence"]["process_state"] = "stopped"
        self.assertEqual(validated["evidence"]["process_state"], "running")

    def test_top_level_private_fields_rejected(self):
        for key in ("accounts", "token", "hostname", "command", "raw_log"):
            with self.subTest(key=key):
                report = deepcopy(self.packet)
                report[key] = "private-value"
                with self.assertRaises(ValueError):
                    validate_report(report)

    def test_nested_private_fields_rejected(self):
        self.packet["evidence"]["cash"] = 42
        with self.assertRaises(ValueError):
            validate_report(self.packet)

    def test_missing_fields_rejected(self):
        del self.packet["evidence"]["heartbeat_at"]
        with self.assertRaises(ValueError):
            validate_report(self.packet)

    def test_wrong_shapes_rejected(self):
        for report in (None, [], "not a packet", 1):
            with self.subTest(report=report), self.assertRaises(ValueError):
                validate_report(report)

    def test_invalid_schema_subject_and_producer_rejected(self):
        for key, value in (("schema", "v2"), ("subject", "other"), ("producer", "unknown")):
            with self.subTest(key=key):
                report = deepcopy(self.packet)
                report[key] = value
                with self.assertRaises(ValueError):
                    validate_report(report)

    def test_report_id_is_not_a_free_text_channel(self):
        for value in ("machine-name", None, 1, "00000000000040008000000000000001"):
            with self.subTest(value=value):
                self.packet["report_id"] = value
                with self.assertRaises(ValueError):
                    validate_report(self.packet)

    def test_naive_and_invalid_timestamps_rejected(self):
        for value in ("2026-01-01T15:00:00", "2026-02-30T15:00:00Z", "now", None):
            with self.subTest(value=value):
                self.packet["observed_at"] = value
                with self.assertRaises(ValueError):
                    validate_report(self.packet)

    def test_evidence_cannot_postdate_observation(self):
        self.packet["evidence"]["heartbeat_at"] = "2026-01-01T15:00:01Z"
        with self.assertRaises(ValueError):
            validate_report(self.packet)

    def test_consumer_rejects_future_report(self):
        with self.assertRaises(ValueError):
            assess_report(self.packet, received_at="2026-01-01T14:00:00Z")
        with self.assertRaises(ValueError):
            import_report(self.store, self.packet, received_at="2026-01-01T14:00:00Z")
        with self.assertRaises(KeyError):
            self.store.get("health:" + self.packet["report_id"])

    def test_offsets_compared_as_instants(self):
        self.packet["observed_at"] = "2026-01-01T10:00:00-05:00"
        result = assess_report(self.packet, received_at=NOW)
        self.assertEqual(result["report_age_seconds"], 30)

    def test_duplicate_json_keys_rejected_at_any_depth(self):
        for raw in ('{"schema":1,"schema":2}', '{"evidence":{"phase":1,"phase":2}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.load(raw)

    def test_oversize_and_malformed_json_rejected(self):
        for raw in (b" " * (MAX_BYTES + 1), b"\xff", b"{", b"[" * 1200):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                self.load(raw)

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            self.load('{"value":NaN}')

    def test_unknown_states_are_not_healthy(self):
        e = self.packet["evidence"]
        e.update(process_state="unknown", task_state="unknown", phase="unknown",
                 heartbeat_at=None, last_collection_at=None, last_collection_result="unknown",
                 consecutive_failures=None, stop_requested=None)
        result = assess_report(self.packet, received_at=NOW)
        self.assertIn("process_unknown", result["flags"])
        self.assertIn("heartbeat_unknown", result["flags"])
        self.assertIn("collection_unknown", result["flags"])
        self.assertNotIn("healthy", result)

    def test_bool_is_not_failure_count(self):
        for value in (True, -1, 1.5, "0", 1_000_001):
            with self.subTest(value=value):
                self.packet["evidence"]["consecutive_failures"] = value
                with self.assertRaises(ValueError):
                    validate_report(self.packet)

    def test_stop_flag_must_be_bool_or_null(self):
        self.packet["evidence"]["stop_requested"] = 0
        with self.assertRaises(ValueError):
            validate_report(self.packet)

    def test_collection_result_requires_time(self):
        self.packet["evidence"]["last_collection_at"] = None
        with self.assertRaises(ValueError):
            validate_report(self.packet)

    def test_fresh_packet_not_authenticated(self):
        result = assess_report(self.packet, received_at=NOW)
        self.assertEqual(result["flags"], [])
        self.assertEqual(result["heartbeat_age_seconds"], 32)
        self.assertIn("not authenticated", result["provenance"])
        self.assertNotIn("healthy", result)

    def test_freshness_uses_receiver_time(self):
        result = assess_report(self.packet, received_at="2026-01-01T16:00:00Z")
        self.assertIn("report_stale", result["flags"])
        self.assertIn("heartbeat_stale", result["flags"])
        self.assertEqual(result["heartbeat_age_seconds"], 3602)

    def test_new_wrapper_does_not_refresh_old_heartbeat(self):
        self.packet["observed_at"] = "2026-01-01T16:00:00Z"
        result = assess_report(self.packet, received_at="2026-01-01T16:00:01Z")
        self.assertNotIn("report_stale", result["flags"])
        self.assertIn("heartbeat_stale", result["flags"])

    def test_waiting_window_does_not_imply_collection_failure(self):
        self.packet["evidence"]["phase"] = "waiting_for_clock_window"
        self.packet["evidence"]["last_collection_at"] = "2025-12-31T20:00:00Z"
        result = assess_report(self.packet, received_at=NOW)
        self.assertEqual(result["flags"], [])
        self.assertGreater(result["collection_age_seconds"], 300)

    def test_failure_and_stop_remain_visible_with_fresh_heartbeat(self):
        self.packet["evidence"].update(last_collection_result="failure",
                                       consecutive_failures=2, stop_requested=True)
        result = assess_report(self.packet, received_at=NOW)
        self.assertIn("collection_failure", result["flags"])
        self.assertIn("reported_failures", result["flags"])
        self.assertIn("stop_requested", result["flags"])

    def test_invalid_age_budget_rejected(self):
        for value in (True, 0, -1, 86_401):
            with self.subTest(value=value), self.assertRaises(ValueError):
                assess_report(self.packet, received_at=NOW, max_age_seconds=value)

    def test_import_and_replay_are_idempotent(self):
        first, inserted = import_report(self.store, self.packet, received_at=NOW)
        second, repeated = import_report(self.store, self.packet, received_at=NOW)
        self.assertTrue(inserted)
        self.assertFalse(repeated)
        self.assertEqual(first, second)
        self.assertTrue(first.source_ref.startswith("handoff:sha256:"))

    def test_reordered_json_is_same_record(self):
        first, _ = import_report(self.store, self.packet, received_at=NOW)
        reordered = dict(reversed(list(self.packet.items())))
        second, inserted = import_report(self.store, reordered, received_at=NOW)
        self.assertEqual(first, second)
        self.assertFalse(inserted)

    def test_same_id_different_payload_fails_without_overwrite(self):
        first, _ = import_report(self.store, self.packet, received_at=NOW)
        self.packet["evidence"]["process_state"] = "stopped"
        with self.assertRaises(ValueError):
            import_report(self.store, self.packet, received_at=NOW)
        self.assertEqual(self.store.get(first.event_id), first)

    def test_linked_later_report_and_inference_preserve_source(self):
        first, _ = import_report(self.store, self.packet, received_at=NOW)
        self.packet["report_id"] = "00000000-0000-4000-8000-000000000002"
        self.packet["observed_at"] = "2026-01-01T15:00:20Z"
        later, _ = import_report(self.store, self.packet, received_at=NOW,
                                 parent_ids=(first.event_id,))
        interpretation = Record("analysis", NOW, "inference", "test-consumer",
                                "Synthetic interpretation, not a new host observation", (later.event_id,))
        self.store.add(interpretation)
        self.assertEqual([r.event_id for r in self.store.ancestors("analysis")],
                         [first.event_id, later.event_id])
        self.assertEqual(self.store.get(first.event_id), first)

    def test_extreme_timestamp_overflow_is_validation_error(self):
        self.packet["observed_at"] = "0001-01-01T00:00:00+23:59"
        with self.assertRaises(ValueError):
            validate_report(self.packet)

    def test_empty_receipt_timestamp_is_not_current_time(self):
        with self.assertRaises(ValueError):
            assess_report(self.packet, received_at="")

    def test_same_id_changed_ancestry_rejected(self):
        first, _ = import_report(self.store, self.packet, received_at=NOW)
        with self.assertRaises(ValueError):
            import_report(self.store, self.packet, received_at=NOW, parent_ids=("different",))
        self.assertEqual(self.store.get(first.event_id), first)

    def test_cli_refuses_symlinked_local_directory(self):
        destination = self.root / "outside"
        destination.mkdir()
        try:
            (self.root / ".local").symlink_to(destination, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable in this environment")
        old = Path.cwd()
        try:
            os.chdir(self.root)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(EXAMPLE), "--save"]), 2)
        finally:
            os.chdir(old)
        self.assertEqual(list(destination.iterdir()), [])

    def test_cli_is_read_only_by_default(self):
        old = Path.cwd()
        output = io.StringIO()
        try:
            os.chdir(self.root)
            with redirect_stdout(output):
                code = main([str(EXAMPLE)])
        finally:
            os.chdir(old)
        self.assertEqual(code, 0)
        self.assertFalse((self.root / ".local").exists())
        self.assertIn("provenance", json.loads(output.getvalue()))

    def test_cli_save_and_replay_use_separate_ledger(self):
        old = Path.cwd()
        outputs = []
        try:
            os.chdir(self.root)
            for _ in range(2):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main([str(EXAMPLE), "--save"]), 0)
                outputs.append(json.loads(output.getvalue())["receipt"])
        finally:
            os.chdir(old)
        self.assertEqual(outputs, ["inserted", "already_present"])
        self.assertTrue((self.root / ".local/epiphany_handoff.sqlite3").exists())

    def test_cli_invalid_packet_no_database_and_no_secret_echo(self):
        packet = self.root / "invalid.json"
        packet.write_text('{"secret":"sensitive-test-value"}')
        old = Path.cwd()
        errors = io.StringIO()
        try:
            os.chdir(self.root)
            with redirect_stderr(errors):
                self.assertEqual(main([str(packet), "--save"]), 2)
        finally:
            os.chdir(old)
        self.assertNotIn("sensitive-test-value", errors.getvalue())
        self.assertFalse((self.root / ".local").exists())

    def test_cli_refuses_unrelated_database(self):
        local = self.root / ".local"
        local.mkdir()
        with sqlite3.connect(local / "epiphany_handoff.sqlite3") as connection:
            connection.execute("CREATE TABLE unrelated (id INTEGER)")
        old = Path.cwd()
        try:
            os.chdir(self.root)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(EXAMPLE), "--save"]), 2)
        finally:
            os.chdir(old)
        with sqlite3.connect(local / "epiphany_handoff.sqlite3") as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(names, {"unrelated"})


if __name__ == "__main__":
    unittest.main()
