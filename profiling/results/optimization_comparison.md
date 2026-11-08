# Optimization Comparison

## 1. C++ compiler optimization: `-O0` versus `-O2`

The same C++ benchmark source was compiled twice without profiling instrumentation. Both binaries used the same compiler, workload, and command-line argument (5,000 iterations).

```bash
g++ -std=c++17 -Wall -Wextra -pedantic -O0 -o benchmark_O0 benchmark.cpp
g++ -std=c++17 -Wall -Wextra -pedantic -O2 -o benchmark_O2 benchmark.cpp
```

Five runs were measured for each binary using a monotonic wall clock in the same Linux container.

| Run | `-O0` | `-O2` |
|---|---:|---:|
| 1 | 0.839687 s | 0.227014 s |
| 2 | 0.835944 s | 0.210123 s |
| 3 | 0.787920 s | 0.268329 s |
| 4 | 0.857844 s | 0.229398 s |
| 5 | 0.828693 s | 0.213149 s |
| **Median** | **0.835944 s** | **0.227014 s** |

The `-O2` median was approximately 3.68 times faster for this synthetic workload (about 72.8% less elapsed time). Both builds printed the same checksum (`60,757,944`), alert count (`1,310`), final CPU mean (`50.10%`), and RAM rolling average (`44.20%`). This supports that the optimization preserved the benchmark's observed outputs.

These are results for this benchmark and machine only. They should be repeated on the team's target machine before being used as a final project performance claim.

**Important:** use `-O0 -pg` for the `gprof` profiling build. The timing comparison above uses non-instrumented binaries. Do not compare a `-pg` runtime directly against a non-instrumented `-O2` runtime because profiling adds overhead.

## 2. Python analytics profiling

The C++ `gprof` report does not profile Python code. To profile the actual Python analytics engine, use:

```bash
python -m cProfile -s cumulative -m profiling.python_benchmark --iterations 1000 --processes 100
```

The observed hot paths in the supplied workload were process normalization, field extraction, and top-process ranking. This is useful diagnostic information, not proof that any one change is faster. For a defensible Python optimization comparison, preserve a baseline revision, run the same benchmark several times before and after the change, and compare medians while checking that outputs remain identical.

## 3. Interpretation

An optimization should be retained only when it preserves correctness and improves the relevant measured workload. Keep source revisions, compiler/interpreter versions, flags, workload size, commands, and repeated measurements with the final report.
