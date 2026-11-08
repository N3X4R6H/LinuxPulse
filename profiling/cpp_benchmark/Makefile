CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -pedantic
PROFILE_FLAGS = -O0 -pg

TARGET = benchmark
SOURCE = benchmark.cpp

.PHONY: all run profile clean optimized

all: $(TARGET)

$(TARGET): $(SOURCE)
	$(CXX) $(CXXFLAGS) $(PROFILE_FLAGS) -o $(TARGET) $(SOURCE)

run: $(TARGET)
	./$(TARGET)

profile: $(TARGET)
	rm -f gmon.out ../results/gprof_report.txt
	./$(TARGET)
	gprof ./$(TARGET) gmon.out > ../results/gprof_report.txt
	@echo "Created ../results/gprof_report.txt"

optimized:
	$(CXX) $(CXXFLAGS) -O2 -o benchmark_optimized $(SOURCE)

clean:
	rm -f $(TARGET) benchmark_optimized gmon.out ../results/gprof_report.txt
