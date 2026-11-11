// LinuxPulse C++ performance experiment (separate from the Python dashboard).
//
// This program is NOT the Python application and does not profile it. It reproduces, in C++,
// the *kinds* of computation LinuxPulse performs (statistics, rolling averages, process
// ranking, measurement aggregation) on deterministic synthetic data, so GCC + gprof can be
// demonstrated on a repeatable workload.
//
// Usage: benchmark [--size N] [--seed S] [--impl baseline|optimized]
//   --size N   workload scale (default 100). Every workload dimension is proportional to N.
//   --seed S   seed of the deterministic LCG generator (default 123456789).
//   --impl X   which implementation of the profiled hot spot to run (default baseline).
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#define NOINLINE __attribute__((noinline))   // keep functions visible in the gprof call graph

struct ProcessSample {
    int pid;
    std::string name;
    double cpu_percent;
    double memory_percent;
};

static bool g_optimized = false;

// Deterministic LCG; same sequence on every machine for a given seed.
struct Rng {
    uint32_t s;
    explicit Rng(uint32_t seed) : s(seed) {}
    NOINLINE uint32_t next() { s = s * 1664525u + 1013904223u; return s; }
    double pct() { return (next() >> 8) % 10000u / 100.0; }   // 0.00 .. 99.99
};

// ---- Workload 1: large-array statistics (mean, stddev, min, max, median) -----------------
struct Stats { double mean, stddev, min, max, median; };

NOINLINE Stats array_statistics(const std::vector<double>& v) {
    Stats st = {0, 0, v[0], v[0], 0};
    double sum = 0;
    for (double x : v) { sum += x; st.min = std::min(st.min, x); st.max = std::max(st.max, x); }
    st.mean = sum / v.size();
    double acc = 0;
    for (double x : v) acc += (x - st.mean) * (x - st.mean);
    st.stddev = std::sqrt(acc / v.size());
    std::vector<double> copy = v;
    std::sort(copy.begin(), copy.end());
    st.median = copy[copy.size() / 2];
    return st;
}

// ---- Workload 2: rolling average over a long series (window W) ---------------------------
NOINLINE std::vector<double> rolling_average(const std::vector<double>& v, size_t window) {
    std::vector<double> out(v.size());
    for (size_t i = 0; i < v.size(); ++i) {
        size_t start = i + 1 > window ? i + 1 - window : 0;
        double total = 0;
        for (size_t j = start; j <= i; ++j) total += v[j];
        out[i] = total / (i - start + 1);
    }
    return out;
}

// ---- Workload 3: process ranking (top-5 by CPU and by memory per snapshot) ---------------
// Ordering is total (ties broken by lower pid) so both implementations give identical output.
static inline bool ranks_before(const ProcessSample& a, const ProcessSample& b, bool by_cpu) {
    double x = by_cpu ? a.cpu_percent : a.memory_percent;
    double y = by_cpu ? b.cpu_percent : b.memory_percent;
    return x != y ? x > y : a.pid < b.pid;
}

// Baseline: copy every ProcessSample (each owns a std::string) and fully sort the copy.
NOINLINE std::vector<ProcessSample> top_processes_baseline(const std::vector<ProcessSample>& procs,
                                                           bool by_cpu, size_t limit) {
    std::vector<ProcessSample> ranked = procs;
    std::sort(ranked.begin(), ranked.end(), [by_cpu](const ProcessSample& a, const ProcessSample& b) {
        return ranks_before(a, b, by_cpu);
    });
    if (ranked.size() > limit) ranked.resize(limit);
    return ranked;
}

// Optimized: only the `limit` best are needed, so partially sort a vector of indices
// (no string copies, O(n log k)) and copy just the winners.
NOINLINE std::vector<ProcessSample> top_processes_optimized(const std::vector<ProcessSample>& procs,
                                                            bool by_cpu, size_t limit) {
    std::vector<uint32_t> idx(procs.size());
    for (size_t i = 0; i < idx.size(); ++i) idx[i] = (uint32_t)i;
    size_t k = std::min(limit, idx.size());
    std::partial_sort(idx.begin(), idx.begin() + k, idx.end(), [&](uint32_t a, uint32_t b) {
        return ranks_before(procs[a], procs[b], by_cpu);
    });
    std::vector<ProcessSample> out;
    for (size_t i = 0; i < k; ++i) out.push_back(procs[idx[i]]);
    return out;
}

NOINLINE std::vector<ProcessSample> top_processes(const std::vector<ProcessSample>& procs,
                                                  bool by_cpu, size_t limit) {
    return g_optimized ? top_processes_optimized(procs, by_cpu, limit)
                       : top_processes_baseline(procs, by_cpu, limit);
}

