"""Parsers that turn raw command / procfs text into plain dictionaries.

Linux sources: /proc/loadavg, /proc/stat, /proc/meminfo, `top -b`, `ps`.
macOS sources: `sysctl vm.loadavg`, `sysctl vm.swapusage`, `vm_stat`, `ps`, `top -l`.

All parsers are pure functions (text in, dict/list out) so they can be unit
tested on any OS. Memory values are returned in KiB on every platform.
"""
import os
import re


def _to_float(text):
    """Float that also accepts a decimal comma ('1,5'), as printed by some locales."""
    return float(text.replace(",", "."))


# --------------------------------------------------------------------------- Linux
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
            try:
                memory[key] = int(parts[1])
            except ValueError:
                continue

    # Kernels older than 3.14 have no MemAvailable: estimate it the way the
    # kernel does (free + reclaimable page cache and slab).
    if "MemAvailable" not in memory and all(k in memory for k in ("MemFree", "Buffers", "Cached")):
        memory["MemAvailable"] = (memory["MemFree"] + memory["Buffers"] + memory["Cached"]
                                  + memory.get("SReclaimable", 0))

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

    return _memory_dict(total, free, available, swap_total, swap_total - swap_free)


def _memory_dict(total, free, available, swap_total, swap_used):
    """Common memory result (all KiB), shared by the Linux and macOS parsers."""
    if total <= 0:
        raise ValueError("Invalid total memory")
    return {
        "ram_total": total,
        "ram_used": total - available,
        "ram_free": free,
        "ram_available": available,
        "ram_usage_percent": ((total - available) / total) * 100,
        "swap_total": swap_total,
        "swap_used": swap_used,
        "swap_free": swap_total - swap_used,
        "swap_usage_percent": (
            swap_used / swap_total * 100
            if swap_total > 0 else 0
        )
    }


# Column names in `top` output that the parser needs
_TOP_COLUMNS = ("PID", "USER", "S", "%CPU", "%MEM", "COMMAND")


def parse_processes(output):
    """Parse the task area of `top -b` output.

    Columns are located by their header names, so a different column order or
    extra columns do not break parsing. Rows that cannot be parsed are skipped.
    """
    processes = []
    lines = output.splitlines()

    header = None
    header_index = -1

    for i, line in enumerate(lines):
        cols = line.split()
        if "PID" in cols and "USER" in cols and "COMMAND" in cols:
            header, header_index = cols, i
            break

    if header is None:
        return processes

    index = {name: header.index(name) for name in _TOP_COLUMNS if name in header}
    # %CPU and %MEM are required; COMMAND must be last so names with spaces stay whole
    if "%CPU" not in index or "%MEM" not in index or header[-1] != "COMMAND":
        return processes

    for line in lines[header_index + 1:]:
        parts = line.split(None, len(header) - 1)

        if len(parts) < len(header):
            continue

        try:
            process = {
                "pid": int(parts[index["PID"]]),
                "user": parts[index["USER"]],
                "cpu_percent": _to_float(parts[index["%CPU"]]),
                "memory_percent": _to_float(parts[index["%MEM"]]),
                "state": parts[index["S"]] if "S" in index else None,
                "command": parts[-1]
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


# --------------------------------------------------------------------------- ps (Linux fallback + macOS)
def parse_ps(output):
    """Parse `ps -o pid=,user=,%cpu=,%mem=,state=,comm=` output (no header).

    `comm` may be a full path on macOS; only its last component is kept.
    """
    processes = []
    for line in output.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        try:
            command = parts[5].strip()
            processes.append({
                "pid": int(parts[0]),
                "user": parts[1],
                "cpu_percent": _to_float(parts[2]),
                "memory_percent": _to_float(parts[3]),
                "state": parts[4][:1] or None,
                "command": os.path.basename(command) or command,
            })
        except ValueError:
            continue
    return processes


# --------------------------------------------------------------------------- macOS
def parse_sysctl_loadavg(output):
    """`sysctl -n vm.loadavg` -> '{ 1.89 2.10 2.21 }'."""
    values = re.findall(r"\d+(?:[.,]\d+)?", output)
    if len(values) < 3:
        raise ValueError("Invalid load average data")
    return {
        "load_1min": _to_float(values[0]),
        "load_5min": _to_float(values[1]),
        "load_15min": _to_float(values[2])
    }


def parse_vm_stat(output):
    """`vm_stat` -> {'page_size': bytes, 'free': pages, 'active': pages, ...}."""
    page = re.search(r"page size of (\d+) bytes", output)
    if not page:
        raise ValueError("Invalid vm_stat output")
    stats = {"page_size": int(page.group(1))}
    for line in output.splitlines():
        m = re.match(r'\s*"?([^":]+)"?:\s+(\d+)\.?\s*$', line)
        if m:
            key = m.group(1).strip().lower().replace("pages ", "").replace(" ", "_")
            stats[key] = int(m.group(2))
    return stats


_SIZE_UNITS = {"K": 1, "M": 1024, "G": 1024 ** 2, "T": 1024 ** 3}


def parse_swapusage(output):
    """`sysctl -n vm.swapusage` -> (total_kib, used_kib).

    Example: 'total = 2048.00M  used = 1003.75M  free = 1044.25M  (encrypted)'.
    """
    m = re.search(r"total\s*=\s*([\d.,]+)([KMGT])\s+used\s*=\s*([\d.,]+)([KMGT])", output)
    if not m:
        raise ValueError("Invalid swap usage data")
    total = _to_float(m.group(1)) * _SIZE_UNITS[m.group(2)]
    used = _to_float(m.group(3)) * _SIZE_UNITS[m.group(4)]
    return int(total), int(used)


def parse_mac_memory(memsize_bytes, vm_stat_output, swapusage_output):
    """Combine `sysctl hw.memsize`, `vm_stat` and `vm.swapusage` into the common memory dict (KiB).

    available = free + inactive pages (same definition as psutil on macOS).
    """
    stats = parse_vm_stat(vm_stat_output)
    page_kib = stats["page_size"] / 1024
    total = int(int(memsize_bytes) / 1024)
    free = int((stats.get("free", 0) - stats.get("speculative", 0)) * page_kib)
    available = int((stats.get("free", 0) + stats.get("inactive", 0)) * page_kib)
    available = max(0, min(available, total))
    try:
        swap_total, swap_used = parse_swapusage(swapusage_output)
    except ValueError:
        swap_total, swap_used = 0, 0
    return _memory_dict(total, max(0, free), available, swap_total, swap_used)


def parse_mac_top_cpu(output):
    """Last 'CPU usage: 6.97% user, 5.47% sys, 87.55% idle' line of `top -l` output."""
    matches = re.findall(r"CPU usage:\s*([\d.,]+)%\s*user,\s*([\d.,]+)%\s*sys,\s*([\d.,]+)%\s*idle", output)
    if not matches:
        raise ValueError("Invalid top CPU data")
    user, system, idle = (_to_float(v) for v in matches[-1])
    return {"user": user, "system": system, "idle": idle}
