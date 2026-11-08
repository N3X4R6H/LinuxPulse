# Dashboard GUI and Application Integration

The GUI and application-integration layer provides the desktop interface for the Unix System Monitoring Dashboard. It presents system resource usage, process information, analytics results, and monitoring alerts in a responsive, consistent interface.

## Responsibilities

- Develop the desktop interface using Python and Tkinter.
- Implement the Overview, Processes, and Analytics views.
- Display CPU, memory, swap, system load, and monitoring status.
- Build a process table with sorting and support for empty or incomplete data.
- Present analytics results and active alerts from the analytics module.
- Apply and maintain a consistent dark theme.
- Integrate GUI components with the application controller and shared data models.
- Keep the interface responsive and support safe application shutdown.
- Maintain GUI design documentation and application assets.

Data collection, analytics calculations, and graph generation are handled by their respective modules. The GUI displays and integrates their outputs.

## Project Files

```text
project/
├── gui/
│   ├── __init__.py
│   ├── dashboard.py
│   └── process_table.py
│
├── docs/
│   └── gui_design.md
│
├── assets/
│   ├── logo.png
│   └── screenshots/
│       ├── overview.png
│       ├── processes.png
│       └── analytics.png
│
├── main.py
├── config.py
└── models.py
```

| File / Directory | Purpose |
|---|---|
| `gui/dashboard.py` | Main window, navigation, dashboard views, and GUI coordination |
| `gui/process_table.py` | Process table, column display, and sorting |
| `gui/__init__.py` | GUI package initialization |
| `docs/gui_design.md` | Detailed GUI design, layout, components, styling, and integration documentation |
| `assets/logo.png` | Application logo |
| `assets/screenshots/` | Screenshots documenting the Overview, Processes, and Analytics views |
| `main.py` | Application entry point and integration with the GUI |
| `config.py` | Shared application and GUI configuration |
| `models.py` | Shared data structures used by the GUI and other modules |

The tree shows the expected files for this module; add screenshot files as the corresponding views are implemented. Keep the structure aligned with the team's agreed repository layout.

## Dashboard Views and Functional Requirements

The dashboard is organized into three views, accessible through consistent navigation.

### Overview
Provides an at-a-glance summary of system health through:
- **CPU, RAM, and SWAP cards:** Display current utilization and clearly indicate unavailable measurements.
- **CPU core count:** Shows the number of available logical or physical cores, according to the shared data model.
- **System load:** Displays the system load information supplied by the collector.
- **Monitoring status:** Indicates whether monitoring is active and whether the latest update is current.

### Processes
Displays process-level information in a dedicated, sortable table:
- **Process ID (PID)**
- **Process name**
- **CPU usage**
- **Memory usage**
- **Process state**

The table must support sorting by CPU and memory usage, remain usable with large process lists, and provide a clear empty state when no process records are available. Missing or incomplete fields should be represented safely rather than causing the interface to fail.

### Analytics
Presents computed results supplied by the analytics module:
- **Average CPU and RAM utilization**
- **Peak resource utilization**
- **Top processes** by resource consumption
- **Active alerts** raised by the monitoring and analytics components

The GUI is responsible for presenting these results; analytics calculations remain in the analytics module.

## GUI Design Documentation

Detailed design and implementation notes belong in [`docs/gui_design.md`](docs/gui_design.md), rather than duplicating them here. This document should cover:

- Dashboard layout, navigation, and view organization.
- Widget hierarchy and process-table behavior.
- Dark theme, colors, typography, and visual consistency.
- Data flow between the controller, shared models, and GUI.
- Refresh behavior, thread safety, and error handling.
- Screenshots or references to the implemented views.

## Assets

The `assets/` directory stores visual resources used by or documenting the application:

- `logo.png` — application branding.
- `screenshots/overview.png` — Overview page.
- `screenshots/processes.png` — Processes page.
- `screenshots/analytics.png` — Analytics page.

Use clear, consistent screenshot names. Keep screenshots up to date with the implemented interface.

## Technology Stack

| Technology | Use |
|---|---|
| Python 3 | Application development |
| Tkinter / `ttk` | Desktop interface and process table |
| `threading` and `queue` | Background-task coordination and thread-safe data transfer |
| Matplotlib | Displaying visualizations supplied by the visualization module |
| Git and GitHub | Version control and collaborative review |
| `unittest` | Automated testing |

