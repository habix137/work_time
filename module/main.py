# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, Response
import json
import os
import jdatetime
from datetime import datetime as dt

BASE_DIR = os.path.dirname(__file__)
template_dir = os.path.join(BASE_DIR, 'templates')
app = Flask(__name__, template_folder=template_dir)
app.secret_key = 'your-secret-key-here'

DATA_FILE = os.path.join(os.path.dirname(BASE_DIR), 'work_data.json')

DEFAULT_GROUP = "Ungrouped"

# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
def load_data():
    """
    Backward-compatible loader:
    - Always returns dict with keys: { "projects": {...}, "groups": [...] }
    - Ensures each project has: tags(list), time_logs(list), group(str)
    - Old datasets (no groups / no group field) => projects go to 'Ungrouped'
    """
    data = {"projects": {}, "groups": [DEFAULT_GROUP]}

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(loaded)
            except json.JSONDecodeError:
                pass

    if "projects" not in data or not isinstance(data.get("projects"), dict):
        data["projects"] = {}

    if "groups" not in data or not isinstance(data.get("groups"), list):
        data["groups"] = [DEFAULT_GROUP]

    # normalize groups
    normalized_groups = []
    seen = set()
    for g in data["groups"]:
        if isinstance(g, str):
            g = g.strip()
            if g and g not in seen:
                normalized_groups.append(g)
                seen.add(g)

    if DEFAULT_GROUP not in seen:
        normalized_groups.insert(0, DEFAULT_GROUP)
        seen.add(DEFAULT_GROUP)

    data["groups"] = normalized_groups

    # normalize projects
    for pname, p in list(data["projects"].items()):
        if not isinstance(p, dict):
            data["projects"][pname] = {"tags": [], "time_logs": [], "group": DEFAULT_GROUP}
            continue

        if "tags" not in p or not isinstance(p.get("tags"), list):
            p["tags"] = []
        if "time_logs" not in p or not isinstance(p.get("time_logs"), list):
            p["time_logs"] = []
        if "group" not in p or not isinstance(p.get("group"), str) or not p.get("group").strip():
            p["group"] = DEFAULT_GROUP

        # if project group is unknown, add it to groups
        grp = p["group"].strip()
        p["group"] = grp
        if grp not in seen:
            data["groups"].append(grp)
            seen.add(grp)

    return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_today_persian():
    return jdatetime.date.today().isoformat()


def _safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except (ValueError, TypeError):
        return default


def compute_project_total_hours(project: dict) -> float:
    total = 0.0
    for log in project.get("time_logs", []) or []:
        total += _safe_float(log.get("duration", 0.0), 0.0)
    return total


def compute_all_totals(projects: dict):
    per_project = {}
    overall = 0.0
    for name, proj in (projects or {}).items():
        t = compute_project_total_hours(proj or {})
        per_project[name] = round(t, 2)
        overall += t
    return per_project, round(overall, 2)


def compute_group_totals(data: dict):
    """
    Returns {group_name: hours_total}
    """
    projects = data.get("projects", {})
    group_totals = {}

    for pname, p in projects.items():
        grp = (p.get("group") or DEFAULT_GROUP).strip() or DEFAULT_GROUP
        group_totals.setdefault(grp, 0.0)
        group_totals[grp] += compute_project_total_hours(p)

    return {g: round(v, 2) for g, v in group_totals.items()}


def group_projects(projects: dict, groups: list):
    """
    Returns ordered dict-like structure:
      { group_name: [(project_name, project_dict), ...], ... }
    Groups are ordered by data['groups'].
    """
    grouped = {g: [] for g in groups}
    # include unknown groups if any
    for pname, p in (projects or {}).items():
        grp = (p.get("group") or DEFAULT_GROUP).strip() or DEFAULT_GROUP
        if grp not in grouped:
            grouped[grp] = []
        grouped[grp].append((pname, p))

    # sort projects by name inside each group
    for g in grouped:
        grouped[g].sort(key=lambda x: x[0].lower())

    return grouped


