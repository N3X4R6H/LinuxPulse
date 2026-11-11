# C++ benchmark build (separate from the Python app). Run `make` here, or use ../../scripts/profile.sh.
CXX      ?= g++
CXXFLAGS := -std=c++17 -Wall -Wextra -pedantic
SRC      := benchmark.cpp

.PHONY: all profiled plain run clean
all: profiled

# -O0 -pg : gprof instrumentation, no optimization, so functions are not inlined away.
profiled: benchmark
benchmark: $(SRC)
	$(CXX) $(CXXFLAGS) -O0 -pg -o $@ $<

# Same flags without -pg: used only to time the program without profiling overhead.
plain: benchmark_plain
benchmark_plain: $(SRC)
	$(CXX) $(CXXFLAGS) -O0 -o $@ $<

run: benchmark
	./benchmark $(ARGS)

clean:
	rm -f benchmark benchmark_plain gmon.out