## Tkinter, Layout, and Application Integration

### Window and Widget Management
Build the desktop window and its widgets using Tkinter and `ttk`. Use layout managers consistently:
- Use `grid()` for structured, row-and-column layouts such as metric cards and forms.
- Use `pack()` for simple stacked or side-by-side sections where appropriate.
- Use `place()` only when fixed positioning is genuinely required; avoid it for the main responsive dashboard layout.
- Keep widget creation, layout, styling, and view-switching responsibilities organized in reusable components.

### Dynamic Updates
Refresh displayed values as new system snapshots arrive. Update existing widgets and table rows where practical instead of repeatedly rebuilding the entire interface. Keep timestamps and monitoring status synchronized with the latest received data.

### GUI Responsiveness
System collection and other potentially slow operations must not block Tkinter's event loop. Use background workers for such operations and communicate their results to the GUI through a thread-safe `queue.Queue`. Use Tkinter's `after()` method to poll the queue and schedule UI updates on the main thread.

### Communication with the Application Controller
The GUI receives system snapshots and analytics results through the application controller and shared interfaces in `models.py`. Keep the GUI focused on presentation and user interaction; system collection and analytics calculations belong to their respective modules.

### Missing and Unavailable Data
Handle missing, unavailable, stale, or invalid measurements without crashing. Distinguish unavailable values from numeric zero, show a clear placeholder or status where data cannot be displayed, and treat an empty process list as valid input.

### Safe Shutdown
When the application closes, stop refresh callbacks and signal background workers to terminate. Ensure workers are shut down cleanly without attempting to update destroyed widgets.

**Thread-safety:** Background threads must never update Tkinter widgets directly.

## Setup and Execution

Prerequisites: Python 3, Tkinter support, and the dependencies listed in `requirements.txt`.

On Ubuntu/Debian, install Tkinter if needed:

```bash
sudo apt update
sudo apt install python3-tk
```

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Launch the application from the repository root:

```bash
python3 main.py
```

## Process Table Requirements

The process table is implemented as a dedicated, reusable GUI component in `gui/process_table.py`. It must:
- Display PID, name, CPU usage, memory usage, and process state.
- Support sorting by different columns, with CPU and memory sorting as required dashboard operations.
- Handle large process lists without making the interface unresponsive.
- Display a useful empty-state message when the process list is empty.
- Handle missing or unavailable process fields safely.

## Dark Mode and Visual Consistency

Apply a consistent dark theme across the main window, navigation, metric cards, tables, dialogs, and status indicators. Maintain readable text contrast, clear visual hierarchy, consistent spacing, and distinguishable states for normal, warning, and critical alerts. Avoid relying on color alone to communicate status; include text or other visual cues where appropriate.

## Testing

Run the project test suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

GUI and integration tests should verify:

- Window initialization and navigation between views.
- Correct display of system and analytics data.
- Empty, missing, and incomplete process data.
- Process-table sorting.
- Large process lists and refresh behavior.
- Queue-based updates and GUI responsiveness.
- Handling of collection errors and stale data.
- Graceful application shutdown.

Use controlled test data where possible instead of relying on live system measurements.

## Development Workflow

Use a feature branch for dashboard and integration changes:

```bash
git switch main
git pull origin main
git switch -c feature/dhiren-dashboard
```

After making changes:

```bash
git add gui/ docs/gui_design.md assets/
git commit -m "Implement monitoring dashboard GUI"
git push -u origin feature/dhiren-dashboad
```

Open a Pull Request on GitHub and request review before merging into `main`. Coordinate changes to shared files such as `main.py`, `config.py`, and `models.py` with the relevant contributors.

## Deliverables Checklist

- [ ] Implement the main dashboard window and navigation.
- [ ] Complete the Overview, Processes, and Analytics views.
- [ ] Implement process-table sorting and empty-state handling.
- [ ] Apply and validate the dark theme.
- [ ] Integrate GUI updates with the application controller and shared models.
- [ ] Ensure thread-safe updates and graceful shutdown.
- [ ] Add and run GUI/integration tests.
- [ ] Complete `docs/gui_design.md`.
- [ ] Add the application logo and screenshots under `assets/`.
- [ ] Update documentation to reflect the implemented interface.

---

*Unix System Monitoring Dashboard — GUI and Application Integration*
