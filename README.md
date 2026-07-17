# SIT223 DevOps Task Manager

A secure Flask task-management application created to demonstrate a complete Jenkins CI/CD pipeline.

## Application features

- User registration and authentication
- Secure password hashing
- Create, edit, complete and delete tasks
- SQLite database storage
- Health-check endpoint
- Prometheus metrics endpoint
- Security response headers
- Docker production deployment using Gunicorn

## DevOps pipeline stages

1. Build
2. Test
3. Code Quality
4. Security
5. Deploy
6. Release
7. Monitoring and Alerting

## Technology stack

- Python and Flask
- SQLite
- Pytest and pytest-cov
- Flake8
- Bandit
- pip-audit
- Docker
- Gunicorn
- Jenkins
- Prometheus

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m flask --app app init-db
python app.py
```

The application is available at `http://localhost:5000`.

## Testing

```bash
python -m pytest --cov=app --cov-report=term-missing
```

## Docker build

```bash
APP_VERSION=$(cat VERSION)
docker build --build-arg APP_VERSION="$APP_VERSION" -t sit223-taskmanager:"$APP_VERSION" .
```

## Health and monitoring endpoints

- `/health`
- `/metrics`
