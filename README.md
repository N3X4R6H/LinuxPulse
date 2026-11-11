# LINUXPULSE
### Real-Time Linux System Monitoring & Performance Analytics Dashboard

<p align="center">
  <strong>A lightweight, real-time system monitoring and performance analytics application for Linux.</strong>
</p>

---

## How to run:
./run.sh              # start with live data (Linux and macOS)
./run.sh --demo       # force demo data (--mock and --interval 1 also work)
./run.sh test         # run all unit tests
./run.sh clean        # delete .venv to start fresh

## Overview

**LINUXPULSE** is a desktop-based Linux system monitoring and performance analytics application designed to provide real-time visibility into system resource utilization and running processes.

The application combines Linux system monitoring utilities with a Python-based graphical interface to present system performance information in an intuitive and structured manner.

Unlike traditional terminal-based monitoring utilities, LINUXPULSE provides a centralized dashboard featuring live resource metrics, process-level monitoring, historical visualization, statistical analytics, and configurable resource alerts.

The project also incorporates a separate C++ performance benchmarking experiment using GCC and GNU gprof to demonstrate profiling, bottleneck identification, and optimization techniques.

## Objectives

- Monitor Linux system resources in near real time.
- Display CPU, RAM, swap and system load information.
- Track running processes and their resource consumption.
- Visualize historical system performance.
- Apply numerical analysis to resource utilization data.
- Identify resource-intensive processes.
- Generate alerts when configurable thresholds are exceeded.
- Demonstrate performance profiling and optimization using GCC and gprof.

## Features

### 1. Real-Time System Monitoring

Monitor important system-level metrics:

| Metric | Description |
|---|---|
| CPU utilization | Overall CPU usage percentage |
| CPU cores | Number of available logical CPU cores |
| Load average | System load over 1, 5 and 15 minutes |
| RAM utilization | Total, used and available memory |
| Swap utilization | Total and used swap memory |

The default monitoring interval is **2 seconds**.

### 2. Process Monitoring

LINUXPULSE provides a live process table containing:

| Attribute | Description |
|---|---|
| PID | Process identifier |
| Process name | Name of the running process |
| CPU % | CPU consumption |
| Memory % | Memory consumption |
| User | Process owner |
| State | Current process state |

Additional functionality:

- Sort processes by CPU utilization.
- Sort processes by memory utilization.
- Refresh process information automatically.
- Identify resource-intensive processes.
- Handle processes that appear or disappear during monitoring.

### 3. Historical Performance Visualization

The application uses Matplotlib embedded inside the Tkinter interface to visualize resource utilization over time.

Available visualizations:

- CPU utilization versus time.
- RAM utilization versus time.
- Swap utilization versus time (where implemented).

The application maintains a bounded historical buffer to prevent unbounded memory consumption.

Default historical capacity: **300 samples**.

### 4. Statistical Analytics

NumPy is used to perform numerical analysis on collected system measurements.

Supported analytical metrics include:

- Mean CPU utilization.
- Peak CPU utilization.
- Minimum CPU utilization.
- CPU standard deviation.
- Mean RAM utilization.
- Peak RAM utilization.
- Minimum RAM utilization.
- RAM standard deviation.
- Rolling averages.
- Top CPU-consuming processes.
- Top memory-consuming processes.

### 5. Resource Threshold Alerts

LINUXPULSE supports configurable resource utilization thresholds.

Default configuration:

| Resource | Alert threshold |
|---|---:|
| CPU | 80% |
| RAM | 85% |
| Swap | 80% |

Alerts help identify potentially overloaded system resources.

### 6. Performance Profiling

The project includes a separate C++ performance benchmark designed around computational workloads relevant to system analytics.

The benchmark uses:

- GCC for compilation.
- `-pg` instrumentation.
- GNU gprof for profiling.
- Before-and-after optimization comparisons.

The profiling experiment demonstrates how computational bottlenecks can be identified and optimized.

**Important:** GNU gprof profiles the separate C++ benchmark. It is not used to directly profile the Python dashboard.

### 7. Mock Monitoring Mode

A mock-data mode allows the application to be tested without depending on live system measurements.

It is useful for:

- Independent GUI development.
- Integration testing.
- Demonstrating dashboard behavior.
- Testing analytics and visualization components.

Mock measurements are explicitly distinguished from real system measurements.

---

## System Architecture

LINUXPULSE follows a modular architecture that separates system data acquisition, analytics, visualization and user interface responsibilities.

