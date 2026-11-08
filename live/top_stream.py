"""Runs `top` continuously in batch/logging mode and yields one complete frame at a time.

One long-lived `top` process means every frame's CPU percentages are measured over
the refresh interval (not since boot), and no process is spawned per sample.
"""
import os
import queue
import shutil
import subprocess
import tempfile
import threading


class TopNotAvailable(RuntimeError):
    pass


class TopStream:
    def __init__(self, commands, is_frame_start, flush_after=0.35):
        """commands: candidate argv lists, tried in order (first that keeps running wins)."""
        if not shutil.which("top"):
            raise TopNotAvailable("`top` was not found on PATH")
        self.commands = commands
        self.is_frame_start = is_frame_start
        self.flush_after = flush_after
        self.proc = None
        # Empty config dir + C locale: ignore any personal toprc (custom columns/units)
        # and guarantee '.' decimal points.
        self._home = tempfile.mkdtemp(prefix="sysmon-top-")
        self.env = dict(os.environ, LC_ALL="C", LANG="C", HOME=self._home, XDG_CONFIG_HOME=self._home)

    def _start(self):
        errors = []
        for argv in self.commands:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    env=self.env, bufsize=1)
            try:
                proc.wait(timeout=0.4)          # exited immediately -> unsupported option
                errors.append(f"{' '.join(argv)}: {proc.stderr.read().strip()[:200]}")
            except subprocess.TimeoutExpired:
                return proc
        raise TopNotAvailable("could not start top:\n" + "\n".join(errors))

    def frames(self, stop):
        self.proc = self._start()
        lines = queue.Queue()

        def reader():
            for line in self.proc.stdout:
                lines.put(line.rstrip("\n"))
            lines.put(None)

        threading.Thread(target=reader, name="top-reader", daemon=True).start()
        frame = []
        try:
            while not stop.is_set():
                try:
                    line = lines.get(timeout=self.flush_after)
                except queue.Empty:
                    # top writes a frame in one burst; a quiet pipe means the frame is complete
                    if frame and self.is_frame_start(frame[0]):
                        yield frame
                    frame = []
                    continue
                if line is None:
                    err = self.proc.stderr.read().strip()
                    raise RuntimeError(f"top exited unexpectedly{': ' + err[:200] if err else ''}")
                if self.is_frame_start(line) and frame:
                    if self.is_frame_start(frame[0]):
                        yield frame
                    frame = []
                frame.append(line)
        finally:
            self.close()

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self._home, ignore_errors=True)
