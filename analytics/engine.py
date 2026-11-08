"""Bounded, thread-safe resource analytics for LinuxPulse.

The engine accepts either dictionaries or dataclass-like objects.  The
canonical snapshot shape is documented in docs/analytics_design.md.
No third-party packages are required.
"""

from collections import deque
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from heapq import nlargest
import math
import threading
from typing import Any, Deque, Dict, List, Optional, Sequence


_MISSING = object()


def _read_field(source: Any, *names: str, default: Any = None) -> Any:
    """Read the first available key/attribute from a dict or object."""
    if source is None:
        return default

    for name in names:
        try:
            if isinstance(source, Mapping):
                if name in source:
                    return source[name]
            else:
                value = getattr(source, name, _MISSING)
                if value is not _MISSING:
                    return value
        except Exception:
            # A broken property or custom mapping should not break collection.
            continue
    return default


def _to_number(value: Any) -> Optional[float]:
    """Convert a finite numeric value; reject booleans and malformed values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _to_system_percentage(value: Any) -> Optional[float]:
    """System utilization is expected to be between 0 and 100 percent."""
    number = _to_number(value)
    if number is None or number < 0.0 or number > 100.0:
        return None
    return number


def _percentage_from_bytes(used: Any, total: Any) -> Optional[float]:
    used_number = _to_number(used)
    total_number = _to_number(total)
    if used_number is None or total_number is None:
        return None
    if used_number < 0 or total_number < 0:
        return None
    if total_number == 0:
        # A known zero-sized resource (for example, no swap configured) has
        # no utilization to report. Treat it as unavailable, not 0% used.
        return None
    return _to_system_percentage((used_number / total_number) * 100.0)


def _normalise_timestamp(value: Any) -> str:
    """Return a timezone-aware ISO-8601 timestamp in UTC.

    Missing or malformed timestamps are replaced with the current UTC time so
    that an incomplete collector result can still be represented in history.
    """
    timestamp: Optional[datetime] = None

    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            timestamp = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            timestamp = None
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            timestamp = datetime.fromisoformat(text)
        except ValueError:
            timestamp = None

    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    elif timestamp.tzinfo is None:
        # A naive timestamp is interpreted as local-to-the-application UTC.
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)

    return timestamp.isoformat(timespec="milliseconds")


def _normalise_process(process: Any) -> Optional[Dict[str, Any]]:
    """Convert one process record to the stable analytics representation."""
    pid_value = _read_field(process, "pid", "process_id", default=None)
    pid_number = _to_number(pid_value)
    pid = (
        int(pid_number)
        if pid_number is not None and pid_number >= 0 and pid_number.is_integer()
        else None
    )

    name_value = _read_field(process, "name", "command", "cmd", "comm", default=None)
    name = str(name_value) if name_value is not None else None

    # Skip a completely unrecognisable record, but retain partial records.
    if pid is None and not name:
        return None

    cpu_value = _read_field(
        process, "cpu_percent", "percent_cpu", "cpu_usage_percent", "cpu", default=None
    )
    memory_value = _read_field(
        process,
        "memory_percent",
        "mem_percent",
        "percent_memory",
        "ram_percent",
        default=None,
    )
    state_value = _read_field(process, "state", "status", default=None)

    cpu_percent = _to_number(cpu_value)
    memory_percent = _to_system_percentage(memory_value)
    if cpu_percent is not None and cpu_percent < 0:
        cpu_percent = None

    return {
        "pid": pid,
        "name": name if name is not None else "Unknown",
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "state": str(state_value) if state_value is not None else None,
    }


def _normalise_processes(value: Any) -> List[Dict[str, Any]]:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        return []
    if not isinstance(value, Iterable):
        return []

    result: List[Dict[str, Any]] = []
    try:
        for process in value:
            try:
                normalised = _normalise_process(process)
            except Exception:
                # Ignore one malformed record and continue with the others.
                continue
            if normalised is not None:
                result.append(normalised)
    except Exception:
        # A partially broken iterable should not take down resource analytics.
        return result
    return result


class AnalyticsEngine:
    """Maintain bounded history and calculate system-resource analytics.

    Parameters are intentionally configurable so Ankush can pass the shared
    values from config.py when the application controller is integrated.
    """

    def __init__(
        self,
        history_size: int = 300,
        rolling_window: int = 10,
        cpu_threshold: float = 99.0,
        ram_threshold: float = 85.0,
        swap_threshold: float = 90.0,
        top_process_limit: int = 5,
    ) -> None:
        if not isinstance(history_size, int) or isinstance(history_size, bool) or history_size <= 0:
            raise ValueError("history_size must be a positive integer")
        if not isinstance(rolling_window, int) or isinstance(rolling_window, bool) or rolling_window <= 0:
            raise ValueError("rolling_window must be a positive integer")
        if not isinstance(top_process_limit, int) or isinstance(top_process_limit, bool) or top_process_limit <= 0:
            raise ValueError("top_process_limit must be a positive integer")

        self.history_size = history_size
        self.rolling_window = rolling_window
        self.top_process_limit = top_process_limit
        self.thresholds = {
            "cpu": self._validate_threshold("cpu_threshold", cpu_threshold),
            "ram": self._validate_threshold("ram_threshold", ram_threshold),
            "swap": self._validate_threshold("swap_threshold", swap_threshold),
        }

        # Only numeric resource samples are kept in history. Process records
        # are retained for the latest poll only, avoiding process-history bloat.
        self._history: Deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._latest_processes: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    @staticmethod
    def _validate_threshold(name: str, value: Any) -> float:
        number = _to_system_percentage(value)
        if number is None:
            raise ValueError("{} must be a finite percentage from 0 to 100".format(name))
        return number

    @staticmethod
    def _resource_value(container: Any, snapshot: Any, resource: str) -> Optional[float]:
        if resource == "cpu":
            value = _read_field(
                container,
                "usage_percent",
                "utilization_percent",
                "percent",
                "cpu_percent",
                default=_read_field(snapshot, "cpu_percent", "cpu_usage_percent", default=None),
            )
            return _to_system_percentage(value)

        if resource == "ram":
            value = _read_field(
                container,
                "usage_percent",
                "utilization_percent",
                "percent",
                "memory_percent",
                "ram_percent",
                default=_read_field(snapshot, "memory_percent", "ram_percent", default=None),
            )
            percentage = _to_system_percentage(value)
            if percentage is not None:
                return percentage
            used = _read_field(container, "used_bytes", "used", default=None)
            total = _read_field(container, "total_bytes", "total", default=None)
            return _percentage_from_bytes(used, total)

        value = _read_field(
            container,
            "usage_percent",
            "utilization_percent",
            "percent",
            "swap_percent",
            default=_read_field(snapshot, "swap_percent", "swap_usage_percent", default=None),
        )
        percentage = _to_system_percentage(value)
        if percentage is not None:
            return percentage
        used = _read_field(container, "used_bytes", "used", default=None)
        total = _read_field(container, "total_bytes", "total", default=None)
        return _percentage_from_bytes(used, total)

    def add_snapshot(self, snapshot: Any) -> Dict[str, Any]:
        """Add one collector snapshot and return the updated analytics result.

        Missing or malformed measurements are stored as None rather than zero.
        This prevents incomplete collector output from biasing averages or
        accidentally triggering alerts.
        """
        cpu_container = _read_field(snapshot, "cpu", default=None)
        ram_container = _read_field(snapshot, "memory", "ram", default=None)
        swap_container = _read_field(snapshot, "swap", default=None)

        sample = {
            "timestamp": _normalise_timestamp(_read_field(snapshot, "timestamp", "time", default=None)),
            "cpu_percent": self._resource_value(cpu_container, snapshot, "cpu"),
            "ram_percent": self._resource_value(ram_container, snapshot, "ram"),
            "swap_percent": self._resource_value(swap_container, snapshot, "swap"),
        }

        process_data = _read_field(snapshot, "processes", "process_list", default=None)
        processes = _normalise_processes(process_data)

        with self._lock:
            self._history.append(sample)
            self._latest_processes = processes
            return self._build_analytics_locked()

    def get_history(self) -> List[Dict[str, Any]]:
        """Return a copy of the retained resource history, oldest first."""
        with self._lock:
            return [dict(sample) for sample in self._history]

    def get_latest_processes(self) -> List[Dict[str, Any]]:
        """Return a copy of process records from the most recent poll."""
        with self._lock:
            return [dict(process) for process in self._latest_processes]

    def get_latest_sample(self) -> Optional[Dict[str, Any]]:
        """Return the newest resource sample, or None before the first poll."""
        with self._lock:
            if not self._history:
                return None
            return dict(self._history[-1])

    def get_analytics(self) -> Dict[str, Any]:
        """Return current values, statistics, top processes and active alerts."""
        with self._lock:
            return self._build_analytics_locked()

    def reset(self) -> None:
        """Clear history and current process data."""
        with self._lock:
            self._history.clear()
            self._latest_processes = []

    def _values_locked(self, key: str) -> List[float]:
        return [sample[key] for sample in self._history if sample[key] is not None]

    @staticmethod
    def _mean(values: Sequence[float]) -> Optional[float]:
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _round(value: Optional[float]) -> Optional[float]:
        return round(value, 2) if value is not None else None

    def _resource_statistics_locked(self, resource: str, key: str) -> Dict[str, Any]:
        values = self._values_locked(key)
        recent_samples = list(self._history)[-self.rolling_window :]
        rolling_values = [sample[key] for sample in recent_samples if sample[key] is not None]

        return {
            "current_percent": self._round(self._history[-1][key]) if self._history else None,
            "mean_percent": self._round(self._mean(values)),
            "minimum_percent": self._round(min(values)) if values else None,
            "maximum_percent": self._round(max(values)) if values else None,
            "rolling_average_percent": self._round(self._mean(rolling_values)),
            "valid_samples": len(values),
            "rolling_valid_samples": len(rolling_values),
            "threshold_percent": self.thresholds[resource],
        }

    def _rank_processes_locked(self, field: str) -> List[Dict[str, Any]]:
        known = (p for p in self._latest_processes if p[field] is not None)
        # Analytics only needs the top K entries, not a fully sorted process
        # table. nlargest is O(N log K), which is preferable when K is small.
        top = nlargest(self.top_process_limit, known, key=lambda process: process[field])
        return [dict(process) for process in top]

    def _active_alerts_locked(self) -> List[Dict[str, Any]]:
        if not self._history:
            return []

        latest = self._history[-1]
        alerts: List[Dict[str, Any]] = []
        labels = {"cpu": "CPU", "ram": "RAM", "swap": "Swap"}
        keys = {"cpu": "cpu_percent", "ram": "ram_percent", "swap": "swap_percent"}

        for resource in ("cpu", "ram", "swap"):
            value = latest[keys[resource]]
            threshold = self.thresholds[resource]
            if value is not None and value >= threshold:
                alerts.append(
                    {
                        "resource": resource,
                        "name": labels[resource],
                        "value_percent": self._round(value),
                        "threshold_percent": threshold,
                        "severity": "critical",
                        "message": "{} utilization is at or above {:.1f}%".format(labels[resource], threshold),
                    }
                )
        return alerts

    def _build_analytics_locked(self) -> Dict[str, Any]:
        if self._history:
            latest_timestamp = self._history[-1]["timestamp"]
        else:
            latest_timestamp = None

        resources = {
            "cpu": self._resource_statistics_locked("cpu", "cpu_percent"),
            "ram": self._resource_statistics_locked("ram", "ram_percent"),
            "swap": self._resource_statistics_locked("swap", "swap_percent"),
        }

        return {
            "sample_count": len(self._history),
            "history_limit": self.history_size,
            "rolling_window": self.rolling_window,
            "latest_timestamp": latest_timestamp,
            "resources": resources,
            "top_cpu_processes": self._rank_processes_locked("cpu_percent"),
            "top_memory_processes": self._rank_processes_locked("memory_percent"),
            "active_alerts": self._active_alerts_locked(),
        }
