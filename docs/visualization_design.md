# LinuxPulse — Visualization Module Design

## 1. Overview

The visualization module is responsible for displaying historical CPU, RAM and Swap utilization using Matplotlib.

The graphs are embedded into the Tkinter application using `FigureCanvasTkAgg`.

The module is implemented as a reusable Python class named `SystemPlotter`.

## 2. Technologies Used

- Python
- Matplotlib
- Tkinter
- NumPy (if required by future visualization functionality)

## 3. Architecture

The visualization module receives system measurements from the analytics engine and displays them through three time-series graphs.

The `SystemPlotter` class accepts a Tkinter parent Frame, allowing it to be embedded into the main dashboard.

## 4. Graph Components

Three graphs are displayed:

1. CPU Usage — percentage of CPU utilization.
2. RAM Usage — percentage of memory utilization.
3. Swap Usage — percentage of swap utilization.

Each graph has:
- Time on the X-axis.
- Utilization percentage on the Y-axis.
- A fixed Y-axis range of 0–100%.
- Grid lines for readability.

## 5. Live Updates

The visualization uses Matplotlib's `Line2D.set_data()` method to update existing graph lines.

Existing line objects are reused instead of creating new plots for every measurement.

The canvas is refreshed using `draw_idle()`.

The Tkinter application can schedule periodic updates using `root.after()`.

## 6. Sliding Window

The visualization displays a maximum of 30 measurements at a time.

When new measurements arrive, older measurements are removed from the displayed window.

The X-axis moves with the latest measurements, providing a continuously sliding time-series view.

This display limit is independent of the analytics engine's historical data storage limit.

## 7. Input Handling

The update method supports:

- Empty measurement lists.
- Missing measurement values.
- Validation of equal input-list lengths.
- Restricting displayed measurements to the latest 30 samples.

Missing values are converted to `NaN`, allowing Matplotlib to display gaps instead of misleading values.

Unequal input lengths raise a `ValueError`.

## 8. Testing

The visualization module has been tested for:

- Empty input.
- Missing measurements.
- Unequal input lengths.
- Displaying only the latest 30 measurements.

All four unit tests passed.

A separate performance benchmark was also developed to measure graph-update execution time and Python memory usage over 1,000 updates.

## 9. Integration

The module is designed to integrate with:

- The analytics engine for historical system measurements.
- The Tkinter dashboard for graphical presentation.

Final integration will be completed after the analytics and GUI interfaces are available.

## 10. Future Improvements

- Integrate actual system measurements.
- Improve graph styling to match the dashboard theme.
- Add performance and memory regression tests.
- Support additional system metrics if required.