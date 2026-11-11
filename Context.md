# LINUXPULSE — Project Context

> **Project:** LINUXPULSE — Real-Time Linux System Monitoring & Performance Analytics Dashboard  
> **Institution:** Indian Institute of Technology Dharwad  
> **Domain:** Linux Systems Programming, Performance Analysis, Software Engineering  
> **Primary Language:** Python  
> **Target Operating System:** Arch Linux / Omarchy

---

## 1. Project Overview

LINUXPULSE is a desktop-based Linux system monitoring and performance analytics application designed to provide real-time visibility into system resource utilization and running processes.

The project combines Linux system monitoring utilities with a Python-based graphical interface to provide a centralized platform for observing, analyzing and visualizing system performance.

Traditional command-line utilities such as `top` provide useful system information but are limited in their ability to present long-term historical trends, consolidated statistical insights and graphical analytics.

LINUXPULSE addresses this by integrating:

- Linux system data acquisition.
- Process-level monitoring.
- Numerical analytics.
- Historical performance visualization.
- Threshold-based resource alerts.
- Performance benchmarking and profiling.

The application is designed as a modular system in which data acquisition, analytics, GUI development, visualization and application orchestration are separated into independent components.

## 2. Project Objectives

The primary objectives are:

1. Monitor CPU utilization in near real time.
2. Monitor RAM and swap utilization.
3. Retrieve system load averages and CPU core information.
4. Display running processes and their resource consumption.
5. Provide sorting and refreshing of process information.
6. Maintain historical resource utilization measurements.
7. Calculate statistical performance indicators using NumPy.
8. Visualize CPU and memory utilization using Matplotlib.
9. Generate alerts when resource thresholds are exceeded.
10. Demonstrate performance profiling and optimization using GCC and GNU gprof.
11. Develop a modular, testable and maintainable application.

## 3. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Main application language |
| Tkinter | Desktop GUI |
| ttk | GUI widgets and process table |
| NumPy | Statistical computation |
| Matplotlib | Historical data visualization |
| FigureCanvasTkAgg | Embedding Matplotlib inside Tkinter |
| Linux `top` | System and process monitoring |
| Python subprocess | Executing Linux monitoring commands |
| threading | Background data acquisition |
| queue | Thread-safe communication |
| C++ | Separate performance benchmark |
| GCC | Compilation and profiling instrumentation |
| GNU gprof | Performance profiling |
| Bash | Application automation |
| GNU Make | Build and task automation |
| unittest | Unit and integration testing |
| Git | Version control |

## 4. Functional Requirements

### 4.1 System Monitoring

The application monitors:

- CPU utilization.
- Number of CPU cores.
- Load averages over 1, 5 and 15 minutes.
- Total, used and available RAM.
- Total and used swap memory.

The default collection interval is two seconds.

### 4.2 Process Monitoring

The process monitoring component retrieves:

- PID.
- Process name.
- CPU utilization percentage.
- Memory utilization percentage.
- Process owner.
- Process state.

The process table supports resource-based sorting and periodic refreshing.

The monitoring implementation uses Linux `top` in batch mode through Python subprocess.

### 4.3 Historical Visualization

Matplotlib is embedded inside the Tkinter application using `FigureCanvasTkAgg`.

Historical graphs include:

- CPU utilization versus time.
- RAM utilization versus time.
- Swap utilization versus time, where implemented.

The application uses a bounded historical buffer to prevent unbounded memory growth.

Default historical capacity: 300 samples.

### 4.4 Statistical Analytics

NumPy is used to calculate:

- Mean resource utilization.
- Peak resource utilization.
- Minimum resource utilization.
- Standard deviation.
- Rolling averages.
- Highest CPU-consuming processes.
- Highest memory-consuming processes.

### 4.5 Threshold Alerts

Default resource thresholds:

| Resource | Threshold |
|---|---:|
| CPU | 80% |
| RAM | 85% |
| Swap | 80% |

Threshold values are configurable through centralized application configuration.

### 4.6 Mock Monitoring

The application supports a mock-data mode for testing and demonstrating the GUI and integration architecture without requiring live system measurements.

Mock measurements must remain distinguishable from actual system measurements.

## 5. System Architecture

LINUXPULSE follows a modular architecture.