```text
                 LINUX OPERATING SYSTEM
                           |
                           v
                 Linux top (batch mode)
                           |
                           v
                 +-------------------+
                 | System Collector  |
                 |    Member 1       |
                 +-------------------+
                           |
                           v
                 +-------------------+
                 | Snapshot Parser   |
                 +-------------------+
                           |
                           v
                 +-------------------+
                 | Thread-Safe Queue |
                 +-------------------+
                           |
                           v
                 +-------------------+
                 | Application       |
                 | Controller        |
                 |    Member 5       |
                 +-------------------+
                      /          \
                     /            \
                    v              v
          +----------------+  +----------------+
          | Analytics      |  | Tkinter GUI    |
          | Member 2       |  | Member 3       |
          +----------------+  +----------------+
                    |              |
                    v              v
          +----------------+  +----------------+
          | Statistics &   |  | Live Metrics & |
          | Alerts         |  | Process Table  |
          +----------------+  +----------------+
                                   |
                                   v
                          +----------------+
                          | Matplotlib     |
                          | Visualization  |
                          | Member 4       |
                          +----------------+
```

### Application Data Flow

1. Linux system information is collected using `top` in batch mode.
2. The collector parses raw monitoring output.
3. Measurements are converted into standardized system snapshots.
4. Snapshots are transferred through a thread-safe queue.
5. The application controller coordinates data distribution.
6. The analytics engine processes measurements and maintains historical statistics.
7. Tkinter displays live system information and process data.
8. Matplotlib updates historical resource utilization graphs.

### Threading Architecture

To maintain GUI responsiveness:

- Data acquisition runs in a background thread.
- A thread-safe queue transfers measurements.
- Tkinter's `after()` mechanism periodically processes incoming snapshots.
- All Tkinter widget updates happen on the GUI main thread.
- Matplotlib updates also happen on the GUI main thread.
- Historical data is maintained using a bounded buffer.

This prevents system monitoring operations from blocking the graphical interface.

---

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Main application development |
| Tkinter | Graphical user interface |
| NumPy | Numerical computation and analytics |
| Matplotlib | Historical performance visualization |
| Linux `top` | System and process monitoring |
| Python subprocess | Executing Linux monitoring utilities |
| C++ | Performance benchmark |
| GCC | C++ compilation and instrumentation |
| GNU gprof | Performance profiling |
| Bash | Application launcher and automation |
| GNU Make | Build and task automation |
| unittest | Unit and integration testing |
| Git | Version control |

---

## Project Structure

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
│   ├── check_env.sh
│   ├── profile.sh
│   ├── compare_profiles.sh
│   └── (launch.sh — planned, Member 1)
│
├── tests/
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_collector.py
│   ├── test_analytics.py
│   ├── test_visualization.py
│   ├── test_controller.py
│   ├── test_integration.py
│   └── test_gui_integration.py
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
│   ├── presentation.tex
│
└── assets/
    └── screenshots/
```

---

## Installation

### Prerequisites

LINUXPULSE is primarily developed and tested for Linux environments.

Required tools:

- Python 3
- pip
- Tkinter
- GNU Make
- GCC / G++
- GNU gprof
- Linux `top`

For Arch Linux / Omarchy:

```bash
sudo pacman -S python python-pip tk gcc make binutils procps-ng
```

`gprof` ships in `binutils` on Arch (there is no separate `gprof` package); `top` comes from `procps-ng`.

### Clone the Repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd linuxpulse
```

Replace the placeholder with the actual repository URL.

### Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Quick Setup with Make

```bash
make install   # creates .venv, installs requirements.txt (never calls sudo)
make check     # verifies Python, Tkinter, NumPy, Matplotlib, gcc, gprof, top, make
```

See `docs/setup.md` for Arch / Omarchy notes.

### Verify the Environment

```bash
python -m tkinter
```

This should open a small Tkinter test window.

Also verify:

```bash
top --version
gcc --version
gprof --version
make --version
```

---

## Running the Application

### Real Monitoring Mode

Launch LINUXPULSE using:

```bash
python main.py
```

Alternatively, use the launcher that creates the virtual environment for you:

```bash
./run.sh            # live data      (./run.sh --mock for simulated data)
```

(`scripts/launch.sh` is planned by Member 1 and is not in the repository yet; `make run` / `make mock`
and `./run.sh` are the supported launch paths.)

### Mock Monitoring Mode

To launch the application with simulated system measurements:

```bash
python main.py --mock
```

Mock mode is intended for GUI testing and demonstrations.

---

## Build Automation

LINUXPULSE provides a GNU Make-based workflow.

| Command | Description |
|---|---|
| `make help` | Display available commands |
| `make install` | Install Python dependencies |
| `make run` | Launch real monitoring mode |
| `make mock` | Launch mock monitoring mode |
| `make test` | Run the test suite |
| `make profile` | Execute the profiling workflow |
| `make clean` | Remove generated temporary files |

Run a command using:

```bash
make <target>
```

---

## Testing

The project uses Python's built-in `unittest` framework.

### Run All Tests

```bash
python -m unittest discover -s tests -v
```

Alternatively:

```bash
make test
```

### Testing Strategy

The testing process covers:

