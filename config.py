"""Centralized configuration for the LINUXPULSE application.

All tunable runtime parameters live in this module. Every other module
(collector, analytics, GUI, visualization, main) MUST import its settings
from here instead of redefining literals locally, so that there is exactly
one source of truth and behavior can be changed in a single place.

The module exposes a frozen :class:`AppConfig` dataclass and a ready-to-use
:class:`DEFAULT_CONFIG` instance. Overrides may be supplied programmatically
by constructing a new ``AppConfig`` or from the environment via
:meth:`AppConfig.from_env` (variables prefixed ``LINUXPULSE_``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MemoryUnit(str, Enum):
    """Units in which memory quantities are presented to the end user.

    The application stores memory internally in *bytes* (see
    :mod:`models`). This setting only controls the unit used when a value
    is rendered for display by the GUI or the visualization layer.
    """

    BYTES = "bytes"
    KIB = "KiB"
    MIB = "MiB"
    GIB = "GiB"


# Conversion factor from one byte to a given unit's base quantity.
_BYTES_PER_UNIT = {
    MemoryUnit.BYTES: 1,
    MemoryUnit.KIB: 1024,
    MemoryUnit.MIB: 1024 ** 2,
    MemoryUnit.GIB: 1024 ** 3,
}


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration.

    Field names carry their unit suffix (``_seconds``, ``_percent``,
    ``_bytes``, ``_count``) so that units are self-documenting at every
    call site and no implicit conversion is needed.
    """

    # --- Sampling cadence and history -------------------------------------
    # Seconds between two consecutive ``top`` samples produced by the collector.
    sampling_interval_seconds: float = 2.0
    # Maximum number of samples retained in the in-memory history ring buffer.
    # At the default interval this is 300 * 2s = 600s = 10 minutes of history.
    history_limit: int = 300
    # How many processes the collector keeps per snapshot (top ``-n`` rows).
    default_process_count: int = 20

    # --- Alert thresholds (percent, 0.0 - 100.0) --------------------------
    cpu_threshold_percent: float = 80.0
    ram_threshold_percent: float = 85.0
    swap_threshold_percent: float = 80.0

    # --- Display ----------------------------------------------------------
    memory_display_unit: MemoryUnit = MemoryUnit.MIB

    # --- Concurrency: queue and thread settings ---------------------------
    # Capacity of the queue that decouples the collector (producer) from the
    # analytics / GUI (consumers). Bounding it prevents unbounded memory
    # growth if a consumer falls behind. When full the producer drops the
    # oldest pending snapshot (see docs/architecture.md).
    queue_capacity: int = 256
    # Names make threads identifiable in tooling such as py-spy / htop.
    collector_thread_name: str = "linuxpulse-collector"
    analytics_thread_name: str = "linuxpulse-analytics"
    gui_thread_name: str = "linuxpulse-gui"
    # Collector and analytics run as daemon threads so that a GUI exit can
    # tear the process down even if a thread is mid-work.
    collector_thread_daemon: bool = True
    analytics_thread_daemon: bool = True

    # --- Collector subprocess invocation ----------------------------------
    # The binary and flags used to drive ``top`` in batch mode. Centralizing
    # them here keeps the collector (Member 1) free of magic literals.
    top_binary: str = "top"
    top_batch_mode: bool = True        # -b : batch mode, no curses
    top_iterations: int = 1            # -n : produce this many samples per call
    top_show_threads: bool = True      # -H : show per-thread rows
    # Time, in seconds, the collector waits for ``top`` to exit on stop.
    top_terminate_timeout_seconds: float = 3.0

    # --- GUI / visualization refresh --------------------------------------
    # How often the Tkinter main loop re-renders from the latest data.
    gui_refresh_interval_seconds: float = 1.0

    # --- Shutdown ---------------------------------------------------------
    # Maximum time main.py waits for worker threads to join on shutdown.
    shutdown_timeout_seconds: float = 5.0

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def from_env(cls, base: Optional["AppConfig"] = None) -> "AppConfig":
        """Return an :class:`AppConfig` with fields overridden by env vars.

        Recognized variables (all optional)::

            LINUXPULSE_SAMPLING_INTERVAL_SECONDS
            LINUXPULSE_HISTORY_LIMIT
            LINUXPULSE_DEFAULT_PROCESS_COUNT
            LINUXPULSE_CPU_THRESHOLD_PERCENT
            LINUXPULSE_RAM_THRESHOLD_PERCENT
            LINUXPULSE_SWAP_THRESHOLD_PERCENT
            LINUXPULSE_MEMORY_DISPLAY_UNIT   (bytes|KiB|MiB|GiB)
            LINUXPULSE_QUEUE_CAPACITY
            LINUXPULSE_GUI_REFRESH_INTERVAL_SECONDS

        Unset variables fall back to the values from ``base`` (or the
        dataclass defaults). Malformed values are ignored with a warning
        printed to stderr rather than raising, so a bad env var cannot
        prevent the application from starting.
        """
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


# The single canonical instance used by the rest of the application.
DEFAULT_CONFIG: AppConfig = AppConfig()


# ---------------------------------------------------------------------- #
# Display helpers (tied to the configured memory unit)
# ---------------------------------------------------------------------- #
def convert_bytes(value: Optional[int],
                  unit: MemoryUnit = DEFAULT_CONFIG.memory_display_unit
                  ) -> Optional[float]:
    """Convert a byte quantity to ``unit``. ``None`` passes through."""
    if value is None:
        return None
    return value / _BYTES_PER_UNIT[unit]


def format_memory(value: Optional[int],
                  unit: MemoryUnit = DEFAULT_CONFIG.memory_display_unit,
                  precision: int = 1) -> str:
    """Format a byte quantity as a human-readable string in ``unit``.

    ``None`` (i.e. an unavailable measurement) renders as ``"-"`` so that
    the GUI never confuses "missing" with "0".
    """
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
