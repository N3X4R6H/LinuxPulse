
import tkinter as tk
import unittest

from visualization.plots import SystemPlotter


class TestSystemPlotter(unittest.TestCase):

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.plotter = SystemPlotter(self.root)

    def tearDown(self):
        self.root.destroy()

    def test_empty_data(self):
        self.plotter.update([], [], [], [])

        self.assertEqual(
            len(self.plotter.cpu_line.get_xdata()), 0
        )

    def test_missing_values(self):
        time = [1, 2, 3]
        cpu = [20, None, 40]
        ram = [30, 40, 50]
        swap = [10, 15, None]

        self.plotter.update(time, cpu, ram, swap)

        self.assertEqual(len(self.plotter.cpu_line.get_ydata()), 3)

    def test_unequal_lengths(self):
        with self.assertRaises(ValueError):
            self.plotter.update(
                [1, 2, 3],
                [20, 30],
                [40, 50, 60],
                [10, 15, 20]
            )


    def test_latest_30_measurements(self):

        time = list(range(1, 51))
        cpu = list(range(1, 51))
        ram = list(range(1, 51))
        swap = list(range(1, 51))

        self.plotter.update(time, cpu, ram, swap)

        self.assertEqual(len(self.plotter.cpu_line.get_xdata()), 30)

        self.assertEqual(
            list(self.plotter.cpu_line.get_xdata()),
            list(range(21, 51))
        )


if __name__ == "__main__":
    unittest.main()
