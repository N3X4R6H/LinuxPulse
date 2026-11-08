"""Typed data models for LINUXPULSE.

This module defines the canonical in-process representation of every piece
of data that flows between modules. All models are immutable
(:func:`dataclasses.dataclass` with ``frozen=True``) so snapshots can be
shared safely across threads without defensive copying.

Unit conventions (the "one canonical representation")
-----------------------------------------------------
* Memory quantities are stored in **bytes** as ``int``. Field names carry
  the ``_bytes`` suffix. The display unit (MiB by default) is a
  presentation concern handled by :mod:`config`, never stored here.
* Percentages are stored as ``float`` in the range ``0.0`` - ``100.0``
  and carry the ``_percent`` suffix.
* Counts carry the ``_count`` suffix. Timestamps are POSIX epoch seconds
  (``float``).

Optional vs. missing
--------------------
Any measurement that may be unavailable on a given host or in a given
sample is typed ``Optional[...]`` and uses ``None`` -- never a sentinel
``0`` or ``-1`` -- to mean "no value". This keeps "the sensor reported
zero" distinguishable from "the sensor reported nothing". Consumers must
check for ``None`` before doing arithmetic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Deque


# ---------------------------------------------------------------------- #
# Enums
# ---------------------------------------------------------------------- #
class AlertLevel(str, Enum):
    """Severity of a threshold alert raised by the analytics engine."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ProcessState(str, Enum):
    """Linux process states as reported by ``top`` (the ``S`` column).

    Stored as the raw letter to remain faithful to the source; consumers
    that want a label can map it themselves. Modelled as an enum so the
    accepted set is explicit, but unknown letters are tolerated by
    constructing via :class:`str`.
    """

    RUNNING = "R"
    SLEEPING = "S"
    DISK_SLEEP = "D"
    ZOMBIE = "Z"
    STOPPED = "T"
    TRACING_STOP = "t"
    PAGING = "W"
    DEAD = "X"


# ---------------------------------------------------------------------- #
# Sub-models
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class LoadAverages:
    """The three load-average figures reported by ``top``.

    Each is the run-queue average over the past 1, 5 and 15 minutes.
    Any of them may be ``None`` if the host does not report load average.
    """

    one_minute: Optional[float] = None
    five_minutes: Optional[float] = None
    fifteen_minutes: Optional[float] = None


@dataclass(frozen=True)
class CPUInfo:
    """Aggregated CPU state for a single snapshot.

    ``usage_percent`` is the system-wide busy percentage (0-100).
    ``core_count`` is the number of logical CPUs and is always an ``int``;
    it is structural metadata rather than a measurement, so it is never
    ``None``. ``load_averages`` groups the three standard load figures.
    """

    usage_percent: Optional[float] = None
    core_count: int = 0
    load_averages: LoadAverages = field(default_factory=LoadAverages)


@dataclass(frozen=True)
class MemoryInfo:
    """RAM state. All byte quantities are in **bytes**.

    ``usage_percent`` should equal ``used_bytes / total_bytes * 100``;
    prefer constructing via :meth:`from_total_used_free` so the
    percentage is computed consistently rather than independently parsed.
    """

    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    usage_percent: Optional[float] = None

    @classmethod
    def from_total_used_free(cls,
                             total_bytes: int,
                             used_bytes: int,
                             free_bytes: Optional[int] = None
                             ) -> "MemoryInfo":
        """Build a :class:`MemoryInfo`, deriving the usage percentage.

        ``free_bytes`` defaults to ``total_bytes - used_bytes`` when not
        supplied. If ``total_bytes`` is zero the percentage is ``None``
        (genuinely undefined) rather than a divide-by-zero.
        """
        if free_bytes is None:
            free_bytes = total_bytes - used_bytes
        usage_percent: Optional[float]
        if total_bytes <= 0:
            usage_percent = None
        else:
            usage_percent = (used_bytes / total_bytes) * 100.0
        return cls(
            total_bytes=total_bytes,
            used_bytes=used_bytes,
            free_bytes=free_bytes,
            usage_percent=usage_percent,
        )


@dataclass(frozen=True)
class SwapInfo:
    """Swap state. All byte quantities are in **bytes**.

    ``free_bytes`` is intentionally omitted to match the snapshot contract
    (total / used / usage percentage); it is trivially
    ``total_bytes - used_bytes`` when needed.
    """

    total_bytes: int = 0
    used_bytes: int = 0
    usage_percent: Optional[float] = None

    @classmethod
    def from_total_used(cls,
                        total_bytes: int,
                        used_bytes: int) -> "SwapInfo":
        """Build a :class:`SwapInfo`, deriving the usage percentage."""
        usage_percent: Optional[float]
        if total_bytes <= 0:
            usage_percent = None
        else:
            usage_percent = (used_bytes / total_bytes) * 100.0
        return cls(
            total_bytes=total_bytes,
            used_bytes=used_bytes,
            usage_percent=usage_percent,
        )


