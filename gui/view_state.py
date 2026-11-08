"""GUI-side view model.

This describes *what the widgets display*. It is deliberately NOT the backend
data model: when the team's ``models.py`` is available, write one adapter
(``gui/adapter.py: to_view_state(snapshot, analytics) -> ViewState``) and the
GUI keeps working unchanged.

Every field maps to something Linux ``top`` prints:
  header  -> load average, uptime, Tasks line, %Cpu(s) line, MiB Mem/Swap lines
  "1" key -> per-CPU %Cpu0, %Cpu1, ... lines
  table   -> PID USER ... RES ... S %CPU %MEM TIME+ COMMAND

Convention: ``None`` means "unavailable" and is shown as "—"; it is never
treated as zero.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# top's %Cpu(s) fields: us sy ni wa hi si st (+ id)
CPU_DIMS = ("user", "system", "nice", "iowait", "irq", "softirq", "steal")


@dataclass
class CpuBreakdown:
    user: Optional[float] = None
    system: Optional[float] = None
    nice: Optional[float] = None
    iowait: Optional[float] = None
    irq: Optional[float] = None
    softirq: Optional[float] = None
    steal: Optional[float] = None
    idle: Optional[float] = None

    @property
    def total(self) -> Optional[float]:
        return None if self.idle is None else max(0.0, min(100.0, 100.0 - self.idle))


@dataclass
class ProcessRow:
    pid: Optional[int]
    name: Optional[str]           # COMMAND
    cpu: Optional[float]          # %CPU
    mem: Optional[float]          # %MEM
    state: Optional[str]          # S: R, S, D, I, Z, T
    user: Optional[str] = None    # USER
    res_mib: Optional[float] = None   # RES
    time_s: Optional[float] = None    # TIME+ in seconds
    gpu: Optional[float] = None       # only with a separate GPU telemetry source
    is_system: Optional[bool] = None  # per collector's agreed classification


@dataclass
class Alert:
    level: str        # "warning" | "critical"
    message: str
    timestamp: float  # epoch seconds


@dataclass
class History:
    """Equal-length series. ``t`` is seconds relative to ``ViewState.timestamp`` (<= 0)."""
    t: List[float] = field(default_factory=list)
    cpu: List[Optional[float]] = field(default_factory=list)
    ram: List[Optional[float]] = field(default_factory=list)
    swap: List[Optional[float]] = field(default_factory=list)
    load1: List[Optional[float]] = field(default_factory=list)
    cpu_dims: Dict[str, List[Optional[float]]] = field(default_factory=dict)   # key in CPU_DIMS
    per_core: List[Optional[List[Optional[float]]]] = field(default_factory=list)  # per sample: core totals
    mem_used: List[Optional[float]] = field(default_factory=list)        # GiB
    mem_buffcache: List[Optional[float]] = field(default_factory=list)   # GiB
    mem_free: List[Optional[float]] = field(default_factory=list)        # GiB


@dataclass
class ViewState:
    timestamp: float
    # CPU
    cpu: Optional[float] = None
    cpu_dims: Optional[CpuBreakdown] = None
    per_core: Optional[List[CpuBreakdown]] = None
    load: Optional[Tuple[float, float, float]] = None   # 1, 5, 15 min
    # memory (GiB)
    ram: Optional[float] = None
    mem_total_gib: Optional[float] = None
    mem_used_gib: Optional[float] = None
    mem_free_gib: Optional[float] = None
    mem_buffcache_gib: Optional[float] = None
    mem_available_gib: Optional[float] = None
    swap: Optional[float] = None
    swap_used_gib: Optional[float] = None
    swap_total_gib: Optional[float] = None
    # tasks
    total: Optional[int] = None
    running: Optional[int] = None
    sleeping: Optional[int] = None
    stopped: Optional[int] = None
    zombie: Optional[int] = None
    processes: List[ProcessRow] = field(default_factory=list)
    gpu_available: bool = False
    # analytics
    history: History = field(default_factory=History)
    avg_cpu: Optional[float] = None
    avg_ram: Optional[float] = None
    peak_cpu: Optional[float] = None
    peak_ram: Optional[float] = None
    peak_swap: Optional[float] = None
    top_processes: List[ProcessRow] = field(default_factory=list)
    alerts: List[Alert] = field(default_factory=list)
    n_cpus: Optional[int] = None      # logical CPUs, if known without per-core data
    # meta
    uptime_s: Optional[float] = None
    interval_s: Optional[float] = None
    hostname: Optional[str] = None

    @property
    def cores(self) -> Optional[int]:
        return len(self.per_core) if self.per_core else self.n_cpus


@dataclass
class SourceError:
    """Put on the queue by the data pump when the source thread fails."""
    message: str
