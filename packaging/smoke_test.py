"""Checks a build on the system it was built on, with the Java runtime and solver jar that went into the app.

    python packaging/smoke_test.py            (after python packaging/build.py)
    python packaging/smoke_test.py --record   (writes smoke_expected.json from this system's answers)

Runs the solver bridge (core/Extension.py) the way the app does: the same solves must give the answers in
smoke_expected.json, also with several calls at once; stopping and a crashed solver must recover; and every form
of the real page must answer without an error. The release workflow runs it after each build, so a system that
breaks the bridge (such as Windows' line endings or text encoding) fails its build.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
WORK = PROJECT / "build"
EXPECTED = Path(__file__).resolve().parent / "smoke_expected.json"
sys.path.insert(0, str(PROJECT))

# Vehicles whose search takes about a second, long enough to crash the solver in the middle of it.
SLOW = [13] * 11 + [12] * 9 + [11] * 4 + [10] * 6 + [9] * 4 + [8] * 5 + [7] * 4 + [6] * 9 + [5] * 5 + [4] * 6 \
    + [3] * 5 + [2] * 5 + [1] * 9


def solver_command() -> list[str]:
    """The built app's Java command: its trimmed runtime, solver jar and OR-Tools jars (as main.java_command)."""
    java = WORK / "runtime" / "bin" / ("java.exe" if sys.platform == "win32" else "java")
    jars = sorted((WORK / "ortools").glob("*.jar"))
    for path in (java, WORK / "solver.jar", *jars):
        if not path.exists():
            sys.exit(f"{path} is missing: run python packaging/build.py first")
    return [str(java), "-Xmx1g", "-cp", os.pathsep.join(map(str, [WORK / "solver.jar", *jars])), "Combine"]


def cases() -> list[tuple[list[int], int, int]]:
    """Vehicle lists and crews, from small to large fleets."""
    rnd = random.Random(5)
    out = []
    for i in range(30):
        n = rnd.randint(2, 30 if i < 26 else 80)
        vehicles = [rnd.randint(1, 13) for _ in range(n)]
        seats = sum(vehicles) if i < 26 else int(sum(vehicles) * 0.97)
        sixes = rnd.randint(0, seats // 12)
        backups = (seats - 6 * sixes) // 5 if i >= 26 else rnd.randint(0, max(0, seats - 6 * sixes) // 5)
        out.append((vehicles, backups or 1, sixes))
    return out


def solve(extension, vehicles, backups, sixes):
    """What the app asks for one form (as app.solve_and_store), plus a group call; or the error the user would see."""
    from core.Master import combos_in_spare_order, sort_by_spare_space
    try:
        results, groups, crews = extension.call_place(sorted(vehicles, reverse=True), backups, sixes)
    except ValueError as e:
        return ["ValueError", str(e)]
    sorted_allocations, sorted_spaces, _, _ = sort_by_spare_space(results)
    combos, listing = combos_in_spare_order(groups, crews, results[2])
    optimized = extension.call_optimize(sorted_allocations, listing, 5, combos, sorted_spaces)
    grouped = extension.call_group(results[2], [1, 0])
    return [[results, groups, crews], optimized, list(grouped)]


def check(condition: bool, message: str) -> None:
    print(("ok    " if condition else "FAIL  ") + message, flush=True)
    if not condition:
        check.failed = True


check.failed = False


def main() -> None:
    os.environ["COMBINE_COMMAND"] = json.dumps(solver_command())
    from core import Extension

    started = time.perf_counter()
    Extension.ready()
    check(True, f"the solver answers ({time.perf_counter() - started:.1f} s to start)")

    answers = [solve(Extension, *case) for case in cases()]
    if "--record" in sys.argv:
        EXPECTED.write_text(json.dumps(answers) + "\n")
        print(f"recorded {EXPECTED}")
        Extension.stop()
        return
    expected = json.loads(EXPECTED.read_text())
    check(answers == expected, f"{len(answers)} solves give the recorded answers")

    # Several calls at once, as when a user clicks twice.
    together = [None] * len(answers)

    def one(k):
        together[k] = solve(Extension, *cases()[k])

    threads = [threading.Thread(target=one, args=(k,)) for k in range(len(answers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check(together == expected, "the same solves, all at once, give the same answers")

    # Closing the window stops the solver; the next call starts it again.
    started = time.perf_counter()
    Extension.stop()
    check(time.perf_counter() - started < 5, f"stop() returns ({time.perf_counter() - started:.2f} s)")
    check(solve(Extension, *cases()[0]) == expected[0], "the solver starts again after stop()")

    # A solver that crashes mid-search fails the call waiting on it, and the next call starts it again.
    crashed = []

    def slow():
        try:
            Extension.call_place(SLOW, 77, 33)
            crashed.append("no error (the search finished before the crash)")
        except RuntimeError as e:
            crashed.append(str(e))

    waiting = threading.Thread(target=slow)
    waiting.start()
    time.sleep(0.1)
    Extension._solver.process.kill()
    waiting.join(timeout=30)
    check(not waiting.is_alive() and "stopped" in crashed[0],
          f"a call in progress when the solver dies raises RuntimeError ({crashed[0] if crashed else 'still waiting'})")
    check(solve(Extension, *cases()[1]) == expected[1], "the solver starts again after a crash")

    # The real page, through Flask, for every form.
    os.environ["PRECLUSTERING_DATA_DIR"] = tempfile.mkdtemp()
    from app import app
    client = app.test_client()
    failures = []
    for vehicles, backups, sixes in cases()[:10]:
        for extra in ({}, {"pull_combinations": "1"}, {"pull_combinations": "1", "use_combos": "1"}):
            form = {"vehlist": ", ".join(map(str, vehicles)), "pers5": str(backups), "pers6": str(sixes), **extra}
            page = client.post("/", data=form, follow_redirects=True)
            if page.status_code != 200 or "Something went wrong" in page.get_data(as_text=True):
                failures.append(form)
    page = client.post("/matrices", data={"people": "137", "crews": "12"}, follow_redirects=True)
    if page.status_code != 200:
        failures.append("matrices")
    page = client.post("/cluster", data={"single_sites": "4", "double_sites": "2", "triple_sites": "1", "cars": "2",
                                         "vans": "1", "buses": "30,45"}, follow_redirects=True)
    if page.status_code != 200 or "Something went wrong" in page.get_data(as_text=True):
        failures.append("cluster")
    check(not failures, f"every form of the page answers without an error {failures or ''}")

    Extension.stop()
    if check.failed:
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
