def parse_loadavg(output):
    values = output.split()

    if len(values) < 3:
        raise ValueError("Invalid load average data")

    return {
        "load_1min": float(values[0]),
        "load_5min": float(values[1]),
        "load_15min": float(values[2])
    }

def parse_cpu_stat(output):
    values = output.split()

    if len(values) < 9 or values[0] != "cpu":
        raise ValueError("Invalid CPU statistics")

    times = [int(value) for value in values[1:9]]

    return {
        "user": times[0],
        "nice": times[1],
        "system": times[2],
        "idle": times[3],
        "iowait": times[4],
        "irq": times[5],
        "softirq": times[6],
        "steal": times[7],
        "total": sum(times),
        "idle_total": times[3] + times[4]
    }

def parse_meminfo(output):
    memory = {}

    for line in output.splitlines():
        parts = line.split()

        if len(parts) >= 2:
            key = parts[0].rstrip(":")
            value = int(parts[1])

            memory[key] = value

    required = ["MemTotal", "MemFree", "MemAvailable",
                "SwapTotal", "SwapFree"]

    for key in required:
        if key not in memory:
            raise ValueError(f"Missing memory field: {key}")

    total = memory["MemTotal"]
    free = memory["MemFree"]
    available = memory["MemAvailable"]
    swap_total = memory["SwapTotal"]
    swap_free = memory["SwapFree"]

    return {
        "ram_total": total,
        "ram_used": total - available,
        "ram_free": free,
        "ram_available": available,
        "ram_usage_percent": ((total - available) / total) * 100,
        "swap_total": swap_total,
        "swap_used": swap_total - swap_free,
        "swap_free": swap_free,
        "swap_usage_percent": (
            (swap_total - swap_free) / swap_total * 100
            if swap_total > 0 else 0
        )
    }

def parse_processes(output):
    processes = []
    lines = output.splitlines()

    header_index = -1

    for i, line in enumerate(lines):
        if "PID" in line and "USER" in line and "COMMAND" in line:
            header_index = i
            break

    if header_index == -1:
        return processes

    for line in lines[header_index + 1:]:
        parts = line.split(None, 11)

        if len(parts) < 12:
            continue

        try:
            process = {
                "pid": int(parts[0]),
                "user": parts[1],
                "cpu_percent": float(parts[8]),
                "memory_percent": float(parts[9]),
                "state": parts[7],
                "command": parts[11]
            }

            processes.append(process)

        except ValueError:
            continue

    return processes

def calculate_cpu_usage(previous, current):
    total_diff = current["total"] - previous["total"]
    idle_diff = current["idle_total"] - previous["idle_total"]

    if total_diff <= 0:
        return 0.0

    usage = (total_diff - idle_diff) / total_diff * 100

    return round(usage, 2)


