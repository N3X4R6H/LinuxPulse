#!/usr/bin/env bash
# Compare profiling/results/run_baseline.txt with run_optimized.txt (Member 5).
# Checks that all RESULT lines (correctness) are identical and prints median timings.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)/profiling/results"
for f in baseline optimized; do [ -f "$R/run_$f.txt" ] || { echo "missing $R/run_$f.txt (run scripts/profile.sh --impl $f)"; exit 1; }; done
grep '^size=' "$R/run_baseline.txt" | head -1 | sed 's/ impl=[a-z]*//' > /tmp/lp_a.$$
grep '^size=' "$R/run_optimized.txt" | head -1 | sed 's/ impl=[a-z]*//' > /tmp/lp_b.$$
cmp -s /tmp/lp_a.$$ /tmp/lp_b.$$ && echo "Workload parameters: identical" || { echo "Workload parameters DIFFER"; rm -f /tmp/lp_?.$$; exit 1; }
rm -f /tmp/lp_?.$$
if diff <(grep '^RESULT' "$R/run_baseline.txt") <(grep '^RESULT' "$R/run_optimized.txt") >/dev/null; then
  echo "Output correctness: RESULT lines identical"; else echo "Output correctness: MISMATCH"; fi
median() { # file field -> median over un-instrumented "run N:" lines
  grep '^run ' "$1" | grep -o "$2=[0-9.]*" | cut -d= -f2 | sort -n | awk '{a[NR]=$1} END{print a[int((NR+1)/2)]}'
}
printf '%-14s %10s %10s %9s\n' metric baseline optimized speedup
for m in ranking_only rolling total; do
  b=$(median "$R/run_baseline.txt" $m); o=$(median "$R/run_optimized.txt" $m)
  printf '%-14s %9ss %9ss %8.2fx\n' "$m" "$b" "$o" "$(echo "$b $o" | awk '{print $1/$2}')"
done
