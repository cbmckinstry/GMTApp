"""The calculator, crew-matrices and clustering tabs, served locally for the desktop app (started by main.py)."""
from __future__ import annotations

import os
import re
import secrets
import traceback
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, url_for
from flask_session import Session

from core.Extension import call_optimize, call_place
from core.Master import (
    bucket_by_size,
    cluster,
    combo_sizes,
    combos_in_spare_order,
    compute_matrices,
    compute_ranges,
    count_by_size,
    crews_in_combos,
    flatten,
    restore_order,
    sizes_not_in,
    sum_combos,
    sizes_with_space,
    sort_by_spare_space,
    validate_inputs,
    validate_sites,
    validate_vehicles,
)


# --- app setup ---

# main.py sets this to a per-user folder; running app.py directly uses Flask's instance folder.
DATA_DIR = Path(os.environ.get("PRECLUSTERING_DATA_DIR", "").strip() or Path(__file__).resolve().parent / "instance")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def secret_key() -> str:
    """A random key made on first run and kept, so saved results survive restarts and updates."""
    path = DATA_DIR / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


# The page is the desktop's own (templates/, with the three forms on separate tabs); its static files come from the
# shared core/ submodule.
app = Flask(__name__, template_folder="templates", static_folder="core/static")
app.jinja_env.globals.update(len=len)
app.config.update(
    SECRET_KEY=secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_PERMANENT=False,
    SESSION_USE_SIGNER=True,
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=str(DATA_DIR / "flask_session"),
)
Session(app)


# --- calculator ---

def render_index(**overrides):
    """index.html filled from the session, with any values given here taking precedence."""
    saved_vehlist = session.get("vehlist", [])
    values = dict(
        vehlist=",".join(map(str, saved_vehlist if isinstance(saved_vehlist, list) else [saved_vehlist])),
        pers5=session.get("pers5", ""),
        pers6=session.get("pers6", ""),
        results=session.get("results"),
        sorted_allocations=session.get("sorted_allocations"),
        rem_vehs=session.get("rem_vehs"),
        pull_combinations=session.get("pull_combinations", 0),
        use_combos=session.get("use_combos", 0),
        error_message=None,
        alllist=session.get("alllist"),
        matrices_result=session.get("matrices_result"),
        ranges_result=session.get("ranges_result"),
        people=session.get("people", ""),
        crews=session.get("crews", ""),
        cluster_inputs=session.get("cluster_inputs", {}),
        cluster_results=session.get("cluster_results"),
        cluster_error=None,
        active_tab="structure",
    )
    values.update(overrides)
    return render_template("index.html", **values)


def solve_and_store(vehlist: list[int], pers5: int, pers6: int, pull_combinations: int, use_combos: int) -> None:
    """Places the crews, groups vehicles for whatever does not fit whole, and saves the results in the session.
    Only Combos (`pull_combinations`) keeps just the combos' vehicles and crews; Use Combos (`use_combos`) replaces
    each combo's vehicles with one vehicle of their summed size."""
    results, groups, crews = call_place(sorted(vehlist, reverse=True), pers5, pers6)
    off = [pers5 - results[0][0], pers6 - results[0][1]]

    sorted_allocations, sorted_spaces, sorted_sizes, number = sort_by_spare_space(results)

    combos, listing = combos_in_spare_order(groups, crews, results[2])
    totalhelp = crews_in_combos(combos, sorted_allocations, off)
    combos, listing = call_optimize(sorted_allocations, listing, 5, combos, sorted_spaces)
    combos = combo_sizes(combos, sorted_sizes)

    restored_vehs, restored_all, restored_spaces = restore_order(vehlist, sorted_sizes, sorted_allocations, sorted_spaces)

    session["sorted_allocations"] = [
        [restored_vehs[i], restored_all[i], restored_spaces[i], number[i]]
        for i in range(len(sorted_sizes))
    ]
    session["totalhelp"] = totalhelp
    session["alllist"] = bucket_by_size(combos, listing)
    session["rem_vehs"] = count_by_size(sizes_not_in(sizes_with_space(sorted_spaces, sorted_sizes), combos))
    session["results"] = [results[0], off]
    session["pull_combinations"] = pull_combinations
    session["use_combos"] = use_combos

    if pull_combinations == 0:
        session["pers5"] = pers5
        session["pers6"] = pers6
        if use_combos == 1:
            session["vehlist"] = sum_combos(vehlist, combos)
    else:
        session["vehlist"] = flatten(combos)
        session["pers6"] = totalhelp[1]
        session["pers5"] = totalhelp[0]


