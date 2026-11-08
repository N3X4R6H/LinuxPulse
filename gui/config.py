"""Static project details shown on the Introduction view.

Placeholders — replace with the team's confirmed details.
"""
APP_NAME = "LinuxPulse"
APP_TAGLINE = "Real-time Linux telemetry · processes · analytics"
TEAM_NAME = "Mentally Unstable"
MEMBERS = [
    ("Ankush Tarafdar", "MC25BT011"),
    ("Atharv Saxena", "NC25BT04"),
    ("Chettupelly Dhiren", "MC25BT005"),
    ("Manish Parvin Patil", "MC25BT028"),
    ("Pavan nandan gudipudi", "MC25BT004"),
]
WEBSITE = "https://github.com/N3X4R6H/LinuxPulse.git"

# GUI timing
POLL_MS = 250          # how often the GUI drains the data queue
STALE_AFTER_S = 5.0    # no new data for this long -> "STALE"

# Filter thresholds (display only)
HIGH_CPU_MIN = 1.0     # % — "High CPU" filter hides idle processes
