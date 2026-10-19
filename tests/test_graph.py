import tempfile
import unittest
from pathlib import Path

from epiphany_trace import Record, TraceStore


class TraceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "trace.db"
        self.store = TraceStore(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def put(self, ident, kind="observation", parents=(), source=None, at="2026-10-18T10:00:00-04:00"):
        if kind == "observation" and source is None:
            source = f"example:{ident}"
        item = Record(ident, at, kind, "test-actor", ident, tuple(parents), source)
        self.store.add(item)
        return item

    def test_bidirectional_lineage_and_revision_retention(self):
        self.put("initial")
        self.put("hypothesis", "inference", ["initial"], at="2026-10-18T10:01:00-04:00")
        self.put("correction", "revision", ["hypothesis"], at="2026-10-18T10:02:00-04:00")
        self.assertEqual([r.event_id for r in self.store.ancestors("correction")], ["initial", "hypothesis"])
        self.assertEqual([r.event_id for r in self.store.descendants("initial")], ["hypothesis", "correction"])
        self.assertEqual(self.store.get("hypothesis").statement, "hypothesis")

    def test_duplicate_references_are_not_independent_confirmations(self):
        self.put("quote-a", source="archive:one")
        self.put("quote-b", source="archive:one")
        self.put("conclusion", "inference", ["quote-a", "quote-b"])
        self.assertEqual(self.store.independent_source_refs("conclusion"), frozenset({"archive:one"}))

    def test_distinct_sources_remain_distinct(self):
        self.put("a", source="archive:one")
        self.put("b", source="archive:two")
        self.put("c", "inference", ["a", "b"])
        self.assertEqual(len(self.store.independent_source_refs("c")), 2)

    def test_records_survive_restart(self):
        original = self.put("persisted")
        self.store.close()
        self.store = TraceStore(self.path)
        self.assertEqual(self.store.get("persisted"), original)

    def test_missing_parent_fails_closed(self):
        with self.assertRaises(KeyError):
            self.put("unsupported", "inference", ["missing"])
        with self.assertRaises(KeyError):
            self.store.get("unsupported")

    def test_future_parent_is_rejected(self):
        self.put("later", at="2026-10-18T11:00:00-04:00")
        with self.assertRaises(ValueError):
            self.put("earlier", "inference", ["later"], at="2026-10-18T10:00:00-04:00")

    def test_missing_timezone_rejected(self):
        with self.assertRaises(ValueError):
            self.put("no-zone", at="2026-10-18T10:00:00")

    def test_derived_record_must_reference_prior_event(self):
        with self.assertRaises(ValueError):
            self.put("orphan", "inference")

    def test_observation_requires_source(self):
        with self.assertRaises(ValueError):
            self.store.add(Record("bad", "2026-10-18T10:00:00Z", "observation", "test", "value"))

    def test_derived_cannot_masquerade_as_external_source(self):
        self.put("original")
        with self.assertRaises(ValueError):
            self.store.add(Record("echo", "2026-10-18T10:00:01Z", "inference", "test", "echo", ("original",), "independent"))

    def test_duplicate_record_id_not_overwritten(self):
        self.put("a")
        with self.assertRaises(Exception):
            self.put("a")
        self.assertEqual(self.store.get("a").statement, "a")


if __name__ == "__main__":
    unittest.main()
