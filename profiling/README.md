# profiling/ — C++ benchmark and GNU gprof

> **This is a separate performance experiment.** `cpp_benchmark/benchmark.cpp` is *not* part of the
> Python dashboard and does **not** profile it. It re-implements, in C++ on deterministic synthetic
> data, the kinds of computation LinuxPulse does (statistics, rolling averages, process ranking,
> measurement aggregation) so that GCC and gprof can be demonstrated on a repeatable workload.
> Conclusions apply to this C++ program only.

```
profiling/
├── README.md             this file
├── cpp_benchmark/
│   ├── benchmark.cpp     the workload (baseline + optimized process ranking)
│   └── Makefile          builds `benchmark` (-O0 -pg) and `benchmark_plain` (-O0)
└── results/              recorded evidence (run_*.txt, gprof_*.txt)
```

## Running it (from the repository root)

```bash
./scripts/profile.sh --impl baseline            # or: make profile
./scripts/profile.sh --impl optimized
./scripts/compare_profiles.sh                   # correctness check + median timings
./scripts/profile.sh --size 200 --runs 5        # bigger workload
```

Options: `--size N` (workload scale, default 100; all dimensions are proportional), `--seed S`,
`--impl baseline|optimized`, `--runs R` (un-instrumented timing repetitions).
The binary itself also takes `--size/--seed/--impl`. Needs `g++`, `gprof` (Arch: `gcc`, `binutils`).

Outputs: `results/run_<impl>.txt` (parameters, environment, program output, timings),
`results/gprof_<impl>.txt` (flat profile + call graph), and `cpp_benchmark/gmon.out`
(raw data, git-ignored, overwritten each run).

## Concepts

**GCC** is the compiler collection; `g++` compiles C++ to machine code. Flags used: `-O0` (no
optimization, so functions stay separate and visible), `-std=c++17 -Wall -Wextra -pedantic`.

**`-pg`** makes GCC insert a call to `mcount` at the start of every function. At run time that
records who called whom and how many times, and at exit the program writes `gmon.out`. A sampling
timer also interrupts the program (typically every 10 ms) to record which function is executing.

**`gmon.out`** is a binary file containing (1) a histogram of program-counter samples, i.e. where
time was spent, and (2) call-graph arcs with call counts. It carries no symbol names; gprof needs
the same binary to interpret it.

**gprof** (`gprof ./benchmark gmon.out`) combines the binary's symbols with `gmon.out` and prints
the flat profile and the call graph.

### Reading the flat profile
Columns: `% time` share of sampled time; `self seconds` time inside the function itself;
`calls`; `self/total ms/call` per-call time without/with callees. Sort order is by self time.
Use it to find *hot leaf work*. At `-O0`, C++ templates make this noisy: tiny STL helpers
(`string::size()`, `vector::operator[]`) rank high because they are called tens of millions of
times, and an `_init` row collects time gprof cannot attribute (profiling overhead).

### Reading the call graph
Each block is centred on one function (the line with `[n]`): callers are listed above it, callees
below. `self` = its own time, `children` = time in its callees, `% time` = *inclusive* share.
Use it to find which of **your** functions is responsible when time is scattered over STL
internals — e.g. `top_processes` is 43.7 % inclusive even though no single sort helper is.

### Limitations of sampling-based profiling
- Resolution is ~10 ms per sample; short functions or short runs give noisy percentages.
- `mcount` instrumentation slows the program a lot (here ≈ 8×: ~11 s instrumented vs ~1.4 s
  plain) and that overhead is mostly *not* sampled, so profile percentages cover only ~1.3 s of the
  ~11 s run. Never use instrumented time as a performance figure; time the `-pg`-free build.
- `-O0 -pg` distorts relative costs (calls that the optimizer would inline stay as calls).
- Only user-space CPU time of one process; I/O waits and kernel time are invisible.
- Call-graph attribution to callers assumes constant per-call cost (gprof's averaging).
- Results depend on machine and load; compare medians of repeated runs.
