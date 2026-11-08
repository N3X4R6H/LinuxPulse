# LinuxPulse Analytics Design (Manish)

## 1. Purpose

The analytics module converts normalized system snapshots from `collector/` into useful historical statistics and alert information for the GUI and visualization modules. It does not execute `top`, parse terminal output, create widgets, or draw graphs.

The implementation lives in `analytics/engine.py` and exposes `AnalyticsEngine`.

## 2. Data flow

1. Atharv's collector obtains a system snapshot.
2. The application controller passes that snapshot to `AnalyticsEngine.add_snapshot(snapshot)`.
3. The engine normalizes CPU, RAM, swap, timestamp, and process fields.
4. Numeric resource samples enter a bounded history (`deque`, default maximum 300).
5. The engine calculates statistics and checks the newest sample against alert thresholds.
6. Dhiren reads the analytics result and latest process list; Pavan reads history for plots.

The engine is independent of Tkinter and Matplotlib. It uses only the Python standard library.

## 3. Snapshot input contract

The preferred snapshot shape is a dictionary or dataclass-like object with these fields. Dataclass attributes and dictionary keys are both accepted.

```python
snapshot = {
    "timestamp": "2026-11-08T12:00:00+00:00",  # datetime, ISO string, or Unix time
    "cpu": {
        "usage_percent": 42.5,
        "core_count": 8,
        "load_average": [0.5, 0.7, 0.8],
    },
    "memory": {
        "usage_percent": 61.0,  # OR used_bytes and total_bytes
        "used_bytes": 6400000000,
        "total_bytes": 16000000000,
    },
    "swap": {
        "usage_percent": 10.0,  # OR used_bytes and total_bytes
        "used_bytes": 1000000000,
        "total_bytes": 10000000000,
    },
    "processes": [
        {
            "pid": 1234,
            "name": "python worker",
            "cpu_percent": 12.5,
            "memory_percent": 3.2,
            "state": "R",
        }
    ],
}
```

CPU core count and load average are retained as collector/system information, not analytics time series. For this version, analytics consumes `cpu.usage_percent`, `memory.usage_percent`, and `swap.usage_percent`. RAM and swap percentages can instead be calculated from byte counts if the percentage field is absent.

The canonical process fields are `pid`, `name`, `cpu_percent`, `memory_percent`, and `state`. The engine also recognizes common aliases such as `process_id`, `command`, `mem_percent`, and `status`. Process names are kept as strings without shell interpretation or character stripping.

**Integration item for Ankush and Atharv:** please align `models.py` and the collector output with the canonical names above. The engine accepts dictionaries or attribute-based objects, but a single shared contract is preferable to accumulating aliases.

## 4. Public API

```python
from analytics import AnalyticsEngine

engine = AnalyticsEngine(
    history_size=300,
    rolling_window=10,
    cpu_threshold=99.0,
    ram_threshold=85.0,
    swap_threshold=90.0,
    top_process_limit=5,
)

result = engine.add_snapshot(snapshot)  # add one sample and return analytics
history = engine.get_history()          # oldest to newest, bounded
processes = engine.get_latest_processes()
latest = engine.get_latest_sample()
result = engine.get_analytics()
engine.reset()
```

The constructor values should be passed from Ankush's shared `config.py` when the application controller is connected.

## 5. Analytics result contract

`get_analytics()` and `add_snapshot()` return a dictionary with this shape:

```python
{
    "sample_count": 12,
    "history_limit": 300,
    "rolling_window": 10,
    "latest_timestamp": "2026-11-08T12:00:00.000+00:00",
    "resources": {
        "cpu": {
            "current_percent": 42.5,
            "mean_percent": 38.2,
            "minimum_percent": 20.0,
            "maximum_percent": 75.0,
            "rolling_average_percent": 40.1,
            "valid_samples": 12,
            "rolling_valid_samples": 10,
            "threshold_percent": 99.0,
        },
        "ram": {"current_percent": 61.0, "mean_percent": 59.0},
        "swap": {"current_percent": 10.0, "mean_percent": 8.0},
    },
    "top_cpu_processes": [],
    "top_memory_processes": [],
    "active_alerts": [],
}
```

The abbreviated RAM and swap objects above are illustrative; the implementation returns the same complete statistics fields for all three resources. Values are rounded to two decimal places. A statistic is `None` when there are no valid measurements for it.

`get_history()` returns records with `timestamp`, `cpu_percent`, `ram_percent`, and `swap_percent`. This is the intended input for Pavan's time-series graphs. Missing metrics remain `None` so a graph can display a gap rather than a false zero.

`get_latest_processes()` returns the current poll's normalized process records. Process lists are not copied into every historical sample; only the most recent process list is retained, while resource history is bounded by `history_size`.

## 6. Threading

The engine protects its history and current process list with an `RLock`. This allows the collector/controller thread to add a sample while the GUI thread reads an analytics snapshot. The GUI must still update Tkinter widgets only on Tkinter's main thread; the application controller should use a queue or `after()` callback for that handoff.

## 7. Error and incomplete-data behavior

- Missing resource fields become `None`, not zero.
- Non-finite, malformed, negative, or out-of-range system percentages are ignored.
- RAM/swap can be calculated as `used_bytes / total_bytes * 100` when both byte values are valid and total is greater than zero.
- A zero-sized resource is unavailable (`None`), not 0% utilized.
- Missing or malformed timestamps are replaced with the current UTC time.
- Empty or malformed process collections become an empty list; individually malformed process records are skipped.
- Process names containing spaces, punctuation, Unicode, or shell-like characters are preserved as data.
- Each new poll replaces the current process list, including replacing it with an empty list.

## 8. Memory bounds

Resource history uses `collections.deque(maxlen=history_size)`. When the maximum is reached, the oldest sample is discarded automatically. The process list is retained only for the latest poll, not for every historical sample. The configured top-process output is also capped by `top_process_limit`. The engine uses `heapq.nlargest` because it needs only a small top-K list; it does not need to sort the entire process collection. This gives approximately \(O(N \log K)\) selection cost instead of \(O(N \log N)\) full sorting when \(K\) is small.
