"""Runs a data source in a background thread and hands states to the GUI.

A *source* is any object with ``run(stop_event, out_queue)`` that puts
``ViewState`` objects on ``out_queue`` until ``stop_event`` is set. The
temporary ``DummySource`` follows this; the real collector/analytics pair
will be wrapped the same way once ``models.py`` is available.
"""
import queue
import threading
import traceback

from .view_state import SourceError


class DataPump:
    def __init__(self, source, maxsize=8):
        self.source = source
        self.queue = queue.Queue(maxsize=maxsize)
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, name="data-source", daemon=True)
        self.thread.start()

    def _run(self):
        try:
            self.source.run(self.stop_event, self.queue)
        except Exception as exc:  # report to the GUI instead of dying silently
            traceback.print_exc()
            try:
                self.queue.put_nowait(SourceError(f"{type(exc).__name__}: {exc}"))
            except queue.Full:
                pass

    def drain(self):
        """Return the newest item on the queue (or None). Main thread only."""
        latest = None
        while True:
            try:
                latest = self.queue.get_nowait()
            except queue.Empty:
                return latest

    def stop(self, timeout=2.0):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout)