```text
                  LINUX OPERATING SYSTEM
                            |
                            v
                    Linux top (batch)
                            |
                            v
                 +----------------------+
                 | Collector & Parser   |
                 |      Member 1        |
                 +----------------------+
                            |
                            v
                 +----------------------+
                 | Standardized Snapshot|
                 +----------------------+
                            |
                            v
                 +----------------------+
                 | Thread-Safe Queue    |
                 +----------------------+
                            |
                            v
                 +----------------------+
                 | Application          |
                 | Controller           |
                 |      Member 5        |
                 +----------------------+
                       /          \
                      /            \
                     v              v
           +----------------+  +----------------+
           | Analytics      |  | Tkinter GUI    |
           | Member 2       |  | Member 3       |
           +----------------+  +----------------+
                     |               |
                     v               v
           +----------------+  +----------------+
           | Statistics and |  | Live Metrics & |
           | Alerts         |  | Process Table  |
           +----------------+  +----------------+
                                     |
                                     v
                            +----------------+
                            | Matplotlib     |
                            | Visualization  |
                            | Member 4        |
                            +----------------+
```

## 6. Module Responsibilities

### Member 1 — Linux Data Acquisition Engineer

Responsible for:

- Linux monitoring through `top`.
- CPU, memory and swap collection.
- Process information collection.
- Parsing raw command output.
- Handling collection errors.
- Bash application launcher.
- Collector tests and documentation.

Main directory: `collector/`

### Member 2 — Analytics Engineer

Responsible for:

- NumPy-based statistical calculations.
- Historical measurement analysis.
- Rolling averages.
- Process ranking.
- Threshold alerts.
- Analytics tests and methodology documentation.

Main directory: `analytics/`

### Member 3 — GUI Engineer

Responsible for:

- Tkinter dashboard.
- System overview.
- Process monitoring table.
- Sorting and refreshing.
- GUI layout and user experience.
- Application screenshots and user-facing documentation contributions.

Main directory: `gui/`

### Member 4 — Visualization and QA Engineer

Responsible for:

- Matplotlib graph components.
- Tkinter and Matplotlib integration.
- Visualization updates.
- Integration and regression testing.
- Testing documentation.
- LaTeX report compilation.

Main directory: `visualization/`

### Member 5 — Systems Architect, Integration and Profiling Engineer

Responsible for:

- Application architecture.
- Shared data models.
- Centralized configuration.
- Application orchestration.
- Background worker coordination.
- Thread-safe queues.
- Mock monitoring integration.
- Build automation.
- C++ performance benchmark.
- GCC and gprof profiling workflow.
- Integration and release coordination.
- README consolidation.
- Beamer presentation preparation.

Main ownership: root-level application files, `profiling/`, integration documentation and release infrastructure.

## 7. Shared Data Contract

The application uses a standardized system snapshot to ensure compatibility between modules.

Logical representation:

```text
SystemSnapshot
├── timestamp
├── cpu
│   ├── usage
│   ├── cores
│   └── load_average
├── memory
│   ├── total
│   ├── used
│   ├── free
│   └── usage_percent
├── swap
│   ├── total
│   ├── used
│   └── usage_percent
└── processes[]
    ├── pid
    ├── name
    ├── cpu_percent
    ├── memory_percent
    ├── user
    └── state
```

The shared models are defined centrally in `models.py`.

Application settings are centralized in `config.py`.

This avoids inconsistent data structures, duplicated configuration values and unnecessary coupling between modules.

## 8. Threading and Data Flow

A major architectural requirement is keeping the GUI responsive during continuous monitoring.

The application follows this execution model:

1. A background worker performs data acquisition.
2. The collector produces standardized snapshots.
3. Snapshots are transferred through a thread-safe queue.
4. The application controller retrieves incoming measurements.
5. Analytics processes the measurements.
6. The GUI receives the latest system state.
7. Historical measurements are forwarded to visualization components.

### GUI Thread Safety

Tkinter and Matplotlib updates must occur on the GUI main thread.

The application uses Tkinter's `after()` scheduling mechanism to periodically poll the queue.

The background collector must never directly update Tkinter widgets or Matplotlib canvas objects.

The application also requires:

- Bounded queues.
- Bounded historical storage.
- Graceful shutdown.
- Proper background thread signaling.
- Error handling during collection and integration.

## 9. Configuration

Default application settings:

