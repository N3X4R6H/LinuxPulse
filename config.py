from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MemoryUnit(str, Enum):
    BYTES = "bytes"
    KIB = "KiB"
    MIB = "MiB"
    GIB = "GiB"


_BYTES_PER_UNIT = {
    MemoryUnit.BYTES: 1,
    MemoryUnit.KIB: 1024,
    MemoryUnit.MIB: 1024 ** 2,
    MemoryUnit.GIB: 1024 ** 3,
}


@dataclass(frozen=True)
class AppConfig:
    sampling_interval_seconds: float = 2.0
    history_limit: int = 300
    default_process_count: int = 20

    cpu_threshold_percent: float = 90.0
    ram_threshold_percent: float = 85.0
    swap_threshold_percent: float = 80.0

    memory_display_unit: MemoryUnit = MemoryUnit.MIB

    queue_capacity: int = 256
    collector_thread_name: str = "linuxpulse-collector"
    analytics_thread_name: str = "linuxpulse-analytics"
    gui_thread_name: str = "linuxpulse-gui"
    collector_thread_daemon: bool = True
    analytics_thread_daemon: bool = True

    top_binary: str = "top"
    top_batch_mode: bool = True
    top_iterations: int = 1 
    top_show_threads: bool = True
    top_terminate_timeout_seconds: float = 3.0

    gui_refresh_interval_seconds: float = 1.0

    shutdown_timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls, base: Optional["AppConfig"] = None) -> "AppConfig":
        import sys

        defaults = base if base is not None else cls()

        def _as_float(name: str, current: float) -> float:
            raw = os.environ.get(name)
            if raw is None or raw == "":
                return current
            try:
                return float(raw)
            except ValueError:
                print(f"[config] ignoring non-numeric {name}={raw!r}",
                      file=sys.stderr)
                return current

        def _as_int(name: str, current: int) -> int:
            raw = os.environ.get(name)
            if raw is None or raw == "":
                return current
            try:
                return int(raw)
            except ValueError:
                print(f"[config] ignoring non-integer {name}={raw!r}",
                      file=sys.stderr)
                return current

        def _as_unit(name: str, current: MemoryUnit) -> MemoryUnit:
            raw = os.environ.get(name)
            if raw is None or raw == "":
                return current
            try:
                return MemoryUnit(raw)
            except ValueError:
                print(f"[config] ignoring unknown {name}={raw!r} "
                      f"(expected one of {[u.value for u in MemoryUnit]})",
                      file=sys.stderr)
                return current

        return cls(
            sampling_interval_seconds=_as_float(
                "LINUXPULSE_SAMPLING_INTERVAL_SECONDS",
                defaults.sampling_interval_seconds),
            history_limit=_as_int(
                "LINUXPULSE_HISTORY_LIMIT", defaults.history_limit),
            default_process_count=_as_int(
                "LINUXPULSE_DEFAULT_PROCESS_COUNT",
                defaults.default_process_count),
            cpu_threshold_percent=_as_float(
                "LINUXPULSE_CPU_THRESHOLD_PERCENT",
                defaults.cpu_threshold_percent),
            ram_threshold_percent=_as_float(
                "LINUXPULSE_RAM_THRESHOLD_PERCENT",
                defaults.ram_threshold_percent),
            swap_threshold_percent=_as_float(
                "LINUXPULSE_SWAP_THRESHOLD_PERCENT",
                defaults.swap_threshold_percent),
            memory_display_unit=_as_unit(
                "LINUXPULSE_MEMORY_DISPLAY_UNIT",
                defaults.memory_display_unit),
            queue_capacity=_as_int(
                "LINUXPULSE_QUEUE_CAPACITY", defaults.queue_capacity),
            gui_refresh_interval_seconds=_as_float(
                "LINUXPULSE_GUI_REFRESH_INTERVAL_SECONDS",
                defaults.gui_refresh_interval_seconds),
        )


DEFAULT_CONFIG: AppConfig = AppConfig()


def convert_bytes(value: Optional[int],
                  unit: MemoryUnit = DEFAULT_CONFIG.memory_display_unit
                  ) -> Optional[float]:
    if value is None:
        return None
    return value / _BYTES_PER_UNIT[unit]


def format_memory(value: Optional[int],
                  unit: MemoryUnit = DEFAULT_CONFIG.memory_display_unit,
                  precision: int = 1) -> str:
    if value is None:
        return "-"
    converted = value / _BYTES_PER_UNIT[unit]
    return f"{converted:.{precision}f} {unit.value}"


__all__ = [
    "MemoryUnit",
    "AppConfig",
    "DEFAULT_CONFIG",
    "convert_bytes",
    "format_memory",
]