def generate_markdown_report(data, filters=None):
    projects = data.get("projects", {})
    groups = data.get("groups", [DEFAULT_GROUP])

    report = "# Work Time Report\n\n"
    report += f"Generated on: {get_today_persian()}\n\n"

    if filters:
        used = []
        if filters.get("group"):
            used.append(f"Group: {filters['group']}")
        if filters.get("project"):
            used.append(f"Project: {filters['project']}")
        if filters.get("tag"):
            used.append(f"Tag: {filters['tag']}")
        if filters.get("date_from"):
            used.append(f"From: {filters['date_from']}")
        if filters.get("date_to"):
            used.append(f"To: {filters['date_to']}")
        if used:
            report += "**Filters:** " + ", ".join(used) + "\n\n"

    total_overall_hours = 0.0

    grouped = group_projects(projects, groups)

    for group_name, items in grouped.items():
        # group filter
        if filters and filters.get("group") and filters["group"] != group_name:
            continue

        group_any = False
        group_total = 0.0
        group_section = f"## Group: {group_name}\n\n"

        for project_name, project in items:
            # project filter
            if filters and filters.get("project") and filters["project"] != project_name:
                continue

            filtered_logs = list(project.get("time_logs", [])) or []
            if not filtered_logs:
                continue

            if filters:
                if filters.get("tag"):
                    if filters["tag"] not in project.get("tags", []):
                        filtered_logs = []
                if filters.get("date_from"):
                    filtered_logs = [log for log in filtered_logs if log.get("date", "") >= filters["date_from"]]
                if filters.get("date_to"):
                    filtered_logs = [log for log in filtered_logs if log.get("date", "") <= filters["date_to"]]

            if not filtered_logs:
                continue

            group_any = True
            project_total = 0.0

            group_section += f"### {project_name}\n\n"
            group_section += f"**Tags:** {', '.join(project.get('tags', [])) or '—'}\n\n"

            for log in sorted(filtered_logs, key=lambda x: (x.get("date", ""), x.get("start_time", ""))):
                d = _safe_float(log.get("duration", 0.0), 0.0)
                project_total += d
                group_total += d
                total_overall_hours += d
                group_section += (
                    f"- **{log.get('date','—')}**: "
                    f"{log.get('start_time','—')} - {log.get('end_time','—')} "
                    f"({round(d, 2)} hours)\n"
                )

            group_section += f"\n**Project Total: {round(project_total, 2)} hours**\n\n"

        if group_any:
            group_section += f"**Group Total: {round(group_total, 2)} hours**\n\n"
            report += group_section

    report += f"**Overall Total: {round(total_overall_hours, 2)} hours**\n"
    return report


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    data = load_data()
    projects = data.get("projects", {})
    groups = data.get("groups", [DEFAULT_GROUP])
    today = get_today_persian()

    today_logs = {}
    for project_name, project in projects.items():
        logs = project.get("time_logs", [])
        today_logs[project_name] = [log for log in logs if log.get("date") == today]

    project_totals, overall_total = compute_all_totals(projects)
    group_totals = compute_group_totals(data)
    grouped_projects = group_projects(projects, groups)

    return render_template(
        "index.html",
        projects=projects,
        groups=groups,
        grouped_projects=grouped_projects,
        today_persian=today,
        today_logs=today_logs,
        project_totals=project_totals,
        group_totals=group_totals,
        overall_total=overall_total,
    )


@app.route("/get_all_time_totals", methods=["GET"])
def get_all_time_totals():
    data = load_data()
    projects = data.get("projects", {})
    per_project, overall = compute_all_totals(projects)
    per_group = compute_group_totals(data)
    return {
        "status": "success",
        "overall_total": overall,
        "per_project": per_project,
        "per_group": per_group,
    }


# ───────────────────────────────
# Groups CRUD
# ───────────────────────────────
@app.route("/add_group", methods=["POST"])
def add_group():
    data = load_data()
    name = (request.form.get("group_name") or "").strip()
    if not name:
        flash("Group name is required", "error")
        return redirect(url_for("index"))

    if name in data["groups"]:
        flash("Group already exists", "error")
        return redirect(url_for("index"))

    data["groups"].append(name)
    save_data(data)
    flash(f'Added group "{name}"', "success")
    return redirect(url_for("index"))


