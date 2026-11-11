# LinuxPulse — Testing Strategy

## 1. Objective

The objective is to verify the correctness, reliability and performance of the visualization module.

Testing focuses on graph creation, data updates, missing measurements, sliding-window behaviour and integration readiness.

## 2. Unit Testing

Unit tests are implemented using Python's built-in `unittest` framework.

### Test Cases

| Test ID | Test Description | Expected Result |
|---|---|---|
| VT01 | Empty input data | Graphs clear without errors |
| VT02 | Missing measurement values | Missing values are handled using NaN |
| VT03 | Unequal input-list lengths | ValueError is raised |
| VT04 | More than 30 measurements | Only the latest 30 are displayed |

### Execution

Run the tests using:

`python3 -m unittest tests.test_visualization -v`

All four unit tests passed during initial verification.

## 3. Performance Testing

The Tk plot-update script was removed. Performance is covered by the C++ gprof experiment
(`profiling/README.md`, `docs/performance_analysis.md`) and by the resource measurements of the
running application in `docs/integration_guide.md`.

## 4. Integration Testing

Integration testing will verify the interaction between:

1. Analytics engine and visualization module.
2. Tkinter dashboard and visualization module.
3. Historical measurements and graph updates.

These tests will be implemented after the corresponding team modules are available.

## 5. Edge Cases

The following conditions are considered:

- Empty historical data.
- Missing CPU, RAM or Swap measurements.
- Invalid input lengths.
- Historical data exceeding the graph display limit.
- Repeated graph updates.

## 6. Testing Limitations

The current tests use synthetic measurements rather than actual system-monitoring data.

Final integration and end-to-end testing remain pending