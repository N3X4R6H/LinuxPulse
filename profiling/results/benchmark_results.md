# Benchmark Results

## 1. Environment

Measurements in this file were collected in the Linux build container. They are reference results, not guaranteed timings for the team's laptops.

- OS/kernel: Linux 6.18.57, x86_64
- Python: 3.13.5
- C++ compiler: g++ 14.2.0 (Debian)
- GNU gprof: GNU Binutils 2.44

## 2. C++ / gprof workload

Build and run from `profiling/cpp_benchmark/`:

```bash
make clean profile
```

Compiler flags: `-std=c++17 -Wall -Wextra -pedantic -O0 -pg`.

The benchmark runs 5,000 synthetic snapshots. Each snapshot creates 250 synthetic process records, retains at most 300 resource samples, ranks processes by CPU and memory, and evaluates alert thresholds.

| Output | Result |
|---|---:|
| Iterations | 5,000 |
| Retained history | 300 samples |
| Checksum | 60,757,944 |
| Alerts triggered | 1,310 |
| Final CPU mean | 50.10% |
| Final RAM rolling average | 44.20% |

The full flat profile and call graph are stored in `gprof_report.txt`. The profile highlights the process-ranking comparator and the STL sorting/partition path. This is consistent with sorting 250 process records twice per snapshot (once by CPU and once by memory).

The report uses 0.01-second sampling granularity. Small percentage differences should not be treated as precise measurements.

## 3. Python analytics workload

The Python benchmark calls the actual `analytics.engine.AnalyticsEngine`. It was run five times with 1,000 snapshots and 100 process records per snapshot:

```bash
python -m profiling.python_benchmark --iterations 1000 --processes 100
```

| Run | Elapsed time |
|---|---:|
| 1 | 0.344916 s |
| 2 | 0.346577 s |
| 3 | 0.358448 s |
| 4 | 0.338612 s |
| 5 | 0.359406 s |
| **Median** | **0.346577 s** |

Median throughput was approximately 2,885 snapshots/second in this container. Timing varies with machine load and interpreter version.

For Python function-level profiling, run:

```bash
python -m cProfile -s cumulative -m profiling.python_benchmark --iterations 1000 --processes 100
```

In one profiled run, the main cumulative-time areas were process normalization (`_normalise_processes` / `_normalise_process`), field extraction (`_read_field`), and top-process ranking (`heapq.nlargest`). Profiling itself adds overhead, so do not compare the profiled elapsed time with the unprofiled benchmark time.

## 4. Re-running on the team's machine

Run the commands above on the target Linux machine and record its CPU, OS, Python/GCC versions, flags, arguments, and multiple timing runs. Replace these reference measurements when the team obtains its own results.
