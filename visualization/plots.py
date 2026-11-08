from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class SystemPlotter:

    def __init__(self, parent):

        # Create a Matplotlib figure with 3 graphs
        self.figure = Figure(figsize=(8, 6))

        self.cpu_ax = self.figure.add_subplot(3, 1, 1)
        self.ram_ax = self.figure.add_subplot(3, 1, 2)
        self.swap_ax = self.figure.add_subplot(3, 1, 3)

        # Configure CPU graph
        self.cpu_ax.set_title("CPU Usage")
        self.cpu_ax.set_ylabel("Usage (%)")
        self.cpu_ax.set_ylim(0, 100)
        self.cpu_ax.grid(True)

        # Configure RAM graph
        self.ram_ax.set_title("RAM Usage")
        self.ram_ax.set_ylabel("Usage (%)")
        self.ram_ax.set_ylim(0, 100)
        self.ram_ax.grid(True)

        # Configure Swap graph
        self.swap_ax.set_title("Swap Usage")
        self.swap_ax.set_ylabel("Usage (%)")
        self.swap_ax.set_ylim(0, 100)
        self.swap_ax.grid(True)

        self.figure.tight_layout()

        # Embed Matplotlib figure inside the Tkinter Frame
        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.canvas.draw()

        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Create one line for each graph
        self.cpu_line, = self.cpu_ax.plot([], [], marker='o', label="CPU")
        self.ram_line, = self.ram_ax.plot([], [], marker='o', label="RAM")
        self.swap_line, = self.swap_ax.plot([], [], marker='o', label="Swap")



    def update(self, time, cpu, ram, swap):

        # Check that all lists have equal lengths
        if not (len(time) == len(cpu) == len(ram) == len(swap)):
            raise ValueError("All measurement lists must have equal lengths")

        # Handle empty data
        if len(time) == 0:
            self.cpu_line.set_data([], [])
            self.ram_line.set_data([], [])
            self.swap_line.set_data([], [])
            self.canvas.draw_idle()
            return

        # Keep only the latest 30 measurements
        time = list(time)[-30:]
        cpu = list(cpu)[-30:]
        ram = list(ram)[-30:]
        swap = list(swap)[-30:]

        # Replace missing measurements with NaN
        cpu = [float("nan") if v is None else float(v) for v in cpu]
        ram = [float("nan") if v is None else float(v) for v in ram]
        swap = [float("nan") if v is None else float(v) for v in swap]

        # Update existing graph lines
        self.cpu_line.set_data(time, cpu)
        self.ram_line.set_data(time, ram)
        self.swap_line.set_data(time, swap)

        # Move the viewing window
        for ax in [self.cpu_ax, self.ram_ax, self.swap_ax]:

            if len(time) >= 30:
                ax.set_xlim(time[0], time[-1])
            else:
                ax.set_xlim(0, 30)

        self.canvas.draw_idle()
