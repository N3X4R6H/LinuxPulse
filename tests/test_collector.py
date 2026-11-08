import unittest
from unittest.mock import patch
from subprocess import CalledProcessError

from collector.top_collector import (
    collect_cpu,
    collect_memory,
    collect_processes,
    collect_system_data
)


class TestCollector(unittest.TestCase):

    def test_collect_cpu(self):
        result = collect_cpu()

        self.assertIsInstance(result["cpu_cores"], int)
        self.assertGreater(result["cpu_cores"], 0)
        self.assertIn("load_1min", result)
        self.assertIn("load_5min", result)
        self.assertIn("load_15min", result)
        self.assertIn("cpu_times", result)

    def test_collect_memory(self):
        result = collect_memory()

        self.assertIn("ram_total", result)
        self.assertIn("ram_used", result)
        self.assertIn("swap_total", result)
        self.assertGreater(result["ram_total"], 0)

    def test_collect_processes(self):
        result = collect_processes()

        self.assertIsInstance(result, list)

        if result:
            self.assertIn("pid", result[0])
            self.assertIn("cpu_percent", result[0])
            self.assertIn("memory_percent", result[0])
            self.assertIn("command", result[0])

    def test_process_command_failure(self):
        with patch(
            "collector.top_collector.subprocess.run",
            side_effect=CalledProcessError(1, "ps")
        ):
            result = collect_processes()

        self.assertEqual(result, [])

    def test_collect_system_data(self):
        result = collect_system_data()

        self.assertIn("cpu_usage", result)
        self.assertIn("cpu_cores", result)
        self.assertIn("cpu_times", result)
        self.assertIn("load_average", result)
        self.assertIn("memory", result)
        self.assertIn("processes", result)

        self.assertIsNone(result["cpu_usage"])
        self.assertIsInstance(result["processes"], list)

    def test_cpu_usage_with_previous_reading(self):
        previous_cpu = {
            "total": 1000,
            "idle_total": 700
        }

        current_cpu = {
            "total": 1100,
            "idle_total": 750
        }

        with patch(
            "collector.top_collector.collect_cpu",
            return_value={
                "cpu_cores": 4,
                "cpu_times": current_cpu,
                "load_1min": 0.5,
                "load_5min": 0.6,
                "load_15min": 0.7
            }
        ), patch(
            "collector.top_collector.collect_memory",
            return_value={}
        ), patch(
            "collector.top_collector.collect_processes",
            return_value=[]
        ):
            result = collect_system_data(previous_cpu)

        self.assertEqual(result["cpu_usage"], 50.0)


if __name__ == "__main__":
    unittest.main()
