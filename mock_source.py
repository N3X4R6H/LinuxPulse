"""Synthetic data source for LINUXPULSE mock / demo mode (Member 5).

Produces clearly-artificial :class:`models.SystemSnapshot` objects on the
configured sampling cadence and pushes them into the queue. It implements
exactly the same contract as ``collector.top_collector.TopCollector`` so
the controller can swap the two transparently.

This module is used **only** when the application is started with
``--mock``. It never runs in real mode, and real measurements are never
silently substituted with synthetic values -- the choice is explicit and
is logged at startup.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from typing import Optional

import config
from models import (
    CPUInfo, LoadAverages, MemoryInfo, ProcessInfo, SwapInfo, SystemSnapshot,
)


class MockCollector:
    """A drop-in replacement for ``TopCollector`` that emits fake data.

    Constructor signature matches the real collector:
    ``MockCollector(config, output_queue, stop_event)``. The worker thread
    is a daemon named after ``config.collector_thread_name`` with a
    ``-mock`` suffix, so it is identifiable in logs and tooling.
    """

    def __init__(self,
                 cfg: config.AppConfig,
                 output_queue: "queue.Queue[SystemSnapshot]",
                 stop_event: threading.Event) -> None:
        self.cfg = cfg
        self.queue = output_queue
        self.stop_event = stop_event
        self._thread: Optional[threading.Thread] = None
        self._tick: int = 0

    # ------------------------------------------------------------------ #
    # TopCollector contract
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        name = f"{self.cfg.collector_thread_name}-mock"
        self._thread = threading.Thread(
            target=self._run, name=name,
            daemon=self.cfg.collector_thread_daemon)
        self._thread.start()

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                snapshot = self._make_snapshot()
            except Exception:
                # Mirror the real collector: never raise out of the worker.
                # On an unexpected error, emit an empty snapshot so the
                # controller keeps rendering rather than stalling.
                snapshot = SystemSnapshot.empty()
            self._push(snapshot)
            self._tick += 1
            # Wait for the cadence, but wake promptly when stop is signalled.
            self.stop_event.wait(self.cfg.sampling_interval_seconds)

    def _push(self, snapshot: SystemSnapshot) -> None:
        try:
            self.queue.put(snapshot, block=False)
        except queue.Full:
            # Drop the oldest pending item, then push (matches the real
            # collector's back-pressure policy).
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(snapshot)
            except queue.Empty:
                pass

    # ------------------------------------------------------------------ #
    # Synthetic data generation
    # ------------------------------------------------------------------ #
    def _make_snapshot(self) -> SystemSnapshot:
        t = self._tick
        ts = time.time()

        # CPU: a slow sine wave around 40% plus a periodic spike to 92%
        # every 30 samples so alert thresholds are exercised.
        cpu = 40.0 + 25.0 * math.sin(t / 7.0)
        if t > 0 and t % 30 == 0:
            cpu = 92.0
        cpu = max(0.0, min(100.0, cpu))

        # Memory: drifts between ~55% and ~85% of a fixed 16 GiB total.
        total = 16 * 1024 ** 3
        used_frac = 0.55 + 0.30 * (0.5 - 0.5 * math.cos(t / 25.0))
        used = int(total * used_frac)
        memory = MemoryInfo.from_total_used_free(total, used)

        # Swap: 2 GiB, lightly and slowly used.
        swap_total = 2 * 1024 ** 3
        swap_used = int(swap_total * (0.05 + 0.05 * (t % 50) / 50.0))
        swap = SwapInfo.from_total_used(swap_total, swap_used)

        # A handful of fake processes with varying CPU consumption.
        processes = [
            ProcessInfo(pid=1, name="systemd", cpu_percent=0.1,
                        memory_percent=0.5, username="root", state="S"),
            ProcessInfo(pid=2, name="kthreadd", cpu_percent=0.0,
                        memory_percent=0.0, username="root", state="S"),
            ProcessInfo(pid=42, name="workerd",
                        cpu_percent=round(max(0.0, 30.0 * abs(math.sin(t / 3.0))), 1),
                        memory_percent=2.4, username="app", state="R"),
            ProcessInfo(pid=99, name="render-svc",
                        cpu_percent=round(max(0.0, 18.0 * abs(math.cos(t / 5.0))), 1),
                        memory_percent=5.1, username="app", state="R"),
            ProcessInfo(pid=120, name="db-engine",
                        cpu_percent=round(max(0.0, 12.0 * abs(math.sin(t / 11.0))), 1),
                        memory_percent=12.7, username="pg", state="S"),
        ]
        # Respect the configured process count cap.
        processes = processes[: self.cfg.default_process_count]

        return SystemSnapshot(
            timestamp=ts,
            cpu=CPUInfo(
                usage_percent=round(cpu, 1),
                core_count=8,
                load_averages=LoadAverages(
                    one_minute=round(cpu / 100.0 * 4, 2),
                    five_minutes=round(cpu / 100.0 * 3, 2),
                    fifteen_minutes=round(cpu / 100.0 * 2, 2),
                ),
            ),
            memory=memory,
            swap=swap,
            processes=processes,
        )


__all__ = ["MockCollector"]