@app.route("/rename_group", methods=["POST"])
def rename_group():
    data = load_data()
    old = (request.form.get("old_group") or "").strip()
    new = (request.form.get("new_group") or "").strip()

    if not old or not new:
        flash("Both old and new group names are required", "error")
        return redirect(url_for("index"))

    if old == DEFAULT_GROUP:
        flash("You cannot rename Ungrouped", "error")
        return redirect(url_for("index"))

    if old not in data["groups"]:
        flash("Group not found", "error")
        return redirect(url_for("index"))

    if new in data["groups"]:
        flash("New group name already exists", "error")
        return redirect(url_for("index"))

    # rename in group list
    data["groups"] = [new if g == old else g for g in data["groups"]]

    # rename in projects
    for pname, p in data.get("projects", {}).items():
        if (p.get("group") or DEFAULT_GROUP) == old:
            p["group"] = new

    save_data(data)
    flash(f'Renamed group "{old}" → "{new}"', "success")
    return redirect(url_for("index"))


@app.route("/delete_group", methods=["POST"])
def delete_group():
    data = load_data()
    name = (request.form.get("group") or "").strip()

    if not name:
        flash("Group name is required", "error")
        return redirect(url_for("index"))

    if name == DEFAULT_GROUP:
        flash("You cannot delete Ungrouped", "error")
        return redirect(url_for("index"))

    if name not in data["groups"]:
        flash("Group not found", "error")
        return redirect(url_for("index"))

    # move projects to Ungrouped
    for pname, p in data.get("projects", {}).items():
        if (p.get("group") or DEFAULT_GROUP) == name:
            p["group"] = DEFAULT_GROUP

    # remove from groups
    data["groups"] = [g for g in data["groups"] if g != name]
    save_data(data)
    flash(f'Deleted group "{name}" (projects moved to Ungrouped)', "success")
    return redirect(url_for("index"))


# ───────────────────────────────
# Project CRUD
# ───────────────────────────────
@app.route("/add_project", methods=["POST"])
def add_project():
    data = load_data()
    name = (request.form.get("name") or "").strip()
    tags_str = request.form.get("tags", "") or ""
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    group = (request.form.get("group") or DEFAULT_GROUP).strip() or DEFAULT_GROUP

    if not name:
        flash("Project name is required", "error")
        return redirect(url_for("index"))

    projects = data.setdefault("projects", {})
    if name in projects:
        flash("Project already exists", "error")
        return redirect(url_for("index"))

    # ensure group exists
    if group not in data["groups"]:
        data["groups"].append(group)

    projects[name] = {"tags": tags, "time_logs": [], "group": group}
    save_data(data)
    flash(f'Added project "{name}" in group "{group}"', "success")
    return redirect(url_for("index"))


@app.route("/update_project", methods=["POST"])
def update_project():
    data = load_data()
    project_name = (request.form.get("project") or "").strip()
    tags_str = request.form.get("tags", "") or ""
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    group = (request.form.get("group") or DEFAULT_GROUP).strip() or DEFAULT_GROUP

    projects = data.get("projects", {})
    if project_name not in projects:
        flash("Project not found", "error")
        return redirect(url_for("index"))

    # ensure group exists
    if group not in data["groups"]:
        data["groups"].append(group)

    projects[project_name]["tags"] = tags
    projects[project_name]["group"] = group
    save_data(data)
    flash(f'Updated project "{project_name}"', "success")
    return redirect(url_for("index"))


@app.route("/reset_project", methods=["POST"])
def reset_project():
    data = load_data()
    project_name = (request.form.get("project") or "").strip()
    projects = data.get("projects", {})
    if project_name in projects:
        projects[project_name]["time_logs"] = []
        projects[project_name].pop("current_session", None)
        save_data(data)
        flash(f'Reset logs for project "{project_name}"', "success")
    else:
        flash("Project not found", "error")
    return redirect(url_for("index"))


@app.route("/delete_project/<project_name>")
def delete_project(project_name):
    data = load_data()
    projects = data.get("projects", {})
    if project_name in projects:
        del projects[project_name]
        save_data(data)
        flash(f'Deleted project "{project_name}"', "success")
    else:
        flash("Project not found", "error")
    return redirect(url_for("index"))


# ───────────────────────────────
# Time Logging
# ───────────────────────────────
@app.route("/start_time_log", methods=["POST"])
def start_time_log():
    data = load_data()
    project = (request.form.get("project") or "").strip()
    start_time_iso = dt.now().isoformat(timespec="seconds")

    projects = data.setdefault("projects", {})
    if project not in projects:
        return {"status": "error", "message": "Project not found"}, 400

    if projects[project].get("current_session"):
        return {"status": "error", "message": "Session already running"}, 400

    projects[project]["current_session"] = {"start_time": start_time_iso, "date": get_today_persian()}
    save_data(data)
    return {"status": "success", "start_time": start_time_iso}


