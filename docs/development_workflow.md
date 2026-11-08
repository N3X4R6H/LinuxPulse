# LINUXPULSE — Development Workflow

**Owner:** Member 5 (build / release / integration)
**Audience:** all members
**Last updated:** 2026-11-08

This is the working agreement for the team: how branches are named, what a
pull request must contain, how code is tested, how commits are written, and
the order in which work lands on `main`.

---

## 1. Repository layout and ownership

The repository root is `linuxpulse/`. Module ownership is fixed and is
reproduced from [`architecture.md`](./architecture.md):

| Path | Owner |
| --- | --- |
| `main.py`, `config.py`, `models.py`, `Makefile`, `.gitignore` | M5 |
| `requirements.txt`, `scripts/launch.sh` | M1 + M5 / M1 |
| `README.md` | M3 + M5 |
| `collector/` | M1 |
| `analytics/` | M2 |
| `gui/` | M3 |
| `visualization/` | M4 |
| `scripts/profile.sh` | M5 |
| `tests/test_parser.py`, `tests/test_collector.py` | M1 |
| `tests/test_analytics.py` | M2 |
| `tests/test_visualization.py`, `tests/test_integration.py` | M4 |
| `profiling/` | M5 + M2 |
| `docs/architecture.md`, `docs/integration_guide.md`, `docs/development_workflow.md` | M5 |
| `docs/collector_design.md` | M1 |
| `docs/analytics_design.md`, `docs/analytics_methodology.md` | M2 |
| `docs/gui_design.md` | M3 |
| `docs/visualization_design.md`, `docs/testing_strategy.md`, `docs/test_results.md`, `docs/report.tex` | M4 |
| `docs/performance_analysis.md`, `docs/presentation.tex` | M5 |
| `assets/` | M3 |

**Rule:** do not edit a file you do not own. If a contract in
`models.py` or `config.py` needs to change, open a PR against M5's file
and describe the impact; M5 propagates the change to the integration
guide. The shared spine (`config.py`, `models.py`, the docs owned by M5)
is the integration surface — changes there are the one thing that can
break everyone, so they are reviewed by M5.

## 2. Branch naming

All work happens on feature branches off `main`. Names are lower-case,
hyphen-separated, prefixed with the member tag and a short topic:

```
<type>/<member>-<topic>
```

| Member tag | Example branch |
| --- | --- |
| M1 (collector) | `feature/m1-top-parser`, `fix/m1-swap-none` |
| M2 (analytics) | `feature/m2-trend-slope` |
| M3 (gui) | `feature/m3-process-table` |
| M4 (visualization) | `feature/m4-cpu-history-plot` |
| M5 (infra) | `feature/m5-makefile`, `chore/m5-gitignore` |

`type` follows Conventional Commits vocabulary: `feature`, `fix`, `docs`,
`test`, `refactor`, `chore`, `perf`. No member works directly on `main`.

## 3. Commit conventions

Conventional Commits, one logical change per commit:

```
<type>(<scope>): <imperative summary>

<optional body: what and why, wrapped at 72 chars>

<optional footer: BREAKING CHANGE:, Closes #n>
```

`scope` is the module short name: `collector`, `analytics`, `gui`,
`viz`, `config`, `models`, `docs`, `build`, `test`. Examples:

```
feat(collector): parse top -H thread rows into ProcessInfo
fix(analytics): treat None usage_percent as skip, not zero
docs(integration): specify trend_slope unit as percent/second
test(viz): cover empty-history placeholder figure
chore(build): add gprof target to Makefile
```

A change to `models.py` or `config.py` that changes a contract other
modules depend on MUST be marked `BREAKING CHANGE:` in the footer and
list the affected call sites, e.g.:

```
feat(models)!: make SystemSnapshot.swap Optional

BREAKING CHANGE: SwapInfo may now be None when host has no swap.
Affected: analytics.engine.analyze, visualization.plot_memory_history,
gui.dashboard.update. See docs/integration_guide.md §Member 2/3/4.
```

## 4. Testing requirements

* Every module ships its unit tests under `tests/` (see ownership table).
* Tests use the standard library `unittest` framework — no pytest plugin
  dependencies. Run the suite with `python -m unittest discover -s tests`
  (or `make test` once the Makefile lands in Stage 2).
* A PR is **not mergeable** unless:
  - `python -m unittest discover -s tests` passes locally.
  - `python -c "import config, models"` succeeds (smoke import).
  - Every new public function or class has at least one test covering the
    happy path and one covering the empty/`None` path (the
    "missing ≠ zero" rule from `models.py`).
* Contracts are tested against the real `models.py` dataclasses — do not
  re-declare shapes in test fixtures; import from `models`.
* Integration tests (`tests/test_integration.py`, M4) exercise the
  collector→analytics→visualization path with a canned `top` fixture, not
  a live system, so they run in CI without root.

## 5. Pull request expectations

A PR description contains:

1. **What** — one-paragraph summary of the change.
2. **Why** — the problem or requirement it addresses.
3. **Contract impact** — does it touch `models.py`, `config.py`, or any
   interface in `integration_guide.md`? If yes, list the call sites that
   must adapt.
4. **Testing** — the exact `python -m unittest ...` command run and its
   pass/fail counts.
5. **Checklist** — `[ ] imports pass`, `[ ] tests pass`,
   `[ ] no files outside my ownership changed`.

Reviewers:

* Same-member PRs: self-review, then M5 (integration) approves.
* Cross-cutting PRs (touching `models`/`config`/docs owned by M5): M5 is
  the required reviewer.
* M5's own PRs: any other member reviews; M5 does not self-merge to
  `main`.

`main` is always green: every merged commit passes the test suite. Do not
merge a PR whose tests are red, even if the failure is "unrelated".

## 6. Integration procedure

Stage 2 work lands on `main` in dependency order so each layer has real
input to consume (mirrors [`integration_guide.md`](./integration_guide.md)
§Integration order):

1. M5 merges `config.py`, `models.py`, docs, package skeleton (this stage).
2. M1 lands `collector/` + `tests/test_parser.py`, `tests/test_collector.py`.
3. M2 lands `analytics/` + `tests/test_analytics.py`.
4. M4 lands `visualization/` + `tests/test_visualization.py`,
   `tests/test_integration.py`.
5. M3 lands `gui/`.
6. M5 lands `main.py` + `Makefile` + `scripts/profile.sh`; runs the full
   smoke test (`make test` then `python main.py --smoke`).

Between steps, M5 re-runs `python -m unittest discover -s tests` on the
merged `main` and posts the result to the PR that introduced the failure.
If a contract needs to change mid-integration, M5 opens the change on the
shared spine first, updates `integration_guide.md` in the same PR, and
only then do affected members rebase.

## 7. Definition of done (Stage 2)

A module is "done" when:

* Its files exist under its owned path and import cleanly
  (`python -c "import <module>"`).
* Its unit tests pass and cover the happy path and the `None`/empty path.
* It conforms to the contracts in `integration_guide.md` — input types,
  output types, function/class names, and error behavior all match.
* It reads all configuration from `config.DEFAULT_CONFIG` and exchanges
  only `models` dataclasses (no ad-hoc dicts, no duplicated literals).
* Its owned doc file (`docs/<module>_design.md`) is written and consistent
  with the integration guide.

Stage 1 (this stage) is done when `config.py`, `models.py`, the three M5
docs, `.gitignore`, `requirements.txt`, and the package skeleton exist,
import cleanly, and the verification commands in the Stage-1 report pass.
