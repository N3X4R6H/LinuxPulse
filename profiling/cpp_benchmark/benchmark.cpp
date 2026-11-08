#include <algorithm>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>
#include <deque>

struct ProcessSample {
    int pid;
    std::string name;
    double cpu_percent;
    double memory_percent;
};

struct ResourceSample {
    double cpu_percent;
    double ram_percent;
    double swap_percent;
};

struct AlertCounts {
    int cpu;
    int ram;
    int swap;
};

static const std::size_t HISTORY_LIMIT = 300;
static const std::size_t ROLLING_WINDOW = 10;

// Keep the functions visible in the gprof call graph in normal GCC builds.
#if defined(__GNUC__)
#define NOINLINE __attribute__((noinline))
#else
#define NOINLINE
#endif

NOINLINE void add_sample(std::deque<ResourceSample>& history,
                         const ResourceSample& sample) {
    if (history.size() == HISTORY_LIMIT) {
        history.pop_front();
    }
    history.push_back(sample);
}

NOINLINE double mean_cpu(const std::deque<ResourceSample>& history) {
    if (history.empty()) {
        return 0.0;
    }
    double total = 0.0;
    for (std::deque<ResourceSample>::const_iterator it = history.begin();
         it != history.end(); ++it) {
        total += it->cpu_percent;
    }
    return total / static_cast<double>(history.size());
}

NOINLINE double rolling_ram_average(const std::deque<ResourceSample>& history) {
    if (history.empty()) {
        return 0.0;
    }
    const std::size_t start = history.size() > ROLLING_WINDOW
        ? history.size() - ROLLING_WINDOW : 0;
    double total = 0.0;
    std::size_t count = 0;
    for (std::size_t i = start; i < history.size(); ++i) {
        total += history[i].ram_percent;
        ++count;
    }
    return count == 0 ? 0.0 : total / static_cast<double>(count);
}

NOINLINE std::vector<ProcessSample> top_processes(
    const std::vector<ProcessSample>& processes,
    bool rank_by_cpu,
    std::size_t limit) {
    std::vector<ProcessSample> ranked = processes;
    if (rank_by_cpu) {
        std::sort(ranked.begin(), ranked.end(),
                  [](const ProcessSample& a, const ProcessSample& b) {
                      return a.cpu_percent > b.cpu_percent;
                  });
    } else {
        std::sort(ranked.begin(), ranked.end(),
                  [](const ProcessSample& a, const ProcessSample& b) {
                      return a.memory_percent > b.memory_percent;
                  });
    }
    if (ranked.size() > limit) {
        ranked.resize(limit);
    }
    return ranked;
}

NOINLINE AlertCounts check_alerts(const ResourceSample& sample) {
    AlertCounts alerts = {0, 0, 0};
    alerts.cpu = sample.cpu_percent >= 99.0 ? 1 : 0;
    alerts.ram = sample.ram_percent >= 85.0 ? 1 : 0;
    alerts.swap = sample.swap_percent >= 90.0 ? 1 : 0;
    return alerts;
}

static unsigned int next_random(unsigned int& state) {
    state = state * 1664525u + 1013904223u;
    return state;
}

int main(int argc, char** argv) {
    int iterations = 5000;
    if (argc > 1) {
        int requested = std::atoi(argv[1]);
        if (requested > 0) {
            iterations = requested;
        }
    }

    std::deque<ResourceSample> history;
    std::vector<ProcessSample> processes;
    processes.reserve(250);
    unsigned int random_state = 123456789u;
    long long checksum = 0;
    long long alert_total = 0;

    for (int iteration = 0; iteration < iterations; ++iteration) {
        ResourceSample sample;
        sample.cpu_percent = static_cast<double>(next_random(random_state) % 10000u) / 100.0;
        sample.ram_percent = static_cast<double>(next_random(random_state) % 10000u) / 100.0;
        sample.swap_percent = static_cast<double>(next_random(random_state) % 10000u) / 100.0;
        add_sample(history, sample);

        processes.clear();
        for (int i = 0; i < 250; ++i) {
            ProcessSample process;
            process.pid = 1000 + i;
            process.name = "worker_" + std::to_string(i);
            process.cpu_percent = static_cast<double>(next_random(random_state) % 20000u) / 100.0;
            process.memory_percent = static_cast<double>(next_random(random_state) % 10000u) / 100.0;
            processes.push_back(process);
        }

        std::vector<ProcessSample> cpu_top = top_processes(processes, true, 5);
        std::vector<ProcessSample> memory_top = top_processes(processes, false, 5);
        AlertCounts alerts = check_alerts(sample);

        checksum += static_cast<long long>(mean_cpu(history) * 100.0);
        checksum += static_cast<long long>(rolling_ram_average(history) * 100.0);
        checksum += cpu_top.empty() ? 0 : cpu_top[0].pid;
        checksum += memory_top.empty() ? 0 : memory_top[0].pid;
        alert_total += alerts.cpu + alerts.ram + alerts.swap;
    }

    std::cout << "Iterations: " << iterations << '\n';
    std::cout << "Retained history samples: " << history.size() << '\n';
    std::cout << "Checksum: " << checksum << '\n';
    std::cout << "Alerts triggered: " << alert_total << '\n';
    std::cout << std::fixed << std::setprecision(2)
              << "Final CPU mean: " << mean_cpu(history) << "%\n"
              << "Final RAM rolling average: " << rolling_ram_average(history) << "%\n";
    return 0;
}