| Parameter | Default |
|---|---:|
| Sampling interval | 2 seconds |
| Historical buffer | 300 samples |
| CPU threshold | 80% |
| RAM threshold | 85% |
| Swap threshold | 80% |
| Default process count | 20 |
| Memory display | MiB |

Configuration is maintained centrally.

## 10. Performance Profiling

LINUXPULSE includes a separate C++ benchmark for demonstrating performance profiling.

The profiling workflow uses:

- GCC compilation.
- `-pg` instrumentation.
- Benchmark execution.
- `gmon.out` generation.
- GNU gprof analysis.
- Bottleneck identification.
- Code optimization.
- Before-and-after comparison.

The benchmark includes computational operations relevant to system analytics, such as numerical array processing, rolling averages and process ranking.

**Important distinction:** GNU gprof is used to profile the separate C++ benchmark. It does not directly profile the Python dashboard.

Profiling results must be based on actual benchmark execution and must not be fabricated.

## 11. Repository Structure

```text
linuxpulse/
│
├── main.py
├── config.py
├── models.py
├── requirements.txt
├── Makefile
├── README.md
├── .gitignore
│
├── collector/
│   ├── __init__.py
│   ├── top_collector.py
│   └── parser.py
│
├── analytics/
│   ├── __init__.py
│   └── engine.py
│
├── gui/
│   ├── __init__.py
│   ├── dashboard.py
│   └── process_table.py
│
├── visualization/
│   ├── __init__.py
│   └── plots.py
│
├── scripts/
│   ├── launch.sh
│   └── profile.sh
│
├── tests/
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_collector.py
│   ├── test_analytics.py
│   ├── test_visualization.py
│   └── test_integration.py
│
├── profiling/
│   ├── README.md
│   ├── cpp_benchmark/
│   │   ├── benchmark.cpp
│   │   └── Makefile
│   └── results/
│
├── docs/
│   ├── architecture.md
│   ├── integration_guide.md
│   ├── collector_design.md
│   ├── analytics_design.md
│   ├── visualization_design.md
│   ├── testing_strategy.md
│   ├── performance_analysis.md
│   ├── report.tex
│   └── presentation.tex
│
└── assets/
    └── screenshots/
```

## 12. Build and Execution

The project uses a root-level Makefile for common operations.

Expected commands:

```bash
make install
make run
make mock
make test
make profile
make clean
make help
```

Direct application execution:

```bash
python main.py
```

Mock execution:

```bash
python main.py --mock
```

Testing:

```bash
python -m unittest discover -s tests -v
```

Profiling:

```bash
./scripts/profile.sh
```

## 13. Testing Strategy

The testing strategy covers:

- Collector parsing and failure handling.
- Analytics calculations.
- Process ranking.
- Threshold alerts.
- Historical buffer management.
- Visualization data handling.
- Controller integration.
- Queue handling.
- Mock mode.
- Graceful application shutdown.

Unit tests should use controlled fixtures and mocked system command output.

Integration tests should verify data movement across module boundaries.

## 14. Design Constraints

- The application is intended for local Linux monitoring.
- The main application is Python-based.
- System process data is collected using Linux `top`.
- Tkinter is the GUI framework.
- Matplotlib is embedded in Tkinter.
- NumPy is used for analytics.
- The GUI must remain responsive.
- Historical storage must be bounded.
- Monitoring must not modify system processes.
- No process killing or priority modification is implemented.
- Mock data must not be confused with real measurements.
- The C++ profiling benchmark is independent of the Python runtime.

## 15. Project Scope

### Included

- CPU, RAM and swap monitoring.
- Process monitoring.
- Historical graphs.
- Statistical analytics.
- Resource alerts.
- Mock monitoring.
- Performance benchmark.
- GCC/gprof profiling.
- Unit and integration testing.
- Documentation and demonstration.

### Excluded

- Remote monitoring.
- Cloud monitoring.
- Kernel module development.
- Database-backed storage.
- Authentication.
- Predictive machine learning.
- Process termination and priority modification.

## 16. Future Scope

Possible future enhancements include:

- Disk I/O monitoring.
- Network utilization monitoring.
- Hardware temperature monitoring.
- CSV export.
- Configurable sampling intervals.
- Extended historical storage.
- Anomaly detection.
- Remote system monitoring.

---

**LINUXPULSE — Monitor. Analyze. Optimize.**