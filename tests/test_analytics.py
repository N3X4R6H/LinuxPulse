import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from analytics.engine import AnalyticsEngine


def make_snapshot(cpu=0, ram=0, swap=0, processes=None, timestamp="2026-11-08T12:00:00Z"):
    return {
        "timestamp": timestamp,
        "cpu": {"usage_percent": cpu},
        "memory": {"usage_percent": ram},
        "swap": {"usage_percent": swap},
        "processes": processes if processes is not None else [],
    }


class TestAnalyticsEngine(unittest.TestCase):
    def test_empty_engine_returns_empty_analytics(self):
        engine = AnalyticsEngine()
        result = engine.get_analytics()

        self.assertEqual(result["sample_count"], 0)
        self.assertEqual(result["active_alerts"], [])
        self.assertIsNone(result["resources"]["cpu"]["mean_percent"])
        self.assertEqual(engine.get_history(), [])
        self.assertEqual(engine.get_latest_processes(), [])

    def test_stores_samples_with_timestamps(self):
        engine = AnalyticsEngine()
        engine.add_snapshot(make_snapshot(cpu=20, timestamp="2026-11-08T12:00:00Z"))

        history = engine.get_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["timestamp"], "2026-11-08T12:00:00.000+00:00")

    def test_history_is_bounded(self):
        engine = AnalyticsEngine(history_size=3)
        for cpu in (10, 20, 30, 40, 50):
            engine.add_snapshot(make_snapshot(cpu=cpu))

        history = engine.get_history()
        self.assertEqual(len(history), 3)
        self.assertEqual([sample["cpu_percent"] for sample in history], [30, 40, 50])

    def test_mean_minimum_and_maximum(self):
        engine = AnalyticsEngine()
        for cpu in (20, 40, 60):
            engine.add_snapshot(make_snapshot(cpu=cpu))

        stats = engine.get_analytics()["resources"]["cpu"]
        self.assertEqual(stats["mean_percent"], 40)
        self.assertEqual(stats["minimum_percent"], 20)
        self.assertEqual(stats["maximum_percent"], 60)

    def test_rolling_average_uses_last_n_samples(self):
        engine = AnalyticsEngine(rolling_window=3)
        for cpu in (10, 20, 30, 40):
            engine.add_snapshot(make_snapshot(cpu=cpu))

        stats = engine.get_analytics()["resources"]["cpu"]
        self.assertEqual(stats["rolling_average_percent"], 30)
        self.assertEqual(stats["rolling_valid_samples"], 3)

    def test_missing_measurements_are_ignored_not_treated_as_zero(self):
        engine = AnalyticsEngine()
        engine.add_snapshot({"timestamp": "2026-11-08T12:00:00Z", "cpu": {"usage_percent": 40}})
        engine.add_snapshot({"timestamp": "2026-11-08T12:00:01Z", "cpu": {"usage_percent": None}})

        stats = engine.get_analytics()["resources"]["cpu"]
        self.assertEqual(stats["mean_percent"], 40)
        self.assertEqual(stats["valid_samples"], 1)
        self.assertIsNone(stats["current_percent"])

    def test_memory_and_swap_can_be_calculated_from_bytes(self):
        engine = AnalyticsEngine()
        snapshot = {
            "memory": {"used_bytes": 75, "total_bytes": 100},
            "swap": {"used_bytes": 25, "total_bytes": 200},
        }
        engine.add_snapshot(snapshot)

        result = engine.get_analytics()["resources"]
        self.assertEqual(result["ram"]["current_percent"], 75)
        self.assertEqual(result["swap"]["current_percent"], 12.5)

    def test_zero_total_memory_is_unavailable(self):
        engine = AnalyticsEngine()
        engine.add_snapshot({"memory": {"used_bytes": 0, "total_bytes": 0}})

        self.assertIsNone(engine.get_analytics()["resources"]["ram"]["current_percent"])

    def test_top_processes_are_sorted(self):
        engine = AnalyticsEngine(top_process_limit=2)
        processes = [
            {"pid": 1, "name": "low", "cpu_percent": 2, "memory_percent": 70},
            {"pid": 2, "name": "high cpu", "cpu_percent": 90, "memory_percent": 10},
            {"pid": 3, "name": "medium", "cpu_percent": 30, "memory_percent": 40},
        ]
        engine.add_snapshot(make_snapshot(processes=processes))

        result = engine.get_analytics()
        self.assertEqual([p["name"] for p in result["top_cpu_processes"]], ["high cpu", "medium"])
        self.assertEqual([p["name"] for p in result["top_memory_processes"]], ["low", "medium"])

    def test_unusual_process_names_are_preserved(self):
        engine = AnalyticsEngine()
        unusual_name = "worker [kthreadd]/α;$(test)"
        engine.add_snapshot(make_snapshot(processes=[{"pid": 7, "name": unusual_name, "cpu_percent": 1}]))

        self.assertEqual(engine.get_latest_processes()[0]["name"], unusual_name)

    def test_malformed_process_entries_are_skipped(self):
        engine = AnalyticsEngine()
        engine.add_snapshot(make_snapshot(processes=[None, 17, {}, {"pid": 2, "name": "valid", "cpu_percent": 4}] ))

        processes = engine.get_latest_processes()
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes[0]["name"], "valid")

    def test_fractional_process_id_is_not_truncated(self):
        engine = AnalyticsEngine()
        engine.add_snapshot(make_snapshot(processes=[{"pid": 2.5, "name": "worker", "cpu_percent": 4}]))

        process = engine.get_latest_processes()[0]
        self.assertIsNone(process["pid"])
        self.assertEqual(process["name"], "worker")

    def test_none_snapshot_is_safe(self):
        engine = AnalyticsEngine()
        result = engine.add_snapshot(None)

        self.assertEqual(result["sample_count"], 1)
        self.assertIsNone(result["resources"]["cpu"]["current_percent"])
        self.assertEqual(engine.get_latest_processes(), [])

    def test_empty_process_list_clears_previous_processes(self):
        engine = AnalyticsEngine()
        engine.add_snapshot(make_snapshot(processes=[{"pid": 1, "name": "old", "cpu_percent": 1}]))
        engine.add_snapshot(make_snapshot(processes=[]))

        self.assertEqual(engine.get_latest_processes(), [])
        self.assertEqual(engine.get_analytics()["top_cpu_processes"], [])

    def test_alerts_trigger_at_thresholds(self):
        engine = AnalyticsEngine()
        engine.add_snapshot(make_snapshot(cpu=99, ram=85, swap=90))

        alerts = engine.get_analytics()["active_alerts"]
        self.assertEqual([alert["resource"] for alert in alerts], ["cpu", "ram", "swap"])

    def test_alerts_clear_when_values_drop(self):
        engine = AnalyticsEngine()
        engine.add_snapshot(make_snapshot(cpu=100, ram=90, swap=95))
        engine.add_snapshot(make_snapshot(cpu=50, ram=40, swap=20))

        self.assertEqual(engine.get_analytics()["active_alerts"], [])

    def test_missing_values_do_not_trigger_alerts(self):
        engine = AnalyticsEngine()
        engine.add_snapshot({"cpu": {}, "memory": {}, "swap": {}})

        self.assertEqual(engine.get_analytics()["active_alerts"], [])

    def test_invalid_percentages_are_rejected(self):
        engine = AnalyticsEngine()
        engine.add_snapshot(make_snapshot(cpu=150, ram=-1, swap="not-a-number"))

        resources = engine.get_analytics()["resources"]
        self.assertIsNone(resources["cpu"]["current_percent"])
        self.assertIsNone(resources["ram"]["current_percent"])
        self.assertIsNone(resources["swap"]["current_percent"])

    def test_accepts_dataclass_like_snapshots(self):
        @dataclass
        class Resource:
            usage_percent: float

        @dataclass
        class Snapshot:
            timestamp: datetime
            cpu: Resource
            memory: Resource
            swap: Resource
            processes: list

        snapshot = Snapshot(
            datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
            Resource(20), Resource(30), Resource(40), []
        )
        engine = AnalyticsEngine()
        engine.add_snapshot(snapshot)

        resources = engine.get_analytics()["resources"]
        self.assertEqual(resources["cpu"]["current_percent"], 20)
        self.assertEqual(resources["ram"]["current_percent"], 30)

    def test_reset_clears_everything(self):
        engine = AnalyticsEngine()
        engine.add_snapshot(make_snapshot(cpu=20, processes=[{"pid": 1, "name": "p", "cpu_percent": 1}]))
        engine.reset()

        self.assertEqual(engine.get_history(), [])
        self.assertEqual(engine.get_latest_processes(), [])
        self.assertEqual(engine.get_analytics()["sample_count"], 0)

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            AnalyticsEngine(history_size=0)
        with self.assertRaises(ValueError):
            AnalyticsEngine(cpu_threshold=101)


if __name__ == "__main__":
    unittest.main()