@app.route("/end_time_log", methods=["POST"])
def end_time_log():
    data = load_data()
    project = (request.form.get("project") or "").strip()
    projects = data.get("projects", {})

    if project not in projects or "current_session" not in projects[project]:
        return {"status": "error", "message": "No active session"}, 400

    current_session = projects[project]["current_session"]
    end_time_iso = dt.now().isoformat(timespec="seconds")

    start_dt = dt.fromisoformat(current_session["start_time"])
    end_dt = dt.fromisoformat(end_time_iso)

    duration = round((end_dt - start_dt).total_seconds() / 3600, 2)
    if duration < 0:
        duration = 0.0

    time_log = {
        "date": current_session.get("date", get_today_persian()),
        "start_time": start_dt.strftime("%H:%M:%S"),
        "end_time": end_dt.strftime("%H:%M:%S"),
        "duration": duration,
    }

    projects[project].setdefault("time_logs", []).append(time_log)
    projects[project].pop("current_session", None)
    save_data(data)

    return {"status": "success", "duration": duration, "log": time_log}


@app.route("/get_today_time_logs", methods=["GET"])
def get_today_time_logs():
    data = load_data()
    today = get_today_persian()
    projects = data.get("projects", {})
    result = {}
    for project, info in projects.items():
        logs = info.get("time_logs", [])
        today_logs = [log for log in logs if log.get("date") == today]
        if today_logs:
            result[project] = today_logs
    return {"status": "success", "logs": result}


@app.route("/get_current_session", methods=["GET"])
def get_current_session():
    data = load_data()
    project = (request.args.get("project") or "").strip()
    projects = data.get("projects", {})
    if project in projects and "current_session" in projects[project]:
        return {"status": "success", "current_session": projects[project]["current_session"]}
    return {"status": "error", "message": "No active session"}, 404


@app.route("/get_last_time_log", methods=["GET"])
def get_last_time_log():
    data = load_data()
    project = (request.args.get("project") or "").strip()
    projects = data.get("projects", {})
    if project in projects and projects[project].get("time_logs"):
        last_log = max(projects[project]["time_logs"], key=lambda x: (x.get("date", ""), x.get("start_time", "")))
        return {"status": "success", "last_log": last_log}
    return {"status": "error", "message": "No time logs found"}, 404


@app.route("/delete_time_log", methods=["POST"])
def delete_time_log():
    data = load_data()
    project = (request.form.get("project") or "").strip()
    date = (request.form.get("date") or "").strip()
    start_time = (request.form.get("start_time") or "").strip()

    projects = data.get("projects", {})
    if project in projects and "time_logs" in projects[project]:
        before = len(projects[project]["time_logs"])
        projects[project]["time_logs"] = [
            log for log in projects[project]["time_logs"]
            if not (log.get("date") == date and log.get("start_time") == start_time)
        ]
        after = len(projects[project]["time_logs"])
        if after < before:
            save_data(data)
            return {"status": "success"}
    return {"status": "error", "message": "Log not found"}, 404


# ───────────────────────────────
# Report
# ───────────────────────────────
@app.route("/report")
def report():
    data = load_data()
    filters = {}
    if request.args:
        filters["group"] = request.args.get("group") or None
        filters["project"] = request.args.get("project") or None
        filters["tag"] = request.args.get("tag") or None
        filters["date_from"] = request.args.get("date_from") or None
        filters["date_to"] = request.args.get("date_to") or None

    md_report = generate_markdown_report(data, filters)
    return render_template(
        "report.html",
        report=md_report,
        projects=data.get("projects", {}),
        groups=data.get("groups", [DEFAULT_GROUP]),
        filters=filters
    )


@app.route("/download_report")
def download_report():
    data = load_data()
    filters = {}
    if request.args:
        filters["group"] = request.args.get("group") or None
        filters["project"] = request.args.get("project") or None
        filters["tag"] = request.args.get("tag") or None
        filters["date_from"] = request.args.get("date_from") or None
        filters["date_to"] = request.args.get("date_to") or None

    md_report = generate_markdown_report(data, filters)
    return Response(
        md_report,
        mimetype="text/markdown",
        headers={"Content-Disposition": "attachment;filename=work_report.md"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=False)
