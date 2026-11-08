import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk
import time
import tracemalloc
from visualization.plots import SystemPlotter

root = tk.Tk()
root.title("LinuxPulse Performance Test")
root.geometry("900x700")

plotter = SystemPlotter(root)

MAX_POINTS = 30
time_values = []
cpu_values = []
ram_values = []
swap_values = []

tracemalloc.start()
print("Performance test started...")
start_time = time.perf_counter()

for i in range(1000):

    time_values.append(i)
    cpu_values.append((i * 7) % 100)
    ram_values.append((i * 5) % 100)
    swap_values.append((i * 3) % 100)

    # Keep only the latest 30 measurements
    if len(time_values) > MAX_POINTS:
        time_values.pop(0)
        cpu_values.pop(0)
        ram_values.pop(0)
        swap_values.pop(0)

    plotter.update(
        time_values,
        cpu_values,
        ram_values,
        swap_values
    )

    # Process pending Tkinter drawing operations
    root.update()

end_time = time.perf_counter()

current_memory, peak_memory = tracemalloc.get_traced_memory()
print("\n--- LinuxPulse Performance Results ---")
print(f"Total updates: 1000")
print(f"Total time: {end_time - start_time:.3f} seconds")
print(f"Average update time: {(end_time - start_time) * 1000 / 1000:.3f} ms")
print(f"Current Python memory: {current_memory / 1024:.2f} KB")
print(f"Peak Python memory: {peak_memory / 1024:.2f} KB")

tracemalloc.stop()
print("Performance test completed.")
root.destroy()
