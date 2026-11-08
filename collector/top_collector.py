import os
import subprocess

from collector.parser import (
    parse_loadavg,
    parse_cpu_stat,
    parse_meminfo,
    parse_processes,
    calculate_cpu_usage
)

def collect_cpu():
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

def collect_memory():
    with open("/proc/meminfo", "r") as file:
        memory_data = file.read()

    return parse_meminfo(memory_data)

def collect_processes():
    try:
        result = subprocess.run(
            ["top", "-b", "-n", "1", "-w", "512"],
            capture_output=True,
            text=True,
            check=True
        )

        return parse_processes(result.stdout)

    except subprocess.CalledProcessError:
        return []

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

