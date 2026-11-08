# LinuxPulse Analytics Methodology (Manish)

## 1. Purpose and assumptions

This document explains what the analytics engine calculates and why. CPU, RAM, and swap percentages are treated as instantaneous system-level measurements from each successful collector poll. Missing or invalid measurements are not replaced with zero because zero would mean the resource was measured and found idle.

The default history is the latest 300 polls. With a 1-second sampling interval this represents approximately 5 minutes; the time span changes if the sampling interval changes.

## 2. Descriptive statistics

For a resource with valid observations \(x_1, x_2, \ldots, x_n\), the arithmetic mean is

\[
\bar{x} = \frac{1}{n}\sum_{i=1}^{n}x_i.
\]

The minimum and maximum are

\[
x_{\min}=\min_i(x_i), \qquad x_{\max}=\max_i(x_i).
\]

These statistics are calculated over all valid observations currently retained in the 300-sample history. Missing values are skipped. The `valid_samples` field reports how many observations actually contributed to the result. If no valid observation exists, the result is `None`.

The mean gives a simple average load over the retained window. The minimum and maximum show the quietest and busiest measured points. They are descriptive statistics, not forecasts.

## 3. Rolling average

The default rolling window is the latest 10 polls. For the valid values in those latest polls, the rolling average is

\[
\bar{x}_{rolling} = \frac{1}{m}\sum_{i=1}^{m}x_i,
\]

where \(m\) is the number of valid measurements among the latest 10 polls. The window is defined by poll count, not elapsed wall-clock time. Missing measurements are ignored and the output includes `rolling_valid_samples` so consumers can see how much data contributed.

A rolling average reduces short-lived fluctuations and makes trends easier to read. It also introduces lag: after a sudden change, older samples remain in the average until they leave the window.

## 4. Top processes

The engine ranks the process records from the **latest poll only**:

- Top CPU processes: descending `cpu_percent`.
- Top memory processes: descending `memory_percent`.

Each list is limited to the configured `top_process_limit` (default 5). Records with a missing value for the relevant metric are excluded from that ranking. The implementation uses `heapq.nlargest` to select only the top K records instead of fully sorting all N processes. Its expected selection cost is approximately \(O(N \log K)\), compared with \(O(N \log N)\) for a full sort, when K is much smaller than N. This is a snapshot ranking, not a historical ranking; it does not imply that a process was consistently resource-heavy.

The collector's process CPU percentage may follow the convention used by `top`, including values above 100% on some multi-core reporting configurations. It is therefore not restricted to 0–100 in process records. System-wide CPU utilization is validated separately as 0–100%.

## 5. Alert thresholds

An alert becomes active when the newest valid system measurement is greater than or equal to its configured threshold:

| Resource | Default threshold | Condition |
|---|---:|---|
| CPU | 99% | `cpu_percent >= 99` |
| RAM | 85% | `ram_percent >= 85` |
| Swap | 90% | `swap_percent >= 90` |

The first version uses instantaneous threshold checks. An alert clears on the next poll where the measurement is below the threshold, and no alert is emitted when the measurement is missing. This gives predictable behavior and is easy to demonstrate with controlled test snapshots.

The thresholds are operational warning choices for this project, not universal definitions of system failure. CPU can legitimately remain highly utilized during computation; RAM use can include reclaimable cache; and swap use alone does not prove that the machine is actively swapping. A production monitor could later add persistence (for example, threshold exceeded for several consecutive samples), hysteresis (a lower clear threshold), and rates of change to reduce alert flapping.

## 6. Why `None` matters

The engine distinguishes three situations:

- `0`: a measurement was available and utilization was zero.
- A number such as `63.5`: a measurement was available and utilization had that value.
- `None`: the measurement was unavailable or invalid.

This distinction prevents failed collection from lowering an average or hiding an alert. It also allows plots to show gaps in the series.

## 7. Limitations

- Statistics describe only the retained history, not the machine's lifetime behavior.
- Rolling averages are sample-count based; irregular collection intervals can make them represent unequal time spans.
- Instantaneous alerts can flicker near a threshold.
- A top-process list depends on the collector's process sampling and percentage conventions.
- These metrics describe utilization, not root cause. High utilization alone does not identify which workload or system condition caused it.

## 8. Reproducible examples

For CPU samples `[20, 40, 60]`, mean is 40%, minimum is 20%, and maximum is 60%. With a rolling window of 2, the rolling average after the final sample is `(40 + 60) / 2 = 50%`.

A single snapshot with CPU 99%, RAM 85%, and swap 90% triggers all three alerts because the comparison is inclusive (`>=`). A later snapshot with CPU 50%, RAM 40%, and swap 20% clears all three alerts.
