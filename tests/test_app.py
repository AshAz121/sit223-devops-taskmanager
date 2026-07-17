import sqlite3
from contextlib import closing

import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test-taskmanager.db"

    test_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "DATABASE": str(database_path),
        }
    )

    yield test_app


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, username="ashkan", password="StrongPass123"):
    return client.post(
        "/register",
        data={
            "username": username,
            "password": password,
        },
        follow_redirects=True,
    )


def login(client, username="ashkan", password="StrongPass123"):
    return client.post(
        "/login",
        data={
            "username": username,
            "password": password,
        },
        follow_redirects=True,
    )


def test_home_redirects_to_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_user_can_register_and_login(client):
    register_response = register(client)

    assert register_response.status_code == 200
    assert b"Account created successfully" in register_response.data

    login_response = login(client)

    assert login_response.status_code == 200
    assert b"Your task workspace" in login_response.data
    assert b"You have logged in successfully" in login_response.data


def test_registration_rejects_short_password(client):
    response = register(client, password="short")

    assert response.status_code == 200
    assert b"Password must contain at least eight characters" in response.data


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_user_can_add_edit_complete_and_delete_task(client, app):
    register(client)
    login(client)

    add_response = client.post(
        "/tasks",
        data={
            "title": "Configure Jenkins",
            "description": "Create the automated build stage.",
        },
        follow_redirects=True,
    )

    assert add_response.status_code == 200
    assert b"Configure Jenkins" in add_response.data
    assert b"Task added successfully" in add_response.data

    with closing(sqlite3.connect(app.config["DATABASE"])) as database:
        task = database.execute(
            "SELECT id, completed FROM tasks"
        ).fetchone()

    task_id = task[0]

    edit_response = client.post(
        f"/tasks/{task_id}/edit",
        data={
            "title": "Configure Jenkins pipeline",
            "description": "Create and verify the build stage.",
        },
        follow_redirects=True,
    )

    assert edit_response.status_code == 200
    assert b"Configure Jenkins pipeline" in edit_response.data
    assert b"Task updated successfully" in edit_response.data

    toggle_response = client.post(
        f"/tasks/{task_id}/toggle",
        follow_redirects=True,
    )

    assert toggle_response.status_code == 200
    assert b"Completed" in toggle_response.data

    delete_response = client.post(
        f"/tasks/{task_id}/delete",
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    assert b"Task deleted successfully" in delete_response.data
    assert b"Configure Jenkins pipeline" not in delete_response.data


def test_empty_task_title_is_rejected(client):
    register(client)
    login(client)

    response = client.post(
        "/tasks",
        data={
            "title": "",
            "description": "Missing title",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Task title cannot be empty" in response.data


def test_health_endpoint_reports_healthy(client):
    response = client.get("/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "healthy"
    assert payload["database"] == "available"


def test_metrics_endpoint_returns_prometheus_data(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"taskmanager_http_requests_total" in response.data


def test_security_headers_are_present(client):
    response = client.get("/login")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert "default-src 'self'" in response.headers[
        "Content-Security-Policy"
    ]


def test_user_can_logout(client):
    register(client)
    login(client)

    response = client.post("/logout", follow_redirects=True)

    assert response.status_code == 200
    assert b"You have been logged out" in response.data
    assert b"Welcome back" in response.data