@dataclass(frozen=True)
class ProcessInfo:
    """A single process row as reported by ``top``.

    ``pid`` is always present and is the primary key. ``cpu_percent`` and
    ``memory_percent`` are ``Optional`` because ``top`` can render ``-``
    for the first sample or for kernel threads. ``username`` and ``state``
    are ``Optional`` for the same reason. ``state`` is stored as the raw
    letter (see :class:`ProcessState`).
    """

    pid: int
    name: str
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    username: Optional[str] = None
    state: Optional[str] = None


@dataclass(frozen=True)
class AlertInfo:
    """A threshold breach raised by the analytics engine.

    ``value`` is the measurement that triggered the alert and
    ``threshold`` is the configured limit it crossed, so the GUI can show
    both. Either may be ``None`` when the underlying measurement was
    unavailable (e.g. an alert about a swap value on a swap-less host).
    """

    level: AlertLevel
    metric: str
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: float = 0.0


@dataclass(frozen=True)
class MetricStatistics:
    """Summary statistics for one metric over the history window.

    Every field is ``Optional``: with too few samples (or all-``None``
    input) a statistic cannot be computed and must be ``None`` rather than
    a misleading ``0.0``. ``trend_slope`` is the slope of a simple linear
    least-squares fit over the samples (units: percent per second);
    ``None`` when fewer than two valid samples exist.
    """

    current: Optional[float] = None
    average: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    trend_slope: Optional[float] = None


# ---------------------------------------------------------------------- #
# Top-level models
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class SystemSnapshot:
    """A complete point-in-time view of the system, produced by the
    collector and consumed by analytics, the GUI and visualization.

    ``timestamp`` is the POSIX epoch seconds at which the sample was
    taken. ``cpu``, ``memory`` are always present (their inner fields
    may be ``None``). ``swap`` is ``Optional``: ``None`` means the host
    has no swap configured or the value could not be obtained. ``processes``
    is a list (possibly empty) ordered as ``top`` returned it.
    """

    timestamp: float
    cpu: CPUInfo
    memory: MemoryInfo
    swap: Optional[SwapInfo] = None
    processes: List[ProcessInfo] = field(default_factory=list)

    @classmethod
    def empty(cls, timestamp: Optional[float] = None) -> "SystemSnapshot":
        """Build a minimal placeholder snapshot with no measurements.

        Useful as a safe initial value before the first real sample
        arrives, so the GUI can render a known shape rather than ``None``.
        """
        ts = timestamp if timestamp is not None else time.time()
        return cls(
            timestamp=ts,
            cpu=CPUInfo(core_count=0),
            memory=MemoryInfo(),
            swap=None,
            processes=[],
        )


@dataclass(frozen=True)
class AnalyticsResult:
    """Output of the analytics engine for the current history window.

    ``window_seconds`` and ``sample_count`` describe the window the
    statistics were computed over. ``cpu`` and ``memory`` are always
    present; ``swap`` is ``None`` when the host has no swap.
    ``top_cpu_processes`` / ``top_memory_processes`` are the
    highest-consuming processes in the most recent snapshot.
    ``alerts`` lists every threshold breach detected for this window.
    ``generated_at`` is the epoch seconds at which the engine ran.
    """

    window_seconds: float = 0.0
    sample_count: int = 0
    cpu: MetricStatistics = field(default_factory=MetricStatistics)
    memory: MetricStatistics = field(default_factory=MetricStatistics)
    swap: Optional[MetricStatistics] = None
    top_cpu_processes: List[ProcessInfo] = field(default_factory=list)
    top_memory_processes: List[ProcessInfo] = field(default_factory=list)
    alerts: List[AlertInfo] = field(default_factory=list)
    generated_at: float = 0.0

    @classmethod
    def empty(cls) -> "AnalyticsResult":
        """A result with no statistics, for empty history or errors."""
        return cls(
            window_seconds=0.0,
            sample_count=0,
            cpu=MetricStatistics(),
            memory=MetricStatistics(),
            swap=None,
            top_cpu_processes=[],
            top_memory_processes=[],
            alerts=[],
            generated_at=time.time(),
        )


# ---------------------------------------------------------------------- #
# Serialization helpers
# ---------------------------------------------------------------------- #
def as_dict(obj) -> dict:
    """Recursively convert a dataclass model to a plain ``dict``.

    Enums are kept as their enum members; use :func:`as_json` when a
    JSON-serializable representation is needed.
    """
    return asdict(obj)


def as_json(obj, *, indent: Optional[int] = 2) -> str:
    """Serialize a dataclass model to a JSON string.

    Enum members are serialized by their value (``str`` enums render as
    their string value). ``None`` fields render as JSON ``null``.
    """
    import json

    def _default(o):
        if isinstance(o, Enum):
            return o.value
        raise TypeError(f"not JSON serializable: {type(o).__name__}")

    return json.dumps(asdict(obj), default=_default, indent=indent,
                      sort_keys=False)


__all__ = [
    "AlertLevel",
    "ProcessState",
    "LoadAverages",
    "CPUInfo",
    "MemoryInfo",
    "SwapInfo",
    "ProcessInfo",
    "AlertInfo",
    "MetricStatistics",
    "SystemSnapshot",
    "AnalyticsResult",
    "as_dict",
    "as_json",
]
