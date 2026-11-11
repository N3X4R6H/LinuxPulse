# Performance Analysis — C++ Benchmark with GCC and gprof

> Scope: this analysis concerns the standalone C++ benchmark in `profiling/cpp_benchmark/`.
> It is **not** a profile of the Python dashboard, and the speedups below must not be quoted as
> dashboard speedups. All numbers come from the files in `profiling/results/`.

## 1. Purpose
To demonstrate a genuine profile-guided optimization with GCC, `-pg` and gprof on computations
that mirror what LinuxPulse does (analytics and process ranking), using a reproducible workload.

## 2. Workload design
Deterministic (LCG random generator, fixed seed). `--size N` scales everything; N = 100:

| Workload | Mirrors | Parameters at N=100 |
|---|---|---|
| Large-array statistics | mean/stddev/min/max/median | 200,000 samples |
| Rolling average | analytics rolling mean | same series, window 200 (recomputed per point) |
| Process ranking | top-5 CPU and top-5 memory | 2,000 snapshots × 250 processes, ranked twice |
| Measurement aggregation | per-core CPU/memory averaging | 64 cores × 2,000 samples |

Each run prints `RESULT` lines (statistics, checksums) used to verify correctness and `TIME` lines
(wall-clock per phase, `std::chrono::steady_clock`).

## 3. Experimental setup
- Machine: Intel Core Ultra 5 226V, Linux 7.2.8 (Omarchy), x86_64 (recorded in `run_*.txt`).
- Compiler: `g++ -std=c++17 -Wall -Wextra -pedantic -O0` (+ `-pg` for the instrumented build); gprof from binutils.
- Profile: one instrumented run per implementation → `gprof_<impl>.txt`.
- Timing: 5 runs of the **un-instrumented** (`-O0`, no `-pg`) binary, median reported, because
  `-pg` itself makes the program ~8× slower (≈ 11 s vs ≈ 1.4 s).
- Parameters identical for both implementations: `--size 100 --seed 123456789`.

## 4. Baseline results and bottleneck
The flat profile (`gprof_baseline.txt`) is dominated by `_init` (unattributed overhead) and tiny
STL helpers, so it does not name a culprit directly. The call graph does. Inclusive share of the
1.33 s of sampled time:

| Function | Inclusive % |
|---|---:|
| `main` | 75.2 |
| **`top_processes`** (sort path included) | **43.7** |
| `make_processes` | 16.2 |
| `rolling_average` | 10.5 |
| `array_statistics` | ≈ 1.5 |

Un-instrumented wall-clock medians agree: the ranking calls alone take 0.843 s of 1.424 s total
(≈ 59 %), rolling average 0.235 s. **Bottleneck chosen: `top_processes`.**
Cause (from the code): each call copies all 250 `ProcessSample` structs, each owning a
`std::string`, then fully sorts the copy (`std::sort`, O(n log n)) to keep only 5 entries.
The many `std::string` helper rows in the flat profile (move assignment, `_M_set_length`, …) are
the footprint of that copying and element swapping.

One correction made before recording the final baseline: the comparator initially had no tie-break
and `std::sort` is unstable, so two implementations could legitimately pick different PIDs among
equal values. Ties are now broken by lower PID in both implementations, and the baseline was re-run
and re-profiled after that change; all numbers here are from that version.

## 5. Optimization
`top_processes_optimized` builds a vector of 32-bit indices and applies `std::partial_sort` for the
first k = 5 entries (O(n log k)), then copies only those 5 structs. No strings are copied or
swapped during ordering. Selected with `--impl optimized`; the baseline stays in the source for
comparison.

## 6. Final comparison (medians of 5 un-instrumented runs, N = 100)

| Metric | Baseline | Optimized | Speedup |
|---|---:|---:|---:|
| Ranking calls only (`ranking_only`) | 0.8431 s | 0.0420 s | 20.07× |
| Rolling average (unchanged code) | 0.2351 s | 0.2328 s | 1.01× (noise) |
| Whole program | 1.4241 s | 0.6031 s | 2.36× |

Correctness: `scripts/compare_profiles.sh` reports workload parameters identical and all `RESULT`
lines identical (ranking checksum 44994541 in both; stats, rolling and aggregate results equal).

Re-profiling the optimized build (`gprof_optimized.txt`, 0.56 s sampled): `top_processes` fell from
43.7 % to 3.8 % inclusive; the remaining leaders are `make_processes` (39.6 %) and
`rolling_average` (19.6 %) — the next candidates (the latter is O(N·window) and could use a
running sum), deliberately not touched in this experiment.

Why it is faster: the work per call dropped from ≈ n·log₂n ≈ 2,000 string-bearing moves/compares
to ≈ n·log₂5 index compares plus 5 copies, and the 250-element struct copy disappeared.
The whole-program gain (2.36×) is smaller than the function gain (20×) by Amdahl's law, since the
untouched parts remain.

## 7. Limitations
- One machine, one compiler version, `-O0` build; with `-O2` the relative costs would differ and
  the absolute gap would likely shrink. No `-O2` comparison was measured, so none is claimed.
- gprof is sampling-based with 10 ms resolution and heavy instrumentation overhead
  (see `profiling/README.md`); percentages are approximate and cover only ~1.3 s of the ~11 s run.
- Individual runs vary: baseline run 5 was noticeably slower (1.84 s total) than the others; medians
  are used for that reason. Only five runs were taken, so no statistical confidence interval is given.
- Synthetic data; real `top` output has different value distributions and ties.
- C++ results do not transfer to the Python dashboard.