NOINLINE std::vector<ProcessSample> make_processes(Rng& rng, size_t count) {
    std::vector<ProcessSample> procs;
    for (size_t i = 0; i < count; ++i) {
        ProcessSample p;
        p.pid = 1000 + (int)i;
        p.name = "worker_" + std::to_string(i);
        p.cpu_percent = rng.pct() * 2.0;
        p.memory_percent = rng.pct();
        procs.push_back(p);
    }
    return procs;
}

// ---- Workload 4: per-core CPU / memory measurement aggregation ---------------------------
NOINLINE double aggregate_measurements(const std::vector<std::vector<double>>& per_core) {
    double total = 0; size_t n = 0;
    for (const auto& core : per_core) for (double x : core) { total += x; ++n; }
    return n ? total / n : 0.0;
}

static double now_s() {
    using namespace std::chrono;
    return duration<double>(steady_clock::now().time_since_epoch()).count();
}

int main(int argc, char** argv) {
    long size = 100;
    uint32_t seed = 123456789u;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--size") && i + 1 < argc) size = atol(argv[++i]);
        else if (!strcmp(argv[i], "--seed") && i + 1 < argc) seed = (uint32_t)strtoul(argv[++i], 0, 10);
        else if (!strcmp(argv[i], "--impl") && i + 1 < argc) {
            const char* m = argv[++i];
            if (!strcmp(m, "optimized")) g_optimized = true;
            else if (strcmp(m, "baseline")) { fprintf(stderr, "unknown --impl %s\n", m); return 2; }
        } else { fprintf(stderr, "usage: %s [--size N] [--seed S] [--impl baseline|optimized]\n", argv[0]); return 2; }
    }
    if (size <= 0) { fprintf(stderr, "--size must be positive\n"); return 2; }

    // Workload dimensions, all derived from --size.
    const size_t series_len = (size_t)size * 2000;   // samples in the long series
    const size_t window = 200;                       // rolling-average window
    const size_t snapshots = (size_t)size * 20;      // process snapshots to rank
    const size_t procs_per_snapshot = 250;
    const size_t cores = 64, core_samples = (size_t)size * 20;

    Rng rng(seed);
    double t0 = now_s();

    std::vector<double> series(series_len);
    for (auto& x : series) x = rng.pct();
    Stats st = array_statistics(series);
    double t1 = now_s();

    std::vector<double> roll = rolling_average(series, window);
    double roll_sum = 0; for (double x : roll) roll_sum += x;
    double t2 = now_s();

    long long rank_check = 0;
    double rank_only = 0;   // time inside top_processes() only (excludes make_processes)
    for (size_t s = 0; s < snapshots; ++s) {
        std::vector<ProcessSample> procs = make_processes(rng, procs_per_snapshot);
        double r0 = now_s();
        std::vector<ProcessSample> c = top_processes(procs, true, 5);
        std::vector<ProcessSample> m = top_processes(procs, false, 5);
        rank_only += now_s() - r0;
        for (const auto& p : c) rank_check += p.pid;
        for (const auto& p : m) rank_check += p.pid * 3;
    }
    double t3 = now_s();

    std::vector<std::vector<double>> per_core(cores, std::vector<double>(core_samples));
    for (auto& core : per_core) for (auto& x : core) x = rng.pct();
    double agg = aggregate_measurements(per_core);
    double t4 = now_s();

    // Deterministic results (compare these between runs/implementations).
    printf("size=%ld seed=%u impl=%s series_len=%zu window=%zu snapshots=%zu procs=%zu cores=%zu core_samples=%zu\n",
           size, seed, g_optimized ? "optimized" : "baseline", series_len, window, snapshots,
           procs_per_snapshot, cores, core_samples);
    printf("RESULT stats mean=%.6f stddev=%.6f min=%.2f max=%.2f median=%.2f\n",
           st.mean, st.stddev, st.min, st.max, st.median);
    printf("RESULT rolling sum=%.6f last=%.6f\n", roll_sum, roll.back());
    printf("RESULT ranking checksum=%lld\n", rank_check);
    printf("RESULT aggregate mean=%.6f\n", agg);
    // Wall-clock times (vary run to run).
    // ranking_phase = process generation + ranking; ranking_only = the top_processes() calls alone.
    printf("TIME stats=%.4f rolling=%.4f ranking_phase=%.4f ranking_only=%.4f aggregate=%.4f total=%.4f\n",
           t1 - t0, t2 - t1, t3 - t2, rank_only, t4 - t3, t4 - t0);
    return 0;
}
