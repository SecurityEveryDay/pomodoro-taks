import sqlite3
import json
import os
from datetime import datetime, timedelta, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'pomodoro-secret-key-2024-muito-seguro'
DATABASE = os.path.join(os.path.dirname(__file__), 'pomodoro.db')

# ─────────────────────── DATABASE ───────────────────────

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_admin INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                -- settings
                pomodoro_duration INTEGER DEFAULT 25,
                short_break_duration INTEGER DEFAULT 5,
                long_break_duration INTEGER DEFAULT 15,
                long_break_interval INTEGER DEFAULT 4,
                daily_goal INTEGER DEFAULT 8,
                weekly_goal INTEGER DEFAULT 40,
                dark_mode INTEGER DEFAULT 0,
                sound_enabled INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                color TEXT DEFAULT '#e74c3c',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER,
                title TEXT NOT NULL,
                notes TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                priority TEXT DEFAULT 'media',
                estimated_pomodoros INTEGER DEFAULT 1,
                completed_pomodoros INTEGER DEFAULT 0,
                is_completed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS pomodoro_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id INTEGER,
                session_type TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                is_completed INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            );
        ''')
        db.commit()

        # ── Migrations for existing databases ──
        existing_cols = [row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()]
        if 'is_admin' not in existing_cols:
            db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            db.commit()
        if 'is_active' not in existing_cols:
            db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
            db.commit()

# ─────────────────────── AUTH HELPERS ───────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = current_user()
        if not user or not user['is_admin']:
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def current_user():
    if 'user_id' not in session:
        return None
    db = get_db()
    return db.execute('SELECT * FROM users WHERE id = ?', [session['user_id']]).fetchone()

# ─────────────────────── AUTH ROUTES ───────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', [email]).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                return render_template('login.html', error='Conta desativada. Contate o administrador.')
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='E-mail ou senha inválidos.')
    return render_template('login.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not username or not email or not password:
            return render_template('register.html', error='Todos os campos são obrigatórios.')
        if password != confirm:
            return render_template('register.html', error='As senhas não coincidem.')
        if len(password) < 6:
            return render_template('register.html', error='A senha deve ter pelo menos 6 caracteres.')
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, email, password_hash) VALUES (?,?,?)',
                       [username, email, generate_password_hash(password)])
            db.commit()
            user = db.execute('SELECT * FROM users WHERE email = ?', [email]).fetchone()
            # Create default project
            db.execute('INSERT INTO projects (user_id, name, color) VALUES (?,?,?)',
                       [user['id'], 'Geral', '#e74c3c'])
            db.commit()
            session['user_id'] = user['id']
            session['username'] = username
            return redirect(url_for('dashboard'))
        except sqlite3.IntegrityError:
            return render_template('register.html', error='E-mail ou usuário já cadastrado.')
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─────────────────────── DASHBOARD ───────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    db = get_db()
    today = date.today().isoformat()

    sessions_today = db.execute('''
        SELECT COUNT(*) as cnt, SUM(duration_minutes) as total_min
        FROM pomodoro_sessions
        WHERE user_id=? AND session_type='pomodoro' AND is_completed=1
          AND DATE(completed_at)=?
    ''', [user['id'], today]).fetchone()

    tasks_pending = db.execute('''
        SELECT t.*, p.name as project_name, p.color as project_color
        FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
        WHERE t.user_id=? AND t.is_completed=0
        ORDER BY CASE t.priority WHEN 'alta' THEN 1 WHEN 'media' THEN 2 WHEN 'baixa' THEN 3 ELSE 4 END,
                 t.created_at DESC LIMIT 5
    ''', [user['id']]).fetchall()

    tasks_completed_today = db.execute('''
        SELECT COUNT(*) as cnt FROM tasks
        WHERE user_id=? AND is_completed=1 AND DATE(completed_at)=?
    ''', [user['id'], today]).fetchone()

    # Weekly progress
    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).date().isoformat()
    sessions_week = db.execute('''
        SELECT COUNT(*) as cnt, SUM(duration_minutes) as total_min
        FROM pomodoro_sessions
        WHERE user_id=? AND session_type='pomodoro' AND is_completed=1
          AND DATE(completed_at)>=?
    ''', [user['id'], week_start]).fetchone()

    # Recent sessions
    recent_sessions = db.execute('''
        SELECT ps.*, t.title as task_title
        FROM pomodoro_sessions ps LEFT JOIN tasks t ON ps.task_id = t.id
        WHERE ps.user_id=? AND ps.session_type='pomodoro' AND ps.is_completed=1
        ORDER BY ps.completed_at DESC LIMIT 5
    ''', [user['id']]).fetchall()

    return render_template('dashboard.html',
        user=user,
        sessions_today=sessions_today,
        tasks_pending=tasks_pending,
        tasks_completed_today=tasks_completed_today,
        sessions_week=sessions_week,
        recent_sessions=recent_sessions,
        today=today
    )

# ─────────────────────── TIMER ───────────────────────

@app.route('/timer')
@login_required
def timer():
    user = current_user()
    db = get_db()
    tasks = db.execute('''
        SELECT t.*, p.name as project_name, p.color as project_color
        FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
        WHERE t.user_id=? AND t.is_completed=0
        ORDER BY CASE t.priority WHEN 'alta' THEN 1 WHEN 'media' THEN 2 WHEN 'baixa' THEN 3 ELSE 4 END,
                 t.created_at DESC
    ''', [user['id']]).fetchall()
    projects = db.execute('SELECT * FROM projects WHERE user_id=? ORDER BY name', [user['id']]).fetchall()
    return render_template('timer.html', user=user, tasks=tasks, projects=projects)

@app.route('/api/session/start', methods=['POST'])
@login_required
def api_start_session():
    data = request.get_json()
    session_type = data.get('session_type', 'pomodoro')
    task_id = data.get('task_id')
    duration = data.get('duration_minutes', 25)
    db = get_db()
    cur = db.execute('''
        INSERT INTO pomodoro_sessions (user_id, task_id, session_type, duration_minutes, started_at)
        VALUES (?,?,?,?,?)
    ''', [session['user_id'], task_id if task_id else None, session_type, duration, datetime.now().isoformat()])
    db.commit()
    return jsonify({'session_id': cur.lastrowid})

@app.route('/api/session/complete', methods=['POST'])
@login_required
def api_complete_session():
    data = request.get_json()
    session_id = data.get('session_id')
    actual_minutes = data.get('actual_minutes')  # optional: real time spent (early finish)
    db = get_db()
    sess = db.execute('SELECT * FROM pomodoro_sessions WHERE id=? AND user_id=?',
                      [session_id, session['user_id']]).fetchone()
    if not sess:
        return jsonify({'error': 'Sessão não encontrada'}), 404

    update_fields = 'is_completed=1, completed_at=?'
    update_params = [datetime.now().isoformat()]
    if actual_minutes is not None:
        update_fields += ', duration_minutes=?'
        update_params.append(int(actual_minutes))
    update_params.append(session_id)

    db.execute(f'UPDATE pomodoro_sessions SET {update_fields} WHERE id=?', update_params)
    if sess['task_id'] and sess['session_type'] == 'pomodoro':
        db.execute('''
            UPDATE tasks SET completed_pomodoros = completed_pomodoros + 1
            WHERE id=? AND user_id=?
        ''', [sess['task_id'], session['user_id']])
    db.commit()
    return jsonify({'success': True})

@app.route('/api/session/cancel', methods=['POST'])
@login_required
def api_cancel_session():
    data = request.get_json()
    session_id = data.get('session_id')
    db = get_db()
    db.execute('DELETE FROM pomodoro_sessions WHERE id=? AND user_id=?',
               [session_id, session['user_id']])
    db.commit()
    return jsonify({'success': True})

# ─────────────────────── TASKS ───────────────────────

@app.route('/tarefas')
@login_required
def tasks():
    user = current_user()
    db = get_db()
    filter_project = request.args.get('projeto', '')
    filter_tag = request.args.get('tag', '')
    filter_priority = request.args.get('prioridade', '')
    filter_status = request.args.get('status', 'pendentes')
    filter_search = request.args.get('busca', '').strip()

    query = '''
        SELECT t.*, p.name as project_name, p.color as project_color
        FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
        WHERE t.user_id=?
    '''
    params = [user['id']]

    if filter_status == 'pendentes':
        query += ' AND t.is_completed=0'
    elif filter_status == 'concluidas':
        query += ' AND t.is_completed=1'

    if filter_project:
        query += ' AND t.project_id=?'
        params.append(filter_project)
    if filter_priority:
        query += ' AND t.priority=?'
        params.append(filter_priority)
    if filter_search:
        query += ' AND (t.title LIKE ? OR t.notes LIKE ? OR t.tags LIKE ?)'
        like = f'%{filter_search}%'
        params.extend([like, like, like])

    query += ''' ORDER BY CASE t.priority WHEN 'alta' THEN 1 WHEN 'media' THEN 2 WHEN 'baixa' THEN 3 ELSE 4 END,
                t.created_at DESC'''

    task_list = db.execute(query, params).fetchall()

    if filter_tag:
        task_list = [t for t in task_list if filter_tag in (t['tags'] or '').split(',')]

    projects = db.execute('SELECT * FROM projects WHERE user_id=? ORDER BY name', [user['id']]).fetchall()

    all_tags = set()
    all_tasks = db.execute('SELECT tags FROM tasks WHERE user_id=?', [user['id']]).fetchall()
    for t in all_tasks:
        if t['tags']:
            for tag in t['tags'].split(','):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)

    return render_template('tasks.html',
        user=user, tasks=task_list, projects=projects,
        all_tags=sorted(all_tags),
        filter_project=filter_project, filter_tag=filter_tag,
        filter_priority=filter_priority, filter_status=filter_status,
        filter_search=filter_search
    )

@app.route('/tarefas/nova', methods=['POST'])
@login_required
def create_task():
    data = request.form
    db = get_db()
    tags = ','.join([t.strip() for t in data.get('tags', '').split(',') if t.strip()])
    db.execute('''
        INSERT INTO tasks (user_id, project_id, title, notes, tags, priority, estimated_pomodoros)
        VALUES (?,?,?,?,?,?,?)
    ''', [
        session['user_id'],
        data.get('project_id') or None,
        data.get('title', '').strip(),
        data.get('notes', '').strip(),
        tags,
        data.get('priority', 'media'),
        int(data.get('estimated_pomodoros', 1))
    ])
    db.commit()
    return redirect(url_for('tasks'))

@app.route('/tarefas/<int:task_id>/editar', methods=['POST'])
@login_required
def edit_task(task_id):
    data = request.form
    db = get_db()
    tags = ','.join([t.strip() for t in data.get('tags', '').split(',') if t.strip()])
    db.execute('''
        UPDATE tasks SET title=?, notes=?, tags=?, priority=?, estimated_pomodoros=?, project_id=?
        WHERE id=? AND user_id=?
    ''', [
        data.get('title', '').strip(),
        data.get('notes', '').strip(),
        tags,
        data.get('priority', 'media'),
        int(data.get('estimated_pomodoros', 1)),
        data.get('project_id') or None,
        task_id, session['user_id']
    ])
    db.commit()
    return redirect(request.referrer or url_for('tasks'))

@app.route('/tarefas/<int:task_id>/concluir', methods=['POST'])
@login_required
def complete_task(task_id):
    db = get_db()
    db.execute('''
        UPDATE tasks SET is_completed=1, completed_at=? WHERE id=? AND user_id=?
    ''', [datetime.now().isoformat(), task_id, session['user_id']])
    db.commit()
    return redirect(request.referrer or url_for('tasks'))

@app.route('/tarefas/<int:task_id>/reabrir', methods=['POST'])
@login_required
def reopen_task(task_id):
    db = get_db()
    db.execute('''
        UPDATE tasks SET is_completed=0, completed_at=NULL WHERE id=? AND user_id=?
    ''', [task_id, session['user_id']])
    db.commit()
    return redirect(request.referrer or url_for('tasks'))

@app.route('/tarefas/<int:task_id>/excluir', methods=['POST'])
@login_required
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id=? AND user_id=?', [task_id, session['user_id']])
    db.commit()
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tarefas/<int:task_id>/registrar-tempo', methods=['POST'])
@login_required
def register_time(task_id):
    """Manually register pomodoros or free minutes to a task (retroactive)."""
    db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id=? AND user_id=?',
                      [task_id, session['user_id']]).fetchone()
    if not task:
        return redirect(url_for('tasks'))

    mode      = request.form.get('mode', 'pomodoros')   # 'pomodoros' or 'minutes'
    quantity  = int(request.form.get('quantity', 1))
    date_str  = request.form.get('date', datetime.now().date().isoformat())
    time_str  = request.form.get('time', datetime.now().strftime('%H:%M'))
    notes     = request.form.get('notes', '').strip()

    try:
        when = datetime.fromisoformat(f"{date_str}T{time_str}:00")
    except ValueError:
        when = datetime.now()

    pom_duration = db.execute('SELECT pomodoro_duration FROM users WHERE id=?',
                              [session['user_id']]).fetchone()['pomodoro_duration']

    if mode == 'pomodoros':
        # Insert one session per pomodoro
        for i in range(max(1, quantity)):
            started = when - timedelta(minutes=pom_duration * (quantity - i))
            db.execute("""
                INSERT INTO pomodoro_sessions
                  (user_id, task_id, session_type, duration_minutes, started_at, completed_at, is_completed, notes)
                VALUES (?,?,?,?,?,?,1,?)
            """, [session['user_id'], task_id, 'pomodoro', pom_duration,
                  started.isoformat(), when.isoformat(), notes or 'Registrado manualmente'])
        db.execute('UPDATE tasks SET completed_pomodoros = completed_pomodoros + ? WHERE id=? AND user_id=?',
                   [quantity, task_id, session['user_id']])
    else:
        # Free minutes — insert a single session
        minutes = max(1, quantity)
        started = when - timedelta(minutes=minutes)
        db.execute("""
            INSERT INTO pomodoro_sessions
              (user_id, task_id, session_type, duration_minutes, started_at, completed_at, is_completed, notes)
        VALUES (?,?,?,?,?,?,1,?)
        """, [session['user_id'], task_id, 'pomodoro', minutes,
              started.isoformat(), when.isoformat(), notes or 'Registrado manualmente'])
        # Credit equivalent full pomodoros
        full_poms = minutes // pom_duration
        if full_poms > 0:
            db.execute('UPDATE tasks SET completed_pomodoros = completed_pomodoros + ? WHERE id=? AND user_id=?',
                       [full_poms, task_id, session['user_id']])

    db.commit()
    return redirect(request.referrer or url_for('tasks'))

@app.route('/api/tarefas/<int:task_id>', methods=['GET'])
@login_required
def api_get_task(task_id):
    db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id=? AND user_id=?',
                      [task_id, session['user_id']]).fetchone()
    if not task:
        return jsonify({'error': 'Não encontrada'}), 404
    return jsonify(dict(task))

# ─────────────────────── PROJECTS ───────────────────────

@app.route('/projetos')
@login_required
def projects():
    user = current_user()
    db = get_db()
    proj_list = db.execute('''
        SELECT p.*, 
               COUNT(DISTINCT t.id) as total_tasks,
               SUM(CASE WHEN t.is_completed=1 THEN 1 ELSE 0 END) as completed_tasks,
               SUM(t.completed_pomodoros) as total_pomodoros
        FROM projects p LEFT JOIN tasks t ON p.id = t.project_id
        WHERE p.user_id=?
        GROUP BY p.id ORDER BY p.name
    ''', [user['id']]).fetchall()
    return render_template('projects.html', user=user, projects=proj_list)

@app.route('/projetos/novo', methods=['POST'])
@login_required
def create_project():
    data = request.form
    db = get_db()
    db.execute('INSERT INTO projects (user_id, name, color) VALUES (?,?,?)',
               [session['user_id'], data.get('name', '').strip(), data.get('color', '#e74c3c')])
    db.commit()
    return redirect(url_for('projects'))

@app.route('/projetos/<int:project_id>/editar', methods=['POST'])
@login_required
def edit_project(project_id):
    data = request.form
    db = get_db()
    db.execute('UPDATE projects SET name=?, color=? WHERE id=? AND user_id=?',
               [data.get('name', '').strip(), data.get('color', '#e74c3c'), project_id, session['user_id']])
    db.commit()
    return redirect(url_for('projects'))

@app.route('/projetos/<int:project_id>/excluir', methods=['POST'])
@login_required
def delete_project(project_id):
    db = get_db()
    db.execute('DELETE FROM projects WHERE id=? AND user_id=?', [project_id, session['user_id']])
    db.commit()
    return redirect(url_for('projects'))

# ─────────────────────── REPORTS ───────────────────────

@app.route('/relatorios')
@login_required
def reports():
    user = current_user()
    db = get_db()

    period = request.args.get('periodo', 'hoje')
    filter_project = request.args.get('projeto', '')
    filter_tag = request.args.get('tag', '')
    filter_priority = request.args.get('prioridade', '')

    today = date.today()
    if period == 'hoje':
        start_date = today
        end_date = today
    elif period == 'semana':
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif period == 'mes':
        start_date = today.replace(day=1)
        end_date = today
    elif period == 'ano':
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif period == 'personalizado':
        try:
            start_date = date.fromisoformat(request.args.get('inicio', today.isoformat()))
            end_date = date.fromisoformat(request.args.get('fim', today.isoformat()))
        except:
            start_date = today
            end_date = today
    else:
        start_date = today
        end_date = today

    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    # Total pomodoros and minutes
    stats = db.execute('''
        SELECT COUNT(*) as total_pomodoros, COALESCE(SUM(duration_minutes),0) as total_minutes
        FROM pomodoro_sessions
        WHERE user_id=? AND session_type='pomodoro' AND is_completed=1
          AND DATE(completed_at) BETWEEN ? AND ?
    ''', [user['id'], start_str, end_str]).fetchone()

    # Sessions per day for chart
    daily_data = db.execute('''
        SELECT DATE(completed_at) as day, COUNT(*) as pomodoros, SUM(duration_minutes) as minutes
        FROM pomodoro_sessions
        WHERE user_id=? AND session_type='pomodoro' AND is_completed=1
          AND DATE(completed_at) BETWEEN ? AND ?
        GROUP BY DATE(completed_at) ORDER BY day
    ''', [user['id'], start_str, end_str]).fetchall()

    # Tasks worked on
    tasks_query = '''
        SELECT DISTINCT t.*, p.name as project_name, p.color as project_color,
               COUNT(ps.id) as session_count,
               COALESCE(SUM(ps.duration_minutes),0) as focused_minutes
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN pomodoro_sessions ps ON ps.task_id = t.id AND ps.is_completed=1
            AND ps.session_type='pomodoro' AND DATE(ps.completed_at) BETWEEN ? AND ?
        WHERE t.user_id=? AND ps.id IS NOT NULL
    '''
    params = [start_str, end_str, user['id']]
    if filter_project:
        tasks_query += ' AND t.project_id=?'
        params.append(filter_project)
    if filter_priority:
        tasks_query += ' AND t.priority=?'
        params.append(filter_priority)
    tasks_query += ' GROUP BY t.id ORDER BY focused_minutes DESC'
    worked_tasks = db.execute(tasks_query, params).fetchall()

    if filter_tag:
        worked_tasks = [t for t in worked_tasks if filter_tag in (t['tags'] or '').split(',')]

    # By project
    by_project = db.execute('''
        SELECT p.name, p.color, COUNT(ps.id) as pomodoros, COALESCE(SUM(ps.duration_minutes),0) as minutes
        FROM pomodoro_sessions ps
        JOIN tasks t ON ps.task_id = t.id
        JOIN projects p ON t.project_id = p.id
        WHERE ps.user_id=? AND ps.session_type='pomodoro' AND ps.is_completed=1
          AND DATE(ps.completed_at) BETWEEN ? AND ?
        GROUP BY p.id ORDER BY minutes DESC
    ''', [user['id'], start_str, end_str]).fetchall()

    # By tag (manual aggregation)
    tag_sessions = db.execute('''
        SELECT t.tags, ps.duration_minutes
        FROM pomodoro_sessions ps
        JOIN tasks t ON ps.task_id = t.id
        WHERE ps.user_id=? AND ps.session_type='pomodoro' AND ps.is_completed=1
          AND DATE(ps.completed_at) BETWEEN ? AND ?
    ''', [user['id'], start_str, end_str]).fetchall()
    tag_map = {}
    for row in tag_sessions:
        if row['tags']:
            for tag in row['tags'].split(','):
                tag = tag.strip()
                if tag:
                    tag_map[tag] = tag_map.get(tag, 0) + (row['duration_minutes'] or 0)
    by_tag = sorted([{'tag': k, 'minutes': v} for k, v in tag_map.items()], key=lambda x: -x['minutes'])

    projects = db.execute('SELECT * FROM projects WHERE user_id=? ORDER BY name', [user['id']]).fetchall()
    all_tags_raw = db.execute('SELECT tags FROM tasks WHERE user_id=?', [user['id']]).fetchall()
    all_tags = sorted(set(t.strip() for row in all_tags_raw if row['tags'] for t in row['tags'].split(',') if t.strip()))

    return render_template('reports.html',
        user=user, stats=stats, daily_data=daily_data,
        worked_tasks=worked_tasks, by_project=by_project, by_tag=by_tag,
        projects=projects, all_tags=all_tags,
        period=period, start_date=start_str, end_date=end_str,
        filter_project=filter_project, filter_tag=filter_tag, filter_priority=filter_priority
    )

# ─────────────────────── SETTINGS ───────────────────────

@app.route('/configuracoes', methods=['GET', 'POST'])
@login_required
def settings():
    user = current_user()
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'timer':
            db.execute('''
                UPDATE users SET pomodoro_duration=?, short_break_duration=?,
                long_break_duration=?, long_break_interval=?, daily_goal=?, weekly_goal=?
                WHERE id=?
            ''', [
                int(request.form.get('pomodoro_duration', 25)),
                int(request.form.get('short_break_duration', 5)),
                int(request.form.get('long_break_duration', 15)),
                int(request.form.get('long_break_interval', 4)),
                int(request.form.get('daily_goal', 8)),
                int(request.form.get('weekly_goal', 40)),
                session['user_id']
            ])
            db.commit()
        elif action == 'theme':
            dark = 1 if request.form.get('dark_mode') else 0
            sound = 1 if request.form.get('sound_enabled') else 0
            db.execute('UPDATE users SET dark_mode=?, sound_enabled=? WHERE id=?',
                       [dark, sound, session['user_id']])
            db.commit()
        elif action == 'password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            if check_password_hash(user['password_hash'], current_pw) and len(new_pw) >= 6:
                db.execute('UPDATE users SET password_hash=? WHERE id=?',
                           [generate_password_hash(new_pw), session['user_id']])
                db.commit()
        user = current_user()
        return render_template('settings.html', user=user, success=True)
    return render_template('settings.html', user=user)

# ─────────────────────── ADMIN ───────────────────────

@app.route('/admin')
@admin_required
def admin_panel():
    user = current_user()
    db = get_db()
    users = db.execute('''
        SELECT u.*,
               COUNT(DISTINCT t.id) as total_tasks,
               COUNT(DISTINCT ps.id) as total_sessions
        FROM users u
        LEFT JOIN tasks t ON t.user_id = u.id
        LEFT JOIN pomodoro_sessions ps ON ps.user_id = u.id AND ps.is_completed = 1
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''').fetchall()
    return render_template('admin.html', user=user, users=users)

@app.route('/admin/usuario/<int:target_id>/toggle-admin', methods=['POST'])
@admin_required
def admin_toggle_admin(target_id):
    db = get_db()
    target = db.execute('SELECT * FROM users WHERE id=?', [target_id]).fetchone()
    if not target or target_id == session['user_id']:
        return redirect(url_for('admin_panel'))
    db.execute('UPDATE users SET is_admin=? WHERE id=?', [0 if target['is_admin'] else 1, target_id])
    db.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/usuario/<int:target_id>/toggle-active', methods=['POST'])
@admin_required
def admin_toggle_active(target_id):
    db = get_db()
    target = db.execute('SELECT * FROM users WHERE id=?', [target_id]).fetchone()
    if not target or target_id == session['user_id']:
        return redirect(url_for('admin_panel'))
    db.execute('UPDATE users SET is_active=? WHERE id=?', [0 if target['is_active'] else 1, target_id])
    db.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/usuario/<int:target_id>/reset-senha', methods=['POST'])
@admin_required
def admin_reset_password(target_id):
    new_pw = request.form.get('new_password', '').strip()
    if len(new_pw) < 6:
        return redirect(url_for('admin_panel'))
    db = get_db()
    db.execute('UPDATE users SET password_hash=? WHERE id=?',
               [generate_password_hash(new_pw), target_id])
    db.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/usuario/<int:target_id>/excluir', methods=['POST'])
@admin_required
def admin_delete_user(target_id):
    if target_id == session['user_id']:
        return redirect(url_for('admin_panel'))
    db = get_db()
    db.execute('DELETE FROM users WHERE id=?', [target_id])
    db.commit()
    return redirect(url_for('admin_panel'))

# ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
