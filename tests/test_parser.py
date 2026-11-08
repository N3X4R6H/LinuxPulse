import unittest

from collector.parser import (
    parse_loadavg,
    parse_cpu_stat,
    parse_meminfo,
    parse_processes,
    calculate_cpu_usage,
    parse_ps,
    parse_sysctl_loadavg,
    parse_vm_stat,
    parse_swapusage,
    parse_mac_memory,
    parse_mac_top_cpu
)

MAC_VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                3687.
Pages active:                            184925.
Pages inactive:                          181848.
Pages speculative:                         1612.
Pages throttled:                              0.
Pages wired down:                        122030.
Pages purgeable:                           5326.
"Translation faults":                1067410866.
Pages occupied by compressor:            288212.
"""


class TestParser(unittest.TestCase):

    def test_parse_loadavg(self):
        result = parse_loadavg("0.50 0.75 1.00 2/100 1234")

        self.assertEqual(result["load_1min"], 0.50)
        self.assertEqual(result["load_5min"], 0.75)
        self.assertEqual(result["load_15min"], 1.00)

    def test_invalid_loadavg(self):
        with self.assertRaises(ValueError):
            parse_loadavg("0.50 0.75")

    def test_parse_cpu_stat(self):
        result = parse_cpu_stat("cpu 100 20 30 400 5 6 7 8")

        self.assertEqual(result["user"], 100)
        self.assertEqual(result["idle"], 400)
        self.assertEqual(result["total"], 576)
        self.assertEqual(result["idle_total"], 405)

    def test_invalid_cpu_stat(self):
        with self.assertRaises(ValueError):
            parse_cpu_stat("invalid data")

    def test_parse_meminfo(self):
        data = """
MemTotal:       1000 kB
MemFree:         200 kB
MemAvailable:    600 kB
SwapTotal:       500 kB
SwapFree:        300 kB
"""

        result = parse_meminfo(data)

        self.assertEqual(result["ram_total"], 1000)
        self.assertEqual(result["ram_used"], 400)
        self.assertEqual(result["ram_available"], 600)
        self.assertEqual(result["ram_usage_percent"], 40.0)
        self.assertEqual(result["swap_used"], 200)
        self.assertEqual(result["swap_usage_percent"], 40.0)

    def test_missing_memory_field(self):
        data = """
MemTotal: 1000 kB
MemFree: 200 kB
"""

        with self.assertRaises(ValueError):
            parse_meminfo(data)

    def test_parse_processes(self):
        data = """PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
123 root 20 0 1000 500 200 R 10.5 2.0 0:01.00 python3
456 user 20 0 2000 600 300 S 5.0 1.0 0:02.00 firefox
"""

        result = parse_processes(data)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["pid"], 123)
        self.assertEqual(result[0]["cpu_percent"], 10.5)
        self.assertEqual(result[1]["command"], "firefox")

    def test_empty_processes(self):
        self.assertEqual(parse_processes(""), [])

    def test_process_with_spaces(self):
        data = """PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
123 user 20 0 1000 500 200 R 2.0 1.0 0:01.00 my process (test)
"""

        result = parse_processes(data)

        self.assertEqual(result[0]["command"], "my process (test)")

    def test_malformed_process(self):
        data = """PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
invalid row
"""

        self.assertEqual(parse_processes(data), [])

    def test_calculate_cpu_usage(self):
        previous = {"total": 1000, "idle_total": 700}
        current = {"total": 1100, "idle_total": 750}

        result = calculate_cpu_usage(previous, current)

        self.assertEqual(result, 50.0)


    # ---- portability (added during the Linux/macOS hardening) ----
    def test_meminfo_without_memavailable_old_kernel(self):
        data = """
MemTotal:       1000 kB
MemFree:         200 kB
Buffers:          50 kB
Cached:          250 kB
SwapTotal:         0 kB
SwapFree:          0 kB
"""
        result = parse_meminfo(data)
        self.assertEqual(result["ram_available"], 500)
        self.assertEqual(result["ram_used"], 500)
        self.assertEqual(result["swap_usage_percent"], 0)

    def test_processes_decimal_comma_locale(self):
        data = """PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
123 root 20 0 1000 500 200 R 1,5 0,2 0:01.00 init
"""
        result = parse_processes(data)
        self.assertEqual(result[0]["cpu_percent"], 1.5)
        self.assertEqual(result[0]["memory_percent"], 0.2)

    def test_processes_columns_found_by_name(self):
        data = """  PID USER      %CPU %MEM S COMMAND
  77 alice      3.0  1.0 S sshd: alice@pts/0
"""
        result = parse_processes(data)
        self.assertEqual(result[0]["pid"], 77)
        self.assertEqual(result[0]["state"], "S")
        self.assertEqual(result[0]["command"], "sshd: alice@pts/0")

    def test_parse_ps_linux_and_macos(self):
        data = """    1 root               0.0  0.1 Ss   /sbin/launchd
  412 dhiren            23.4  7.3 R    /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  bad line
"""
        result = parse_ps(data)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["command"], "launchd")
        self.assertEqual(result[0]["state"], "S")
        self.assertEqual(result[1]["command"], "Google Chrome")
        self.assertEqual(result[1]["cpu_percent"], 23.4)

    def test_parse_sysctl_loadavg(self):
        result = parse_sysctl_loadavg("{ 1.89 2.10 2.21 }")
        self.assertEqual(result, {"load_1min": 1.89, "load_5min": 2.10, "load_15min": 2.21})
        with self.assertRaises(ValueError):
            parse_sysctl_loadavg("{ }")

    def test_parse_vm_stat(self):
        stats = parse_vm_stat(MAC_VM_STAT)
        self.assertEqual(stats["page_size"], 16384)
        self.assertEqual(stats["free"], 3687)
        self.assertEqual(stats["inactive"], 181848)
        self.assertEqual(stats["wired_down"], 122030)

    def test_parse_swapusage(self):
        total, used = parse_swapusage("total = 2048.00M  used = 1003.75M  free = 1044.25M  (encrypted)")
        self.assertEqual(total, 2048 * 1024)
        self.assertEqual(used, int(1003.75 * 1024))

    def test_parse_mac_memory(self):
        result = parse_mac_memory(str(8 * 1024 ** 3), MAC_VM_STAT,
                                  "total = 0.00M  used = 0.00M  free = 0.00M")
        self.assertEqual(result["ram_total"], 8 * 1024 * 1024)
        self.assertEqual(result["ram_available"], (3687 + 181848) * 16)
        self.assertGreater(result["ram_usage_percent"], 0)
        self.assertEqual(result["swap_total"], 0)

    def test_parse_mac_top_cpu_uses_last_sample(self):
        data = """CPU usage: 50.0% user, 10.0% sys, 40.0% idle
CPU usage: 6.97% user, 5.47% sys, 87.55% idle
"""
        self.assertEqual(parse_mac_top_cpu(data), {"user": 6.97, "system": 5.47, "idle": 87.55})


if __name__ == "__main__":
    unittest.main()
