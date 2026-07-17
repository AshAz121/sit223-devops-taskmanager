import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

import click
from flask import (
    Flask,
    Response,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.cli import with_appcontext
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from werkzeug.security import check_password_hash, generate_password_hash


REQUEST_COUNTER = Counter(
    "taskmanager_http_requests_total",
    "Total HTTP requests received by the Task Manager",
    ["method", "endpoint", "status"],
)


def get_db():
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE"])
        database_path.parent.mkdir(parents=True, exist_ok=True)

        g.db = sqlite3.connect(database_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


def close_db(_error=None):
    database = g.pop("db", None)

    if database is not None:
        database.close()


def init_db():
    database = get_db()

    with current_app.open_resource("schema.sql") as schema_file:
        database.executescript(schema_file.read().decode("utf-8"))


@click.command("init-db")
@with_appcontext
def init_db_command():
    init_db()
    click.echo("The Task Manager database has been initialised.")


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if session.get("user_id") is None:
            flash(
                "Please log in before opening the dashboard.",
                "warning",
            )
            return redirect(url_for("login"))

        return view(**kwargs)

    return wrapped_view


def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


def register():
    if request.method == "POST":
        return process_registration()

    return render_template("register.html")


def process_registration():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    error = validate_registration(username, password)

    if error is None:
        error = create_user(username, password)

    if error is not None:
        flash(error, "error")
        return render_template("register.html")

    flash(
        "Account created successfully. You can now log in.",
        "success",
    )
    return redirect(url_for("login"))


def validate_registration(username, password):
    if len(username) < 3:
        return "Username must contain at least three characters."

    if len(username) > 50:
        return "Username must be no longer than 50 characters."

    if len(password) < 8:
        return "Password must contain at least eight characters."

    return None


def create_user(username, password):
    database = get_db()

    try:
        database.execute(
            """
            INSERT INTO users (username, password_hash)
            VALUES (?, ?)
            """,
            (username, generate_password_hash(password)),
        )
        database.commit()
    except sqlite3.IntegrityError:
        return "That username is already registered."

    return None


def login():
    if request.method == "POST":
        return process_login()

    return render_template("login.html")


def process_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    user = get_db().execute(
        "SELECT * FROM users WHERE username = ?",
        (username,),
    ).fetchone()

    if user is None:
        flash("Incorrect username or password.", "error")
        return render_template("login.html")

    if not check_password_hash(user["password_hash"], password):
        flash("Incorrect username or password.", "error")
        return render_template("login.html")

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]

    flash("You have logged in successfully.", "success")
    return redirect(url_for("dashboard"))


def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@login_required
def dashboard():
    tasks = get_db().execute(
        """
        SELECT id, title, description, completed, created_at
        FROM tasks
        WHERE user_id = ?
        ORDER BY completed ASC, created_at DESC
        """,
        (session["user_id"],),
    ).fetchall()

    completed_count = sum(task["completed"] for task in tasks)

    return render_template(
        "dashboard.html",
        tasks=tasks,
        completed_count=completed_count,
    )


@login_required
def add_task():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    error = validate_task(title, description)

    if error is not None:
        flash(error, "error")
        return redirect(url_for("dashboard"))

    database = get_db()
    database.execute(
        """
        INSERT INTO tasks (user_id, title, description)
        VALUES (?, ?, ?)
        """,
        (session["user_id"], title, description),
    )
    database.commit()

    flash("Task added successfully.", "success")
    return redirect(url_for("dashboard"))


@login_required
def edit_task(task_id):
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    error = validate_task(title, description)

    if error is not None:
        flash(error, "error")
        return redirect(url_for("dashboard"))

    database = get_db()
    result = database.execute(
        """
        UPDATE tasks
        SET title = ?, description = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            title,
            description,
            task_id,
            session["user_id"],
        ),
    )
    database.commit()

    if result.rowcount:
        flash("Task updated successfully.", "success")
    else:
        flash("Task could not be found.", "error")

    return redirect(url_for("dashboard"))


def validate_task(title, description):
    if not title:
        return "Task title cannot be empty."

    if len(title) > 120:
        return "Task title must be no longer than 120 characters."

    if len(description) > 500:
        return "Description must be no longer than 500 characters."

    return None


@login_required
def toggle_task(task_id):
    database = get_db()

    result = database.execute(
        """
        UPDATE tasks
        SET completed =
            CASE completed
                WHEN 0 THEN 1
                ELSE 0
            END
        WHERE id = ? AND user_id = ?
        """,
        (task_id, session["user_id"]),
    )
    database.commit()

    if result.rowcount:
        flash("Task status updated.", "success")
    else:
        flash("Task could not be found.", "error")

    return redirect(url_for("dashboard"))


@login_required
def delete_task(task_id):
    database = get_db()

    result = database.execute(
        """
        DELETE FROM tasks
        WHERE id = ? AND user_id = ?
        """,
        (task_id, session["user_id"]),
    )
    database.commit()

    if result.rowcount:
        flash("Task deleted successfully.", "success")
    else:
        flash("Task could not be found.", "error")

    return redirect(url_for("dashboard"))


def health():
    try:
        get_db().execute("SELECT 1").fetchone()
    except sqlite3.Error:
        return jsonify(
            status="unhealthy",
            database="unavailable",
        ), 503

    return jsonify(
        status="healthy",
        application="SIT223 DevOps Task Manager",
        database="available",
        version=current_app.config["APP_VERSION"],
    )


def metrics():
    return Response(
        generate_latest(),
        mimetype=CONTENT_TYPE_LATEST,
    )


def add_security_headers_and_metrics(response):
    response.headers.setdefault(
        "X-Content-Type-Options",
        "nosniff",
    )
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Referrer-Policy",
        "same-origin",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:;",
    )

    endpoint = request.endpoint or "unknown"

    REQUEST_COUNTER.labels(
        method=request.method,
        endpoint=endpoint,
        status=response.status_code,
    ).inc()

    return response


def register_routes(app):
    app.add_url_rule("/", view_func=index)

    app.add_url_rule(
        "/register",
        view_func=register,
        methods=("GET", "POST"),
    )
    app.add_url_rule(
        "/login",
        view_func=login,
        methods=("GET", "POST"),
    )
    app.add_url_rule(
        "/logout",
        view_func=logout,
        methods=("POST",),
    )
    app.add_url_rule(
        "/dashboard",
        view_func=dashboard,
    )
    app.add_url_rule(
        "/tasks",
        view_func=add_task,
        methods=("POST",),
    )
    app.add_url_rule(
        "/tasks/<int:task_id>/edit",
        view_func=edit_task,
        methods=("POST",),
    )
    app.add_url_rule(
        "/tasks/<int:task_id>/toggle",
        view_func=toggle_task,
        methods=("POST",),
    )
    app.add_url_rule(
        "/tasks/<int:task_id>/delete",
        view_func=delete_task,
        methods=("POST",),
    )
    app.add_url_rule("/health", view_func=health)
    app.add_url_rule("/metrics", view_func=metrics)


def configure_app(app, test_config):
    default_database = Path(app.root_path) / "data" / "taskmanager.db"

    app.config.from_mapping(
        SECRET_KEY=os.environ.get(
            "SECRET_KEY",
            secrets.token_hex(32),
        ),
        DATABASE=os.environ.get(
            "DATABASE",
            str(default_database),
        ),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
        APP_VERSION=os.environ.get("APP_VERSION", "dev"),
    )

    if test_config is not None:
        app.config.update(test_config)


def create_app(test_config=None):
    app = Flask(__name__)

    configure_app(app, test_config)
    Path(app.config["DATABASE"]).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    app.teardown_appcontext(close_db)
    app.after_request(add_security_headers_and_metrics)
    app.cli.add_command(init_db_command)

    register_routes(app)

    with app.app_context():
        if not Path(app.config["DATABASE"]).exists():
            init_db()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", "5000")),
        debug=False,
    )
