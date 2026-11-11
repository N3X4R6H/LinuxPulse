#!/usr/bin/env bash
# LinuxPulse C++ gprof experiment (Member 5). Profiles profiling/cpp_benchmark/benchmark.cpp,
# NOT the Python dashboard.
#
#   ./scripts/profile.sh [--size N] [--impl baseline|optimized] [--seed S] [--runs R]
#
# Outputs (profiling/results/):
#   run_<impl>.txt        parameters, environment, benchmark output, wall-clock timings
#   gprof_<impl>.txt      gprof flat profile + call graph
# gmon.out is written to profiling/cpp_benchmark/ (git-ignored).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH="$ROOT/profiling/cpp_benchmark"
OUT="$ROOT/profiling/results"

SIZE=100; IMPL=baseline; SEED=123456789; RUNS=5
while [ $# -gt 0 ]; do
  case "$1" in
    --size) SIZE="$2"; shift 2 ;;
    --impl) IMPL="$2"; shift 2 ;;
    --seed) SEED="$2"; shift 2 ;;
    --runs) RUNS="$2"; shift 2 ;;
    -h|--help) sed -n 2,11p "$0"; exit 0 ;;
    *) echo "error: unknown option $1" >&2; exit 2 ;;
  esac
done
case "$IMPL" in baseline|optimized) ;; *) echo "error: --impl must be baseline or optimized" >&2; exit 2 ;; esac

for tool in g++ gprof make; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "error: $tool not found. Arch/Omarchy: sudo pacman -S gcc binutils make" >&2; exit 1; }
done

mkdir -p "$OUT"
cd "$BENCH"
make -s clean
make -s profiled plain

ARGS=(--size "$SIZE" --seed "$SEED" --impl "$IMPL")
REPORT="$OUT/run_$IMPL.txt"
{
  echo "# LinuxPulse C++ benchmark run (NOT the Python dashboard)"
  echo "date:      $(date -Iseconds)"
  echo "host:      $(uname -sr) $(uname -m)"
  echo "cpu:       $(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ //' || echo unknown)"
  echo "compiler:  $(g++ --version | head -1)"
  echo "gprof:     $(gprof --version | head -1)"
  echo "flags:     -std=c++17 -O0 -pg (profiled); -O0 (plain, for timing)"
  echo "arguments: ${ARGS[*]}"
  echo
  echo "## Instrumented run (-pg), produces gmon.out"
} > "$REPORT"

rm -f gmon.out
./benchmark "${ARGS[@]}" | tee -a "$REPORT"
[ -f gmon.out ] || { echo "error: gmon.out was not generated" >&2; exit 1; }

gprof ./benchmark gmon.out > "$OUT/gprof_$IMPL.txt"

{
  echo
  echo "## Un-instrumented timing (-O0 without -pg), $RUNS runs, same arguments"
} >> "$REPORT"
for r in $(seq 1 "$RUNS"); do
  ./benchmark_plain "${ARGS[@]}" | grep '^TIME' | sed "s/^/run $r: /" | tee -a "$REPORT"
done

echo
echo "Done. Files:"
echo "  gmon.out      $BENCH/gmon.out"
echo "  gprof report  $OUT/gprof_$IMPL.txt"
echo "  run record    $REPORT"
