import unittest

from collector.parser import (
    parse_loadavg,
    parse_cpu_stat,
    parse_meminfo,
    parse_processes,
    calculate_cpu_usage
)


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


if __name__ == "__main__":
    unittest.main()
