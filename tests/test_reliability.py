"""Regression checks using temporary databases and controlled model failures.

Run on Windows with: python -m unittest discover -s tests -v
"""

import copy
import json
import logging
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from TimeIndex.db.vector_store import TimeIndexStore, VectorStore
from TimeIndex.daemon.daemon import Daemon
from TimeIndex.daemon.llm_processor import LLMProcessor
from TimeIndex.daemon.wmi_monitor import ProcessEvent, SystemSnapshot, WindowInfo, WmiCollector


class StorageReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="timeindex-tests-")
        self.store = VectorStore(db_path=self.directory.name)
        self.record = {
            "id": "1791353724.167714",
            "timestamp": "2026-10-07T14:15:24.167714",
            "summary": "Python functions",
            "tags": ["coding"],
            "primary_app": "Code",
            "active_windows": [{"title": "Python functions - Code", "pid": 10}],
            "process_events": [{"process": "code.exe", "type": "created"}],
            "hardware": {"cpu_percent": 12},
            "vector": [0.25] * 768,
        }

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def rows(self):
        return {row["id"]: row for row in self.store.get_table().to_arrow().to_pylist()}

    def test_partial_update_preserves_vector_and_evidence(self):
        self.store.add(self.record)
        before = self.rows()[self.record["id"]]
        self.assertTrue(self.store.update({
            "id": self.record["id"], "refined_tags": ["coding", "python"],
            "refined_summary": "Writing Python functions", "cluster_id": "coding-1",
        }))
        after = self.rows()[self.record["id"]]
        for field in ("vector", "summary", "tags", "active_windows", "process_events", "hardware", "timestamp"):
            self.assertEqual(before[field], after[field], field)
        self.assertEqual(after["refined_tags"], ["coding", "python"])

    def test_pending_records_preserve_vector_and_normalize_lists_and_nulls(self):
        self.store.add(self.record)
        pending = self.store.get_pending_retag_records()[0]
        self.assertEqual(pending["vector"], self.record["vector"])
        self.assertIsInstance(pending["tags"], list)
        self.assertIsInstance(pending["active_windows"], list)
        for field in ("refined_tags", "refined_summary", "cluster_id"):
            self.assertIsNone(pending[field])

    def test_pending_batches_continue_beyond_first_ten_records(self):
        self.store.add_batch([{**self.record, "id": str(index)} for index in range(25)])
        self.assertEqual(self.store.get_record_count(), 25)
        batch = self.store.get_pending_retag_records(20)
        self.assertEqual(len(batch), 20)
        self.store.update_batch([
            {"id": row["id"], "refined_tags": ["coding"], "refined_summary": "Python", "cluster_id": "a"}
            for row in batch
        ])
        self.assertEqual(len(self.store.get_pending_retag_records(20)), 5)

    def test_missing_vector_can_be_saved_and_is_excluded_from_vector_search(self):
        self.store.add(self.record)
        for name, vector in (("empty", []), ("null", None)):
            self.store.add({**self.record, "id": name, "vector": vector})
        without = {key: value for key, value in self.record.items() if key != "vector"}
        self.store.add({**without, "id": "missing"})
        for name in ("empty", "null", "missing"):
            self.assertIsNone(self.rows()[name]["vector"])
        results = self.store.semantic_search("Python", query_vector=[0.25] * 768, limit=20)
        self.assertEqual([row["id"] for row in results], [self.record["id"]])

    def test_bad_vector_update_preserves_existing_record(self):
        self.store.add(self.record)
        before = self.rows()
        for vector in ([1.0], [float("nan")] * 768, [float("inf")] * 768):
            with self.assertRaises(ValueError):
                self.store.update({"id": self.record["id"], "summary": "changed", "vector": vector})
            self.assertEqual(self.rows(), before)

    def test_database_update_failure_preserves_existing_record(self):
        self.store.add(self.record)
        before = self.rows()
        table = self.store.get_table()
        with patch.object(table, "update", side_effect=RuntimeError("simulated write failure")):
            with self.assertRaises(RuntimeError):
                self.store.update({"id": self.record["id"], "refined_summary": "changed"})
        self.assertEqual(self.rows(), before)

    def test_missing_id_does_not_create_a_record(self):
        self.store.add(self.record)
        self.assertFalse(self.store.update({"id": "missing", "summary": "unused"}))
        self.assertEqual(self.store.get_record_count(), 1)

    def test_quoted_id_updates_only_the_matching_row(self):
        quoted = "a' OR true --"
        self.store.add_batch([self.record, {**self.record, "id": quoted}])
        self.assertTrue(self.store.update({"id": quoted, "refined_summary": "changed"}))
        self.assertIsNone(self.rows()[self.record["id"]]["refined_summary"])
        self.assertEqual(self.rows()[quoted]["refined_summary"], "changed")

    def test_retag_write_only_changes_refinement_fields(self):
        self.store.add(self.record)
        before = self.rows()[self.record["id"]]
        wrapper = TimeIndexStore.__new__(TimeIndexStore)
        wrapper._store = self.store
        count = wrapper.update_retag_records([{
            **self.record, "vector": [0.0] * 768, "summary": "untrusted replacement",
            "refined_tags": ["coding"], "refined_summary": "Python", "cluster_id": "a",
        }])
        self.assertEqual(count, 1)
        after = self.rows()[self.record["id"]]
        self.assertEqual(after["vector"], before["vector"])
        self.assertEqual(after["summary"], before["summary"])