def handle_submit():
    """Validates the posted form, solves it, and redirects back to the page; re-renders the page on bad input."""
    pers5_text = request.form.get("pers5") or "0"
    pers6_text = request.form.get("pers6") or "0"
    vehicle_texts = [x for x in re.split(r"[,\s]+", request.form.get("vehlist", "").strip()) if x]
    vehstring = ",".join(vehicle_texts)
    try:
        pull_combinations = int(request.form.get("pull_combinations", 0))
        # The page lets only one be ticked; if both arrive anyway, Only Combos wins.
        use_combos = 0 if pull_combinations else int(request.form.get("use_combos", 0))
        session["vehlist"] = vehstring
        validate_vehicles(vehicle_texts)
        vehlist = [int(x) for x in vehicle_texts]
        validate_inputs(vehlist, pers5_text, pers6_text)
        solve_and_store(vehlist, int(pers5_text), int(pers6_text), pull_combinations, use_combos)
        return redirect(url_for("index", _anchor="vehicles"))

    except Exception as e:
        if isinstance(e, ValueError):
            message = str(e)
        else:
            traceback.print_exc()
            message = "Something went wrong while calculating. Please try again."
        return render_index(
            error_message=message,
            vehlist=vehstring,
            pers5=pers5_text,
            pers6=pers6_text,
            pull_combinations=1 if request.form.get("pull_combinations") else 0,
            use_combos=1 if request.form.get("use_combos") else 0,
            results=None,
            sorted_allocations=None,
            rem_vehs=None,
            alllist=None,
            active_tab="vehicles",
        )


# --- routes ---

@app.route("/", methods=["GET", "POST"], strict_slashes=False)
def index():
    if request.method == "GET":
        return render_index()
    return handle_submit()


@app.route("/matrices", methods=["POST"])
def matrices():
    try:
        people_input = request.form.get("people", "").strip()
        crews_input = request.form.get("crews", "").strip()
        people = int(people_input) if people_input else 0
        crews = int(crews_input) if crews_input else 0
        session["matrices_result"] = compute_matrices(people, crews)
        session["ranges_result"] = compute_ranges(people)
        session["people"] = people
        session["crews"] = crews
    except ValueError:
        pass    # non-numeric input: keep the previous result
    return redirect(url_for("index", _anchor="structure"))


# The site counts on the clustering form, in the order cluster takes them.
CLUSTER_FIELDS = ["single_sites", "double_sites", "triple_sites", "cars", "vans"]


@app.route("/cluster", methods=["POST"])
def clustering():
    """Places single, double and triple crew sites in cars and vans; re-renders the page on bad input."""
    texts = {name: request.form.get(name, "").strip() or "0" for name in CLUSTER_FIELDS}
    bus_texts = [x for x in re.split(r"[,\s]+", request.form.get("buses", "").strip()) if x]
    texts["buses"] = ",".join(bus_texts)
    session["cluster_inputs"] = texts
    try:
        counts = [int(texts[name]) for name in CLUSTER_FIELDS]
        buses = validate_vehicles(bus_texts, "Bus Entries")
        validate_sites(*counts, buses)
        session["cluster_results"] = cluster(*counts, buses)
        return redirect(url_for("index", _anchor="clustering"))

    except Exception as e:
        if isinstance(e, ValueError):
            message = str(e)
        else:
            traceback.print_exc()
            message = "Something went wrong while calculating. Please try again."
        return render_index(cluster_error=message, cluster_results=None, active_tab="clustering")


@app.route("/view_once", methods=["POST"], strict_slashes=False)
def view_once():
    """The page reports views here for the web version's visitor log; the desktop app records nothing."""
    return ("", 204)


if __name__ == "__main__":
    app.run()
