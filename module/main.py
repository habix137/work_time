# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, Response, jsonify
import json
import os
import jdatetime
from datetime import datetime as dt

# ──────────────────────────────────────────────────────────────────────────────
# Flask setup
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
template_dir = os.path.join(BASE_DIR, 'templates')
app = Flask(__name__, template_folder=template_dir)
app.secret_key = 'your-secret-key-here'

# Store data one level above module/ by default
DATA_FILE = os.path.join(os.path.dirname(BASE_DIR), 'work_data.json')

# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return {'projects': {}}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_today_persian():
    """Return today’s date in YYYY-MM-DD (Persian calendar)."""
    return jdatetime.date.today().isoformat()

def generate_markdown_report(projects, filters=None):
    """Generate a Markdown report for projects, with optional filters."""
    report = "# Work Time Report\n\n"
    report += f"Generated on: {get_today_persian()}\n\n"

    if filters:
        used = []
        if filters.get('project'):   used.append(f"Project: {filters['project']}")
        if filters.get('tag'):       used.append(f"Tag: {filters['tag']}")
        if filters.get('date_from'): used.append(f"From: {filters['date_from']}")
        if filters.get('date_to'):   used.append(f"To: {filters['date_to']}")
        if used:
            report += f"**Filters:** " + ", ".join(used) + "\n\n"

    total_overall_hours = 0.0
    for project_name, project in projects.items():
        if filters and filters.get('project') and filters['project'] != project_name:
            continue

        filtered_logs = list(project.get('time_logs', []))
        if not filtered_logs:
            continue

        if filters:
            if filters.get('tag'):
                # Only include if the *project* has that tag
                if filters['tag'] not in project.get('tags', []):
                    filtered_logs = []
                # else keep filtered_logs as-is
            if filters.get('date_from'):
                filtered_logs = [log for log in filtered_logs if log['date'] >= filters['date_from']]
            if filters.get('date_to'):
                filtered_logs = [log for log in filtered_logs if log['date'] <= filters['date_to']]

        if not filtered_logs:
            continue

        project_total = 0.0
        report += f"## {project_name}\n\n"
        report += f"**Tags:** {', '.join(project.get('tags', [])) or '—'}\n\n"

        for log in sorted(filtered_logs, key=lambda x: (x['date'], x['start_time'])):
            project_total += float(log['duration'])
            total_overall_hours += float(log['duration'])
            report += f"- **{log['date']}**: {log['start_time']} - {log['end_time']} ({round(log['duration'], 2)} hours)\n"

        report += f"\n**Project Total: {round(project_total, 2)} hours**\n\n"

    report += f"**Overall Total: {round(total_overall_hours, 2)} hours**\n"
    return report

# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    data = load_data()
    projects = data.get('projects', {})
    today = get_today_persian()
    today_logs = {}
    for project_name, project in projects.items():
        logs = project.get('time_logs', [])
        today_logs[project_name] = [log for log in logs if log['date'] == today]
    return render_template('index.html',
                           projects=projects,
                           today_persian=today,
                           today_logs=today_logs)

# ───────────────────────────────
# Report
# ───────────────────────────────
@app.route('/report')
def report():
    data = load_data()
    projects = data.get('projects', {})
    filters = {}
    if request.args:
        filters['project'] = request.args.get('project') or None
        filters['tag'] = request.args.get('tag') or None
        filters['date_from'] = request.args.get('date_from') or None
        filters['date_to'] = request.args.get('date_to') or None

    md_report = generate_markdown_report(projects, filters)
    return render_template('report.html', report=md_report, projects=projects, filters=filters)

@app.route('/download_report')
def download_report():
    data = load_data()
    projects = data.get('projects', {})
    filters = {}
    if request.args:
        filters['project'] = request.args.get('project') or None
        filters['tag'] = request.args.get('tag') or None
        filters['date_from'] = request.args.get('date_from') or None
        filters['date_to'] = request.args.get('date_to') or None

    md_report = generate_markdown_report(projects, filters)
    return Response(md_report,
                    mimetype='text/markdown',
                    headers={'Content-Disposition': 'attachment;filename=work_report.md'})

# ───────────────────────────────
# Project CRUD
# ───────────────────────────────
@app.route('/add_project', methods=['POST'])
def add_project():
    data = load_data()
    name = request.form.get('name', '').strip()
    tags_str = request.form.get('tags', '')
    tags = [t.strip() for t in tags_str.split(',') if t.strip()]
    if not name:
        flash('Project name is required', 'error')
        return redirect(url_for('index'))

    projects = data.setdefault('projects', {})
    if name in projects:
        flash('Project already exists', 'error')
        return redirect(url_for('index'))

    projects[name] = {'tags': tags, 'time_logs': []}
    save_data(data)
    flash(f'Added project "{name}" with tags {", ".join(tags) or "—"}', 'success')
    return redirect(url_for('index'))