class RetagMatchingTests(unittest.TestCase):
    def setUp(self):
        self.processor = LLMProcessor.__new__(LLMProcessor)
        self.records = [{"id": "1791353724.167714", "summary": "original", "tags": ["coding"], "refined_tags": None}]

    @staticmethod
    def answer(record_id):
        return {"id": record_id, "refined_tags": ["coding"], "refined_summary": "Python functions", "cluster_id": "a"}

    def test_numeric_timestamp_matches_without_precision_loss(self):
        content = '[{"id":1791353724.167714,"refined_tags":["coding"],"refined_summary":"Python","cluster_id":"a"}]'
        result = self.processor._parse_retag_response(content, self.records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], self.records[0]["id"])

    def test_integer_id_matches_text(self):
        result = self.processor._parse_retag_response(json.dumps([self.answer(123)]), [{"id": "123"}])
        self.assertEqual(result[0]["id"], "123")

    def test_fenced_and_prefixed_arrays_match_all_records(self):
        records = self.records + [{"id": "second"}]
        answer = json.dumps([self.answer(row["id"]) for row in records])
        for content in (answer, "```json\n" + answer + "\n```", "Results:\n" + answer + "\nDone."):
            with self.subTest(content=content[:20]):
                self.assertEqual(len(self.processor._parse_retag_response(content, records)), 2)

    def test_backticks_inside_valid_json_are_preserved(self):
        answer = {**self.answer(self.records[0]["id"]), "refined_summary": "Writing ```Python``` functions"}
        result = self.processor._parse_retag_response(json.dumps([answer]), self.records)
        self.assertEqual(result[0]["refined_summary"], answer["refined_summary"])

    def test_partial_response_only_returns_valid_matches_without_mutating_input(self):
        records = self.records + [{"id": "second"}]
        before = copy.deepcopy(records)
        bad = {**self.answer("second"), "refined_summary": "NaN", "refined_tags": None}
        result = self.processor._parse_retag_response(json.dumps([self.answer(records[0]["id"]), bad, self.answer("unknown")]), records)
        self.assertEqual(len(result), 1)
        self.assertEqual(records, before)

    def test_duplicate_results_are_not_applied(self):
        answer = self.answer(self.records[0]["id"])
        self.assertEqual(self.processor._parse_retag_response(json.dumps([answer, answer]), self.records), [])

    def test_ambiguous_numeric_ids_are_not_applied(self):
        self.assertEqual(self.processor._parse_retag_response(json.dumps([self.answer(1)]), [{"id": "01"}, {"id": "1.0"}]), [])

    def test_invalid_reply_and_malformed_fields_are_not_applied(self):
        for content in ("{}", "not json", "[{", json.dumps([self.answer(True)])):
            self.assertEqual(self.processor._parse_retag_response(content, self.records), [])
        for field, value in (("refined_tags", []), ("refined_tags", "coding"), ("refined_summary", ""), ("cluster_id", None)):
            answer = {**self.answer(self.records[0]["id"]), field: value}
            self.assertEqual(self.processor._parse_retag_response(json.dumps([answer]), self.records), [])

    def test_failed_retag_request_returns_no_updates(self):
        self.processor.model = "test-model"
        self.processor.client = Mock()
        self.processor.client.chat.completions.create.side_effect = ConnectionError("offline")
        with self.assertLogs("TimeIndex.daemon.llm_processor", level=logging.ERROR):
            self.assertEqual(self.processor.retag_cluster(self.records), [])
        self.assertIsNone(self.records[0]["refined_tags"])


