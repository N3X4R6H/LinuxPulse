
# Collector Module Design

## 1. Overview

The collector module is responsible for gathering system performance information and converting raw system data into structured Python data.

It collects the following information:

- CPU utilization
- Number of CPU cores
- CPU load averages
- RAM usage
- Swap usage
- Running process information

The collected data is passed to other modules for further analysis and visualization.

## 2. Module Structure

The collector module contains two main Python files:

```text
collector/
├── __init__.py
├── parser.py
└── top_collector.py
```

### 2.1 parser.py

This file contains functions that parse raw system information and convert it into Python dictionaries and lists.

The main functions are:

- `parse_loadavg()`
- `parse_cpu_stat()`
- `parse_meminfo()`
- `parse_processes()`
- `calculate_cpu_usage()`

### 2.2 top_collector.py

This file is responsible for collecting system information from the operating system.

The main functions are:

- `collect_cpu()`
- `collect_memory()`
- `collect_processes()`
- `collect_system_data()`

## 3. Data Collection Methods

### 3.1 CPU Information

CPU statistics are collected from the Linux `/proc/stat` file.

The collector reads cumulative CPU time counters such as:

- User time
- Nice time
- System time
- Idle time
- I/O wait time
- Hardware interrupt time
- Software interrupt time
- Steal time

CPU utilization is calculated by comparing two consecutive readings.

The number of CPU cores is obtained using Python's `os.cpu_count()` function.

### 3.2 Load Average

Load average is collected from `/proc/loadavg`.

The collector extracts the system load averages for:

- Last 1 minute
- Last 5 minutes
- Last 15 minutes

These values indicate the average system load over the respective time periods.

### 3.3 Memory Information

RAM and swap information are collected from `/proc/meminfo`.

The collector extracts the total, free and available memory values.

RAM usage is calculated as:

```text
RAM Used = RAM Total - RAM Available
```

RAM usage percentage is calculated as:

```text
RAM Usage (%) = (RAM Used / RAM Total) * 100
```

Swap usage is calculated as:

```text
Swap Used = Swap Total - Swap Free
```

The collector also calculates swap usage percentage. If the system has no swap memory, the usage percentage is returned as zero.

### 3.4 Process Information

Process information is collected using the Linux `top` command in batch mode.

The command used is:

```bash
top -b -n 1 -w 512
```

Here:

- `-b` runs top in batch mode.
- `-n 1` collects one snapshot.
- `-w 512` sets the output width to preserve longer command names.

For each process, the parser extracts:

- Process ID (PID)
- Username
- CPU usage percentage
- Memory usage percentage
- Process state
- Command name

The collector retains the complete process list. Selection of processes for individual charts, such as the top CPU-consuming or memory-consuming processes, is handled by the analytics or visualization modules.

## 4. Parsing Logic

The parser converts raw system output into structured Python data.

The parsing functions perform the following operations:

- Load average values are converted into floating-point numbers.
- CPU counters are converted into integers.
- Memory values are extracted from `/proc/meminfo`.
- Process information is split into individual fields.

For process information, the parser preserves the remaining command text as a single field. This allows command names containing spaces to be retained.

Malformed process rows and rows containing invalid numeric values are skipped.

If the process output does not contain a valid header, an empty process list is returned.

## 5. CPU Utilization Calculation

CPU utilization requires two readings because `/proc/stat` contains cumulative CPU time counters.

The first reading is stored as the previous CPU state. A later reading is compared against it to calculate CPU utilization.

The calculation uses the following formula:

```text
Total Difference = Current Total Time - Previous Total Time

Idle Difference = Current Idle Time - Previous Idle Time

CPU Usage (%) =
    ((Total Difference - Idle Difference) / Total Difference) * 100
```

If no previous reading is available, `cpu_usage` is returned as `None`.

If the total CPU time difference is zero or negative, the calculated usage is returned as `0.0`.

## 6. Error Handling

The collector includes basic handling for unexpected or incomplete process output.

- Invalid load average data raises a `ValueError`.
- Invalid CPU statistics raise a `ValueError`.
- Missing required memory fields raise a `ValueError`.
- Malformed process rows are skipped.
- If the process output does not contain a valid header, an empty list is returned.
- If the `top` command returns a non-zero exit status, the collector returns an empty process list.

This prevents unsuccessful process collection from producing invalid process data.

## 7. Output Structure

The main function `collect_system_data()` returns a dictionary containing all collected system information.

The structure is:

```python
{
    "cpu_usage": None,
    "cpu_cores": 16,
    "cpu_times": {},
    "load_average": {
        "1min": 0.0,
        "5min": 0.0,
        "15min": 0.0
    },
    "memory": {},
    "processes": []
}
```

The values shown above are illustrative. Actual values depend on the system being monitored.

The `cpu_usage` field is `None` when the function is called without a previous CPU reading.

The `cpu_times` field contains the parsed CPU counters.

The `memory` field contains RAM and swap statistics.

The `processes` field contains a list of dictionaries, with each dictionary representing one process.

A process entry has the following structure:

```python
{
    "pid": 123,
    "user": "username",
    "cpu_percent": 10.5,
    "memory_percent": 2.0,
    "state": "R",
    "command": "python3"
}
```

## 8. Testing

The collector module is tested using Python's built-in `unittest` framework.

The tests cover:

- Parsing load averages
- Parsing CPU statistics
- Parsing memory information
- Parsing process information
- Handling missing memory fields
- Handling invalid input
- Preserving process names containing spaces
- Handling empty and malformed process output
- Calculating CPU utilization
- Collecting CPU, memory and process information
- Handling process command failures

The current test suite contains 17 tests, all of which pass.

To run the tests from the project root:

```bash
python3 -m unittest discover -v
```

## 9. Dependencies

The collector module uses Python standard library modules:

- `os`
- `subprocess`
- `unittest`
- `unittest.mock`

It also uses Linux system resources:

- `/proc/stat`
- `/proc/loadavg`
- `/proc/meminfo`
- `top` command

No external Python package is required by the collector module.

## 10. Conclusion

The collector module provides the system monitoring project with structured CPU, memory, load average and process information.

It separates data collection from parsing, making the implementation easier to maintain and test.

The collected information is made available to the other project modules for analysis and visualization.

