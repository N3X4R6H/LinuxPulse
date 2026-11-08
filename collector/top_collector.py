"""System data collector for Linux and macOS.

Public API (unchanged): collect_cpu(), collect_memory(), collect_processes(),
collect_system_data(previous_cpu=None). Every platform returns the same dict
shapes, with memory in KiB and cumulative CPU counters in `cpu_times`.

Linux  (Ubuntu, Debian, Kali, Mint, Arch, Fedora, ...): /proc + procps `top`
       (falls back to `top` without -w, then `ps`, e.g. on BusyBox systems).
macOS  (Apple Silicon M1-M5 and Intel): kernel CPU ticks via host_statistics()
       (ctypes, falls back to `top -l`), `vm_stat` + `sysctl` for memory, swap
       and load, `ps` for processes.
"""
import os
import subprocess
import sys
import tempfile

from collector.parser import (
    parse_loadavg,
    parse_cpu_stat,
    parse_meminfo,
    parse_processes,
    calculate_cpu_usage,
    parse_ps,
    parse_sysctl_loadavg,
    parse_mac_memory,
    parse_mac_top_cpu,
)

IS_MAC = sys.platform == "darwin"
COMMAND_TIMEOUT_SECONDS = 10

# Run tools in the C locale ('.' decimal point, English headers) and without the
# user's personal toprc, so the output format is the same on every machine.
_ENV = dict(os.environ, LC_ALL="C", LANG="C",
            HOME=os.path.join(tempfile.gettempdir(), "linuxpulse-no-toprc"),
            XDG_CONFIG_HOME=os.path.join(tempfile.gettempdir(), "linuxpulse-no-toprc"))


def _run(args):
    """Run a command and return stdout; raises on failure, missing binary or timeout."""
    result = subprocess.run(args, capture_output=True, text=True, check=True,
                            env=_ENV, timeout=COMMAND_TIMEOUT_SECONDS)
    return result.stdout


# --------------------------------------------------------------------------- CPU
def _cpu_times_dict(user, nice, system, idle, iowait=0, irq=0, softirq=0, steal=0):
    times = [user, nice, system, idle, iowait, irq, softirq, steal]
    return {
        "user": user, "nice": nice, "system": system, "idle": idle,
        "iowait": iowait, "irq": irq, "softirq": softirq, "steal": steal,
        "total": sum(times), "idle_total": idle + iowait,
    }


_mach = None


def _mac_cpu_ticks():
    """Cumulative CPU ticks from the macOS kernel (host_statistics, HOST_CPU_LOAD_INFO).

    Same idea as Linux /proc/stat: counters only ever grow, usage = delta between samples.
    Returns None if the call is unavailable.
    """
    global _mach
    try:
        import ctypes
        import ctypes.util
        if _mach is None:
            lib = ctypes.CDLL(ctypes.util.find_library("System") or "/usr/lib/libSystem.B.dylib")
            lib.mach_host_self.restype = ctypes.c_uint
            lib.host_statistics.argtypes = [ctypes.c_uint, ctypes.c_int,
                                            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
            lib.host_statistics.restype = ctypes.c_int
            _mach = (lib, lib.mach_host_self())      # host port fetched once (no port leak)
        lib, host = _mach
        info = (ctypes.c_uint * 4)()                  # CPU_STATE_USER, SYSTEM, IDLE, NICE
        count = ctypes.c_uint(4)                      # HOST_CPU_LOAD_INFO_COUNT
        if lib.host_statistics(host, 3, info, ctypes.byref(count)) != 0:   # 3 = HOST_CPU_LOAD_INFO
            return None
        user, system, idle, nice = (int(v) for v in info)
        return _cpu_times_dict(user=user, nice=nice, system=system, idle=idle)
    except (OSError, AttributeError, ValueError):
        return None


_synthetic_ticks = None


def _mac_cpu_ticks_from_top():
    """Fallback: CPU % from `top -l 2` turned into growing counters so deltas still work."""
    global _synthetic_ticks
    usage = parse_mac_top_cpu(_run(["top", "-l", "2", "-n", "0", "-s", "1"]))
    if _synthetic_ticks is None:
        _synthetic_ticks = {"user": 0, "system": 0, "idle": 0}
    for key in ("user", "system", "idle"):
        _synthetic_ticks[key] += int(round(usage[key] * 100))
    t = _synthetic_ticks
    return _cpu_times_dict(user=t["user"], nice=0, system=t["system"], idle=t["idle"])


def collect_cpu():
    if IS_MAC:
        current_cpu = _mac_cpu_ticks() or _mac_cpu_ticks_from_top()
        load_average = parse_sysctl_loadavg(_run(["sysctl", "-n", "vm.loadavg"]))
    else:
        with open("/proc/stat", "r") as file:
            cpu_data = file.readline()

        with open("/proc/loadavg", "r") as file:
            load_data = file.read()

        current_cpu = parse_cpu_stat(cpu_data)
        load_average = parse_loadavg(load_data)

    return {
        "cpu_cores": os.cpu_count(),
        "cpu_times": current_cpu,
        **load_average
    }


# --------------------------------------------------------------------------- memory
def collect_memory():
    if IS_MAC:
        memsize = _run(["sysctl", "-n", "hw.memsize"]).strip()
        try:
            swap = _run(["sysctl", "-n", "vm.swapusage"])
        except (subprocess.SubprocessError, OSError):
            swap = ""                                     # no swap info -> reported as 0 swap
        return parse_mac_memory(memsize, _run(["vm_stat"]), swap)

    with open("/proc/meminfo", "r") as file:
        memory_data = file.read()

    return parse_meminfo(memory_data)


# --------------------------------------------------------------------------- processes
_PS_FORMAT = "pid=,user=,%cpu=,%mem=,state=,comm="


def collect_processes():
    """Process list; [] if every method fails (never raises)."""
    if IS_MAC:
        attempts = [(["ps", "-axo", _PS_FORMAT], parse_ps)]
    else:
        attempts = [
            (["top", "-b", "-n", "1", "-w", "512"], parse_processes),   # procps-ng (most distros)
            (["top", "-b", "-n", "1"], parse_processes),                # top without -w
            (["ps", "-eo", _PS_FORMAT], parse_ps),                      # BusyBox / no top
        ]

    for args, parser in attempts:
        try:
            processes = parser(_run(args))
        except (subprocess.SubprocessError, OSError):
            continue
        if processes:
            return processes

    return []


# --------------------------------------------------------------------------- snapshot
def collect_system_data(previous_cpu=None):
    cpu_data = collect_cpu()
    memory_data = collect_memory()
    process_data = collect_processes()

    cpu_usage = None

    if previous_cpu is not None:
        cpu_usage = calculate_cpu_usage(
            previous_cpu,
            cpu_data["cpu_times"]
        )

    return {
        "cpu_usage": cpu_usage,
        "cpu_cores": cpu_data["cpu_cores"],
        "cpu_times": cpu_data["cpu_times"],
        "load_average": {
            "1min": cpu_data["load_1min"],
            "5min": cpu_data["load_5min"],
            "15min": cpu_data["load_15min"]
        },
        "memory": memory_data,
        "processes": process_data
    }
