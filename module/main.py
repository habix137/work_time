# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash
import json
import os
import jdatetime
from datetime import datetime as dt
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
DATA_FILE = 'work_data.json'

# ──────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ──────────────────────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_today_persian():
    """Return today’s date in YYYY-MM-DD (Persian calendar)."""
    return jdatetime.date.today().isoformat()

def get_remaining_workdays(deadline_date, workdays_count):
    """
    Calculate available days between today and deadline, considering how many days
    per week you want to work.
    `workdays_count` is the number of days you want to work per week (0-7).
    """
    today = jdatetime.date.today()
    # Parse deadline; default = last day of current month
    try:
        y, m, d = map(int, deadline_date.split('-'))
        deadline = jdatetime.date(y, m, d)
    except Exception:
        next_month = jdatetime.date(today.year, today.month, 1) + jdatetime.timedelta(days=32)
        deadline = jdatetime.date(next_month.year, next_month.month, 1) - jdatetime.timedelta(days=1)
    if deadline < today:
        return 0
    # If workdays_count is 0 or 7, count all days
    if workdays_count in (0, 7):
        return (deadline - today).days + 1
    # Calculate workdays based on number of days per week
    total_days = (deadline - today).days + 1
    full_weeks = total_days // 7
    remaining_days = total_days % 7
    total_workdays = full_weeks * workdays_count
    # Add remaining days in the partial week
    if remaining_days > 0:
        total_workdays += min(remaining_days, workdays_count)
    return total_workdays

# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    data = load_data()
    for company_name, company in data.items():
        # Sort logs newest-first for display
        company['log'] = dict(sorted(company['log'].items(), reverse=True))
        # Defaults
        company.setdefault('tasks', [])
        company.setdefault('workdays_count', 7)  # Default to working every day
        company.setdefault('deadline', '')
        # Calculate totals
        total_hours = 0.0
        for entry in company['log'].values():
            hours = float(entry.get('hours', 0)) if isinstance(entry, dict) else float(entry)
            total_hours += hours
        company['total_hours'] = round(total_hours, 1)
        company['remaining_hours'] = max(company['goal'] - total_hours, 0)
        # Progress percentage (cap at 100 for bar width)
        company['progress'] = round((total_hours / company['goal']) * 100, 1) if company['goal'] else 0.0
        # Recommended daily hours
        remaining_days = get_remaining_workdays(company['deadline'], company.get('workdays_count', 7))
        company['remaining_days'] = remaining_days
        if remaining_days:
            company['recommended_hours'] = round(company['remaining_hours'] / remaining_days, 1)
        else:
            company['recommended_hours'] = None
    return render_template('index.html', data=data, today_persian=get_today_persian())

# ───────────────────────────────
# POST: Log work hours
# ───────────────────────────────
@app.route('/log', methods=['POST'])
def log_work():
    data = load_data()
    company = request.form['company'].strip()
    date = request.form['date'] or get_today_persian()
    description = request.form['description'].strip()
    # Validate hours
    try:
        hours = float(request.form['hours'])
        if hours <= 0:
            raise ValueError
    except ValueError:
        flash('Hours must be a positive number', 'error')
        return redirect(url_for('index'))
    data.setdefault(company, {'goal': 0, 'log': {}, 'tasks': [], 'workdays_count': 7})
    # Merge if same date already exists
    if date in data[company]['log'] and isinstance(data[company]['log'][date], dict):
        data[company]['log'][date]['hours'] += hours
        if description:
            data[company]['log'][date]['description'] = description
    else:
        data[company]['log'][date] = {'hours': hours, 'description': description}
    save_data(data)
    flash(f'Logged {hours} h for {company} on {date}', 'success')
    return redirect(url_for('index'))

# ───────────────────────────────
# POST: Set goal
# ───────────────────────────────
@app.route('/set_goal', methods=['POST'])
def set_goal():
    data = load_data()
    company = request.form['company'].strip()
    try:
        workdays_count = int(request.form.get('workdays_count', 7))
        if workdays_count < 0 or workdays_count > 7:
            raise ValueError
    except ValueError:
        flash('Workdays per week must be between 0 and 7', 'error')
        return redirect(url_for('index'))
    deadline = request.form.get('deadline') or ''
    try:
        goal = float(request.form['goal'])
        if goal < 0:
            raise ValueError
    except ValueError:
        flash('Goal must be a non-negative number', 'error')
        return redirect(url_for('index'))
    data.setdefault(company, {'log': {}, 'tasks': []})
    data[company].update({
        'goal': goal,
        'workdays_count': workdays_count,
        'deadline': deadline
    })
    save_data(data)
    days_desc = f"{workdays_count} days/week" if 0 < workdays_count < 7 else ("all days" if workdays_count == 7 else "no days")
    flash(f'Set {goal} h goal for {company} (work schedule: {days_desc})', 'success')
    return redirect(url_for('index'))

# ───────────────────────────────
# GET: Delete a log entry
# ───────────────────────────────
@app.route('/delete_log/<company>/<date>')
def delete_log(company, date):
    data = load_data()
    if company in data and date in data[company]['log']:
        data[company]['log'].pop(date)
        if not (data[company]['log'] or data[company]['goal'] or data[company]['tasks']):
            data.pop(company)
        save_data(data)
        flash('Log deleted', 'success')
    else:
        flash('Log entry not found', 'error')
    return redirect(url_for('index'))