@app.route('/update_project', methods=['POST'])
def update_project():
    """Update tags for an existing project (simple inline editor)."""
    data = load_data()
    project_name = request.form.get('project', '').strip()
    tags_str = request.form.get('tags', '')
    tags = [t.strip() for t in tags_str.split(',') if t.strip()]

    projects = data.get('projects', {})
    if project_name not in projects:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    projects[project_name]['tags'] = tags
    save_data(data)
    flash(f'Updated tags for "{project_name}"', 'success')
    return redirect(url_for('index'))

@app.route('/reset_project', methods=['POST'])
def reset_project():
    data = load_data()
    project_name = request.form['project'].strip()
    projects = data.get('projects', {})
    if project_name in projects:
        projects[project_name]['time_logs'] = []
        projects[project_name].pop('current_session', None)
        save_data(data)
        flash(f'Reset logs for project "{project_name}"', 'success')
    else:
        flash('Project not found', 'error')
    return redirect(url_for('index'))

@app.route('/delete_project/<project_name>')
def delete_project(project_name):
    data = load_data()
    projects = data.get('projects', {})
    if project_name in projects:
        del projects[project_name]
        save_data(data)
        flash(f'Deleted project "{project_name}"', 'success')
    else:
        flash('Project not found', 'error')
    return redirect(url_for('index'))

# ───────────────────────────────
# Time Logging
# ───────────────────────────────
@app.route('/start_time_log', methods=['POST'])
def start_time_log():
    data = load_data()
    project = request.form.get('project', '').strip()
    start_time_iso = dt.now().isoformat(timespec='seconds')

    projects = data.setdefault('projects', {})
    if project not in projects:
        return {'status': 'error', 'message': 'Project not found'}, 400

    # Prevent overlapping session for the same project
    if projects[project].get('current_session'):
        return {'status': 'error', 'message': 'Session already running'}, 400

    projects[project]['current_session'] = {
        'start_time': start_time_iso,
        'date': get_today_persian()
    }
    save_data(data)
    return {'status': 'success', 'start_time': start_time_iso}

@app.route('/end_time_log', methods=['POST'])
def end_time_log():
    data = load_data()
    project = request.form.get('project', '').strip()
    projects = data.get('projects', {})

    if project not in projects or 'current_session' not in projects[project]:
        return {'status': 'error', 'message': 'No active session'}, 400

    current_session = projects[project]['current_session']
    end_time_iso = dt.now().isoformat(timespec='seconds')

    start_dt = dt.fromisoformat(current_session['start_time'])
    end_dt = dt.fromisoformat(end_time_iso)
    duration = round((end_dt - start_dt).total_seconds() / 3600, 2)

    time_log = {
        'date': current_session['date'],
        'start_time': start_dt.strftime('%H:%M:%S'),
        'end_time': end_dt.strftime('%H:%M:%S'),
        'duration': duration
    }
    projects[project].setdefault('time_logs', []).append(time_log)
    projects[project].pop('current_session', None)
    save_data(data)

    return {'status': 'success', 'duration': duration, 'log': time_log}

@app.route('/get_today_time_logs', methods=['GET'])
def get_today_time_logs():
    data = load_data()
    today = get_today_persian()
    projects = data.get('projects', {})
    result = {}
    for project, info in projects.items():
        if 'time_logs' in info:
            today_logs = [log for log in info['time_logs'] if log['date'] == today]
            if today_logs:
                result[project] = today_logs
    return {'status': 'success', 'logs': result}

@app.route('/get_current_session', methods=['GET'])
def get_current_session():
    data = load_data()
    project = request.args.get('project', '').strip()
    projects = data.get('projects', {})
    if project in projects and 'current_session' in projects[project]:
        return {'status': 'success', 'current_session': projects[project]['current_session']}
    return {'status': 'error', 'message': 'No active session'}, 404

@app.route('/get_last_time_log', methods=['GET'])
def get_last_time_log():
    data = load_data()
    project = request.args.get('project', '').strip()
    projects = data.get('projects', {})
    if project in projects and projects[project].get('time_logs'):
        last_log = max(projects[project]['time_logs'], key=lambda x: (x['date'], x['start_time']))
        return {'status': 'success', 'last_log': last_log}
    return {'status': 'error', 'message': 'No time logs found'}, 404

@app.route('/delete_time_log', methods=['POST'])
def delete_time_log():
    data = load_data()
    project = request.form.get('project', '').strip()
    date = request.form.get('date', '').strip()
    start_time = request.form.get('start_time', '').strip()

    projects = data.get('projects', {})
    if project in projects and 'time_logs' in projects[project]:
        before = len(projects[project]['time_logs'])
        projects[project]['time_logs'] = [
            log for log in projects[project]['time_logs']
            if not (log['date'] == date and log['start_time'] == start_time)
        ]
        after = len(projects[project]['time_logs'])
        if after < before:
            save_data(data)
            return {'status': 'success'}
    return {'status': 'error', 'message': 'Log not found'}, 404

# ───────────────────────────────
# Entry
# ───────────────────────────────
if __name__ == '__main__':
    # Run as: python module/main.py
    app.run(debug=True)