class OfflineRecordingTests(unittest.TestCase):
    def test_real_pipeline_saves_evidence_when_models_are_offline(self):
        with tempfile.TemporaryDirectory(prefix="timeindex-offline-") as directory:
            store = TimeIndexStore(db_path=directory)
            with patch("TimeIndex.daemon.daemon.TimeIndexStore", return_value=store):
                daemon = Daemon()
            daemon.llm_processor.client = Mock()
            daemon.llm_processor.client.chat.completions.create.side_effect = ConnectionError("offline")
            snapshot = SystemSnapshot(
                timestamp=datetime(2026, 10, 7, 14, 0),
                windows=[WindowInfo(1, "Python functions - Code", 10, "code.exe")],
                process_events=[ProcessEvent(datetime(2026, 10, 7, 14, 0), "created", "code.exe", 10)],
            )
            for index, outcome in enumerate(([], None, ConnectionError("embedding offline"))):
                snapshot.timestamp = datetime(2026, 10, 7, 14, 0, index)
                options = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with patch("TimeIndex.daemon.daemon.embedding_provider.get_embedding", **options), \
                     self.assertLogs("TimeIndex", level=logging.ERROR):
                    daemon._process_snapshot(snapshot)
            rows = store.store.get_table().to_arrow().to_pylist()
            self.assertEqual(len(rows), 3)
            for row in rows:
                self.assertIsNone(row["vector"])
                self.assertTrue(row["summary"])
                self.assertEqual(row["confidence"], 0)
                self.assertIn("Python functions", row["active_windows"][0])
                self.assertIn("code.exe", row["process_events"][0])
            store.close()

    def test_idle_retag_pipeline_preserves_all_eight_vectors_and_raw_records(self):
        with tempfile.TemporaryDirectory(prefix="timeindex-retag-") as directory:
            store = TimeIndexStore(db_path=directory)
            store.add_activity_batch([
                {"id": str(index), "summary": "Original Python activity", "tags": ["coding"],
                 "active_windows": [{"title": "Python functions - Code"}],
                 "vector": [0.25 + index / 100] * 768}
                for index in range(8)
            ])
            before = {row["id"]: row for row in store.store.get_table().to_arrow().to_pylist()}
            with patch("TimeIndex.daemon.daemon.TimeIndexStore", return_value=store):
                daemon = Daemon(summary_enabled=True)
            answer = [RetagMatchingTests.answer(index) for index in range(8)]
            message = Mock()
            message.model_dump.return_value = {"content": "```json\n" + json.dumps(answer) + "\n```"}
            daemon.llm_processor.client = Mock()
            daemon.llm_processor.client.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=message)]
            )
            daemon._run_retag_task()
            after = {row["id"]: row for row in store.store.get_table().to_arrow().to_pylist()}
            self.assertEqual(len(after), 8)
            for record_id, row in after.items():
                for field in ("vector", "summary", "tags", "active_windows", "timestamp"):
                    self.assertEqual(row[field], before[record_id][field], field)
                self.assertEqual(row["refined_summary"], "Python functions")
            self.assertEqual(store.get_pending_retag(20), [])
            store.close()


class BlacklistTests(unittest.TestCase):
    def setUp(self):
        self.collector = WmiCollector(global_blacklist=["SECRET.EXE"])

    def test_blacklisted_events_never_enter_buffers_or_callbacks(self):
        callback = Mock()
        self.collector.add_event_callback(callback)
        event = SimpleNamespace(TargetInstance=SimpleNamespace(Name="secret.exe", ProcessId=10, CommandLine="private"))
        self.collector._handle_process_event(event, "created")
        self.assertEqual(self.collector._recent_events, [])
        callback.assert_not_called()

    def test_blacklisted_title_never_enters_snapshot_prompt_or_debug_log(self):
        from TimeIndex.daemon import wmi_monitor
        windows = {1: (10, "PRIVATE TITLE", "secret.exe"), 2: (20, "Public - Code", "code.exe")}
        def enumerate_windows(callback, argument):
            for hwnd in windows:
                callback(hwnd, argument)
        with patch.object(wmi_monitor.win32gui, "EnumWindows", side_effect=enumerate_windows), \
             patch.object(wmi_monitor.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(wmi_monitor.win32gui, "GetWindowText", side_effect=lambda hwnd: windows[hwnd][1]) as title_reader, \
             patch.object(wmi_monitor.win32process, "GetWindowThreadProcessId", side_effect=lambda hwnd: (0, windows[hwnd][0])), \
             patch.object(self.collector, "_get_process_name", side_effect=lambda pid: next(row[2] for row in windows.values() if row[0] == pid)), \
             self.assertLogs(wmi_monitor.logger, level=logging.DEBUG) as logs:
            collected = self.collector._collect_window_titles()
        self.assertEqual([window.process_name for window in collected], ["code.exe"])
        title_reader.assert_called_once_with(2)
        self.assertNotIn("PRIVATE TITLE", "\n".join(logs.output))
        snapshot = SystemSnapshot(datetime(2026, 10, 7), windows=collected)
        processor = LLMProcessor.__new__(LLMProcessor)
        self.assertNotIn("PRIVATE TITLE", processor._build_intent_prompt(snapshot))
        record = Daemon.__new__(Daemon)._build_record(snapshot, {"summary": "Public activity"})
        self.assertNotIn("PRIVATE TITLE", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
