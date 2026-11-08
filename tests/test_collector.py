import unittest
from unittest.mock import patch
from subprocess import CalledProcessError

import collector.top_collector as tc
from collector.top_collector import (
    collect_cpu,
    collect_memory,
    collect_processes,
    collect_system_data
)
from tests.test_parser import MAC_VM_STAT

TOP_SAMPLE = """PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
1 root 20 0 1000 500 200 S 0.0 0.1 0:01.00 systemd
"""


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


    # ---- portability (added during the Linux/macOS hardening) ----
    def test_top_without_w_option_is_retried(self):
        calls = []

        def fake_run(args):
            calls.append(args)
            if "-w" in args:
                raise CalledProcessError(1, args)        # e.g. BusyBox top
            return TOP_SAMPLE

        with patch.object(tc, "IS_MAC", False), patch.object(tc, "_run", side_effect=fake_run):
            result = collect_processes()

        self.assertEqual(result[0]["command"], "systemd")
        self.assertEqual(len(calls), 2)

    def test_ps_fallback_when_top_missing(self):
        def fake_run(args):
            if args[0] == "top":
                raise FileNotFoundError("top")
            return "  42 root  1.0  0.5 S  /usr/sbin/crond\n"

        with patch.object(tc, "IS_MAC", False), patch.object(tc, "_run", side_effect=fake_run):
            result = collect_processes()

        self.assertEqual(result[0]["pid"], 42)
        self.assertEqual(result[0]["command"], "crond")

    def test_tools_run_in_c_locale(self):
        self.assertEqual(tc._ENV["LC_ALL"], "C")

    def test_macos_collection_path(self):
        outputs = {
            ("sysctl", "-n", "vm.loadavg"): "{ 1.50 1.20 1.00 }",
            ("sysctl", "-n", "hw.memsize"): str(16 * 1024 ** 3),
            ("sysctl", "-n", "vm.swapusage"): "total = 2048.00M  used = 512.00M  free = 1536.00M",
            ("vm_stat",): MAC_VM_STAT,
            ("top", "-l", "2", "-n", "0", "-s", "1"): "CPU usage: 20.0% user, 10.0% sys, 70.0% idle",
            ("ps", "-axo", tc._PS_FORMAT): "  1 root 0.0 0.1 Ss /sbin/launchd\n",
        }

        with patch.object(tc, "IS_MAC", True), \
                patch.object(tc, "_run", side_effect=lambda args: outputs[tuple(args)]), \
                patch.object(tc, "_mac_cpu_ticks", return_value=None):
            first = collect_system_data()
            second = collect_system_data(first["cpu_times"])

        self.assertEqual(second["load_average"]["1min"], 1.5)
        self.assertEqual(second["memory"]["ram_total"], 16 * 1024 * 1024)
        self.assertEqual(second["memory"]["swap_used"], 512 * 1024)
        self.assertEqual(second["processes"][0]["command"], "launchd")
        self.assertAlmostEqual(second["cpu_usage"], 30.0, places=1)


if __name__ == "__main__":
    unittest.main()
