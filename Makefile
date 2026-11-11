# LinuxPulse — build & automation (Member 5). Run every target from the repository root.
# Note: scripts/launch.sh belongs to Member 1; scripts/profile.sh is expected from the profiling stage.

SHELL    := /usr/bin/env bash
SYS_PY   ?= python3
VENV     ?= .venv
# Use the virtualenv interpreter when it exists, otherwise the system one.
PY       := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,$(SYS_PY))
ARGS     ?=

.DEFAULT_GOAL := help
.PHONY: help install check run mock test profile clean

help: ## Show available targets
	@echo "LinuxPulse — available targets:"
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'
	@echo ""
	@echo "Options: ARGS='--interval 1' passes extra flags to main.py (run/mock)."

install: ## Create .venv and install requirements.txt (no sudo, no system packages)
	@command -v $(SYS_PY) >/dev/null || { echo "error: $(SYS_PY) not found"; exit 1; }
	@$(SYS_PY) -c 'import tkinter' 2>/dev/null || { \
	  echo "NOTE: Tkinter is missing. It is an OS package; install it yourself, e.g.:"; \
	  echo "  Arch/Omarchy: sudo pacman -S tk      Debian/Ubuntu: sudo apt install python3-tk"; \
	  echo "  Fedora: sudo dnf install python3-tkinter"; \
	  echo "(continuing with pip dependencies; the GUI will not start until Tkinter is installed)"; }
	@[ -x $(VENV)/bin/python ] || { echo "Creating $(VENV) ..."; $(SYS_PY) -m venv $(VENV); }
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements.txt
	@echo "Install done. Verify with: make check"

check: ## Verify environment (Python, Tkinter, NumPy, Matplotlib, gcc, gprof, top, make)
	@./scripts/check_env.sh

run: ## Launch live monitoring (real data from top)
	$(PY) main.py $(ARGS)

mock: ## Launch with synthetic (mock) data
	$(PY) main.py --mock $(ARGS)

test: ## Run the unittest suite
	$(PY) -m unittest discover -s tests -t . -v

profile: ## Run the profiling script (scripts/profile.sh)
	@[ -x scripts/profile.sh ] || { echo "error: scripts/profile.sh is missing or not executable (profiling-stage deliverable, not yet in the repo)."; exit 1; }
	./scripts/profile.sh

clean: ## Remove caches, build/profiling artifacts (keeps .venv and committed reports)
	find . -path ./$(VENV) -prune -o -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache \) -print0 | xargs -0 -r rm -rf
	find . -path ./$(VENV) -prune -o -type f \( -name '*.pyc' -o -name 'gmon.out' -o -name '*.prof' -o -name '*.log' \) -print0 | xargs -0 -r rm -f
	rm -f profiling/cpp_benchmark/benchmark profiling/cpp_benchmark/benchmark_plain profiling/cpp_benchmark/benchmark_optimized
	rm -rf build dist
	@echo "Clean. (.venv kept; remove it with: rm -rf $(VENV))"
