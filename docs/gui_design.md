# GUI Design — Unix System Monitoring Dashboard

Visual direction: flat, dense, Netdata-like monitoring console. Charcoal page
(`#1c1e22`), bordered panels (`#23262a`), neon-green accent (`#00d26a`),
clock-time chart axes, stacked per-dimension charts with legends underneath.

## Window

```text
┌────┬──────────────────────────────────────────────────────────────────────────┐
│ ▣  │ (host) HOSTNAME [DEMO DATA]   [▶ Playing][dd/mm • HH:MM:SS → HH:MM:SS]  🔔 0 1  ● LIVE │
│────├──────────────────────────────────────────────────────────────────────────┤
│ ⬡  │ ⁂ System › Overview  ┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆┆ ○ > 08/11/2026•20:00:12 │
│ ▦  ├──────────────────────────────────────────────────────────────────────────┤
│ ☰  │                              active view                                  │
│ 〰 │                                                                           │
└────┴──────────────────────────────────────────────────────────────────────────┘
 56px icon rail (tooltips)   Ctrl+1..4 views · Space pause/resume · Ctrl+F search
```

## Views

**Overview**
```text
┌Total CPU◯┐┌RAM used◯┐┌Swap used◯┐┌System load┐┌Tasks ┐ │ Metrics index
├──────── Per-core utilization (bars ≤16 CPUs, heat tiles >16) ─┤ │  CPU  user…steal
├── Total CPU utilization (stacked us/sy/ni/wa/hi/si/st) ──┬ RAM (used/cache/free) ┤ │  Memory
│  legend: user 22.8% · system 8.3% · … (click to hide)    │ legend                │ │  Swap · Tasks
```
Gauges: full ring, green → amber (75%) → red (90%), red tick = peak in window.

**Processes** — Tasks (total/running/sleeping/stopped/zombie + status), Top 5,
Recent alerts; table with search, All/High CPU/High GPU/System tabs, sortable
`PID USER COMMAND %CPU %MEM RES TIME+ STATE`.

**Analytics** — average/peak tiles; one figure with CPU, RAM, SWAP, load
histories (dashed = average) and a per-core heatmap; top consumers; alerts.

**Introduction** — project, team table, website, quick-nav; clock; host info
(read locally via `platform`); memory donut.

## Data flow
```text
source thread --ViewState--> queue.Queue --root.after(250ms) drain--> active view
```
`gui/view_state.py` is the GUI contract; every field maps to something `top`
prints. `None` = unavailable ("—"), never zero. Pause freezes the display only;
collection keeps running.