# ───────────────────────────────
# POST: Add task
# ───────────────────────────────
@app.route('/add_task', methods=['POST'])
def add_task():
    data = load_data()
    company = request.form['company'].strip()
    title = request.form['task_title'].strip()
    date = request.form['task_date'] or get_today_persian()
    if not company or not title:
        flash('Company and task title are required', 'error')
        return redirect(url_for('index'))
    data.setdefault(company, {'goal': 0, 'log': {}, 'tasks': [], 'workdays_count': 7})
    task_ids = [int(t['id']) for c in data.values() for t in c.get('tasks', [])]
    task_id = str(max(task_ids) + 1 if task_ids else 1)
    data[company]['tasks'].append({'id': task_id, 'title': title, 'date': date, 'completed': False})
    save_data(data)
    flash(f'Added task "{title}" for {company}', 'success')
    return redirect(url_for('index'))

# ───────────────────────────────
# POST: Update task completion
# ───────────────────────────────
@app.route('/update_task/<company>/<task_id>', methods=['POST'])
def update_task(company, task_id):
    data = load_data()
    for task in data.get(company, {}).get('tasks', []):
        if task['id'] == task_id:
            task['completed'] = 'completed' in request.form or 'on' in request.form.values()
            break
    save_data(data)
    flash('Task updated', 'success')
    return redirect(url_for('index'))

# ───────────────────────────────
# GET: Delete task
# ───────────────────────────────
@app.route('/delete_task/<company>/<task_id>')
def delete_task(company, task_id):
    data = load_data()
    tasks = data.get(company, {}).get('tasks', [])
    data[company]['tasks'] = [t for t in tasks if t['id'] != task_id]
    if not (data[company]['log'] or data[company]['goal'] or data[company]['tasks']):
        data.pop(company)
    save_data(data)
    flash('Task deleted', 'success')
    return redirect(url_for('index'))

# ───────────────────────────────
# Time Logging Endpoints
# ───────────────────────────────
@app.route('/start_time_log', methods=['POST'])
def start_time_log():
    data = load_data()
    company = request.form['company']
    start_time = dt.now().isoformat()
    data.setdefault(company, {'goal': 0, 'log': {}, 'tasks': [], 'workdays_count': 7, 'time_logs': []})
    data[company].setdefault('current_session', {})
    data[company]['current_session'] = {
        'start_time': start_time,
        'date': get_today_persian()
    }
    save_data(data)
    return {'status': 'success', 'start_time': start_time}

@app.route('/end_time_log', methods=['POST'])
def end_time_log():
    data = load_data()
    company = request.form['company']
    if 'current_session' not in data.get(company, {}):
        return {'status': 'error', 'message': 'No active session'}, 400
    current_session = data[company]['current_session']
    end_time = dt.now().isoformat()
    start_dt = dt.fromisoformat(current_session['start_time'])
    end_dt = dt.fromisoformat(end_time)
    duration = round((end_dt - start_dt).total_seconds() / 3600, 2)
    time_log = {
        'date': current_session['date'],
        'start_time': start_dt.strftime('%H:%M:%S'),
        'end_time': end_dt.strftime('%H:%M:%S'),
        'duration': duration
    }
    data[company].setdefault('time_logs', []).append(time_log)
    data[company].pop('current_session', None)
    save_data(data)
    return {'status': 'success', 'duration': duration, 'log': time_log}

@app.route('/get_today_time_logs', methods=['GET'])
def get_today_time_logs():
    data = load_data()
    today = get_today_persian()
    result = {}
    for company, info in data.items():
        if 'time_logs' in info:
            today_logs = [log for log in info['time_logs'] if log['date'] == today]
            if today_logs:
                result[company] = today_logs
    return {'status': 'success', 'logs': result}

@app.route('/get_current_session', methods=['GET'])
def get_current_session():
    data = load_data()
    company = request.args.get('company')
    if company in data and 'current_session' in data[company]:
        return {'status': 'success', 'current_session': data[company]['current_session']}
    return {'status': 'error', 'message': 'No active session'}, 404

@app.route('/get_last_time_log', methods=['GET'])
def get_last_time_log():
    data = load_data()
    company = request.args.get('company')
    if company in data and 'time_logs' in data[company] and data[company]['time_logs']:
        # Sort logs by date and start_time to get the most recent
        last_log = max(data[company]['time_logs'], key=lambda x: (x['date'], x['start_time']))
        return {'status': 'success', 'last_log': last_log}
    return {'status': 'error', 'message': 'No time logs found'}, 404

@app.route('/delete_time_log', methods=['POST'])
def delete_time_log():
    data = load_data()
    company = request.form['company']
    date = request.form['date']
    start_time = request.form['start_time']
    if company in data and 'time_logs' in data[company]:
        data[company]['time_logs'] = [
            log for log in data[company]['time_logs']
            if not (log['date'] == date and log['start_time'] == start_time)
        ]
        save_data(data)
        return {'status': 'success'}
    return {'status': 'error', 'message': 'Log not found'}, 404

@app.route('/delete_goal/<company>')
def delete_goal(company):
    data = load_data()
    if company in data:
        # Remove goal-related fields but keep logs and tasks
        data[company].pop('goal', None)
        data[company].pop('workdays_count', None)
        data[company].pop('deadline', None)
        if not (data[company]['log'] or data[company]['tasks']):
            data.pop(company)
        save_data(data)
        flash(f'Goal deleted for {company}', 'success')
    else:
        flash('Company not found', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)