**Collector tests**
- Parsing monitoring output.
- Handling missing fields.
- Handling malformed output.
- Handling command failures.
- Handling empty process lists.

**Analytics tests**
- Mean and peak calculations.
- Rolling averages.
- Process ranking.
- Threshold alerts.
- Historical buffer limits.

**Visualization tests**
- Historical sample handling.
- Empty data handling.
- Graph update behavior.

**Integration tests**
- Snapshot delivery.
- Queue handling.
- Controller coordination.
- Mock monitoring.
- Shutdown behavior.

Unit tests should use controlled fixtures and mocked command outputs rather than depending on actual system load.

---

## Performance Profiling

LINUXPULSE includes a separate C++ benchmark to demonstrate performance profiling and optimization.

### Profiling Workflow

```text
C++ Benchmark
     |
     v
GCC Compilation (-pg)
     |
     v
Benchmark Execution
     |
     v
gmon.out Generation
     |
     v
GNU gprof Analysis
     |
     v
Bottleneck Identification
     |
     v
Code Optimization
     |
     v
Reprofiling and Comparison
```

### Run Profiling

```bash
chmod +x scripts/profile.sh
./scripts/profile.sh
```

Alternatively:

```bash
make profile
```

### Profiling Concepts

| Tool | Purpose |
|---|---|
| GCC | Compiles the benchmark |
| `-pg` | Enables profiling instrumentation |
| `gmon.out` | Stores profiling data |
| gprof | Analyzes execution-time distribution and function calls |

The profiling experiment compares an original implementation with an optimized implementation under equivalent workload conditions.

Results should be documented in:

```text
profiling/results/
docs/performance_analysis.md
```

Actual benchmark results must be generated through execution rather than assumed or fabricated.

---

## Configuration

Important application settings are centralized in `config.py`.

| Configuration | Default |
|---|---:|
| Sampling interval | 2 seconds |
| Historical buffer | 300 samples |
| CPU threshold | 80% |
| RAM threshold | 85% |
| Swap threshold | 80% |
| Default process count | 20 |
| Memory display unit | MiB |

These settings can be modified according to monitoring requirements.

---

## Screenshots

Application screenshots will be maintained in:

```text
assets/screenshots/
```

Suggested screenshots:

1. Main dashboard showing live CPU, RAM and swap utilization.
2. Process monitoring table.
3. Historical CPU and RAM graphs.
4. Analytics and threshold alerts.
5. Mock monitoring mode.

<p align="center">
  <i>Application screenshots will be added after final GUI integration.</i>
</p>

---

## Team Responsibilities

LINUXPULSE is developed collaboratively by a five-member team.

| Member | Role | Responsibilities |
|---|---|---|
| Member 1 | Linux Data Acquisition Engineer | Linux monitoring, process collection, parsing and launcher |
| Member 2 | Analytics Engineer | NumPy-based analytics, historical statistics and alerts |
| Member 3 | GUI Engineer | Tkinter dashboard, process table and user experience |
| Member 4 | Visualization & QA Engineer | Matplotlib graphs, integration tests and technical report |
| Member 5 | Systems Architect & Integration Engineer | Architecture, shared interfaces, application orchestration, profiling, automation and release |

---

## Academic Context

**Institution:** Indian Institute of Technology Dharwad

**Project:** LINUXPULSE — Real-Time Linux System Monitoring and Performance Analytics Dashboard

**Project Domain:** Linux Systems Programming, Performance Analysis and Software Engineering

The project demonstrates practical application of:

- Linux process and system monitoring.
- Python application architecture.
- Multithreaded programming.
- GUI development.
- Numerical computing.
- Data visualization.
- Software testing.
- Performance profiling.
- Code optimization.
- Build automation.

---

## Scope and Limitations

### In Scope

- Local Linux system monitoring.
- CPU, RAM and swap statistics.
- Process-level resource monitoring.
- Historical performance graphs.
- Statistical analytics.
- Threshold-based alerts.
- Performance benchmarking and profiling.

### Out of Scope

- Remote system monitoring.
- Cloud-based monitoring.
- Kernel module development.
- Process termination or priority modification.
- Predictive machine learning.
- Database-backed historical storage.
- User authentication.

---

## Future Improvements

Potential extensions include:

- CSV export of monitoring history.
- Process search and filtering.
- Configurable monitoring intervals.
- Extended historical data storage.
- Network monitoring.
- Disk I/O monitoring.
- Temperature and hardware sensor monitoring.
- Anomaly detection.
- Remote monitoring support.

These features are outside the initial project scope unless implemented after all mandatory requirements are satisfied.

---

## License

This project was developed for academic and educational purposes.

A formal open-source license can be added by the project maintainers.

---

<p align="center">
  <strong>LINUXPULSE</strong><br/>
  <i>Monitor. Analyze. Optimize.</i>
</p>