pipeline {
    agent any

    options {
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 30, unit: 'MINUTES')
    }

    environment {
        IMAGE_NAME = 'sit223-taskmanager'
        STAGING_CONTAINER = 'sit223-taskmanager-staging'
        PRODUCTION_CONTAINER = 'sit223-taskmanager-production'
        DOCKER_NETWORK = 'sit223-monitoring'
        PROMETHEUS_CONTAINER = 'sit223-prometheus'
        ALERTMANAGER_CONTAINER = 'sit223-alertmanager'
        ALERT_RECEIVER_CONTAINER = 'sit223-alert-receiver'
    }

    stages {
        stage('Build') {
            steps {
                sh '''
                    set -eu

                    echo "========== BUILD STAGE =========="

                    rm -rf .jenkins-venv reports artifacts htmlcov .coverage
                    mkdir -p reports artifacts

                    python3 -m venv .jenkins-venv
                    . .jenkins-venv/bin/activate

                    python -m pip install --upgrade pip
                    python -m pip install -r requirements-dev.txt

                    APP_VERSION=$(cat VERSION)
                    BUILD_IMAGE="${IMAGE_NAME}:ci-${BUILD_NUMBER}"

                    echo "Application version: ${APP_VERSION}"
                    echo "Docker build image: ${BUILD_IMAGE}"

                    docker build \
                        --build-arg APP_VERSION="${APP_VERSION}-build.${BUILD_NUMBER}" \
                        -t "${BUILD_IMAGE}" \
                        .

                    docker image inspect "${BUILD_IMAGE}" \
                        > artifacts/build-image-inspect.json

                    {
                        echo "Application version: ${APP_VERSION}"
                        echo "Build number: ${BUILD_NUMBER}"
                        echo "Image: ${BUILD_IMAGE}"
                        echo "Git commit: ${GIT_COMMIT:-unknown}"
                    } > artifacts/build-metadata.txt

                    echo "BUILD RESULT: PASSED"
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    set -eu

                    echo "========== TEST STAGE =========="

                    . .jenkins-venv/bin/activate
                    mkdir -p reports

                    python -m pytest -v \
                        --junitxml=reports/junit.xml \
                        --cov=app \
                        --cov-report=term-missing \
                        --cov-report=html \
                        --cov-report=xml:reports/coverage.xml \
                        --cov-fail-under=85

                    echo "TEST RESULT: PASSED"
                    echo "Coverage quality gate: minimum 85%"
                '''
            }
        }

        stage('Code Quality') {
            steps {
                sh '''
                    set -eu

                    echo "========== CODE QUALITY STAGE =========="

                    . .jenkins-venv/bin/activate

                    python -m flake8 \
                        app.py \
                        tests \
                        monitoring/alert-receiver/app.py \
                        > reports/flake8.txt

                    {
                        echo "FLAKE8 RESULT: PASSED"
                        echo "No configured style, syntax or complexity issues detected."
                    } | tee -a reports/flake8.txt
                '''
            }
        }

        stage('Security') {
            steps {
                sh '''
                    set -eu

                    echo "========== SECURITY STAGE =========="

                    . .jenkins-venv/bin/activate
                    mkdir -p reports

                    python -m bandit \
                        app.py \
                        monitoring/alert-receiver/app.py \
                        -f json \
                        -o reports/bandit.json

                    echo "Bandit source-code scan: PASSED"

                    python -m pip_audit \
                        -r requirements.txt \
                        -f json \
                        -o reports/main-pip-audit.json

                    echo "Main application dependency audit: PASSED"

                    python -m pip_audit \
                        -r monitoring/alert-receiver/requirements.txt \
                        -f json \
                        -o reports/receiver-pip-audit.json

                    echo "Alert receiver dependency audit: PASSED"
                    echo "SECURITY RESULT: PASSED"
                '''
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    set -eu

                    echo "========== DEPLOY STAGE =========="

                    wait_healthy() {
                        container_name="$1"
                        attempt=1
                        health_state="starting"

                        while [ "$attempt" -le 18 ]; do
                            health_state=$(docker inspect \
                                --format='{{.State.Health.Status}}' \
                                "$container_name" 2>/dev/null || echo "missing")

                            echo "${container_name} health check ${attempt}: ${health_state}"

                            if [ "$health_state" = "healthy" ]; then
                                return 0
                            fi

                            if [ "$health_state" = "unhealthy" ] \
                                || [ "$health_state" = "missing" ]; then
                                return 1
                            fi

                            attempt=$((attempt + 1))
                            sleep 5
                        done

                        return 1
                    }

                    docker network inspect "$DOCKER_NETWORK" \
                        >/dev/null 2>&1 \
                        || docker network create "$DOCKER_NETWORK"

                    docker rm -f \
                        "$STAGING_CONTAINER" \
                        sit223-taskmanager-test \
                        >/dev/null 2>&1 || true

                    APP_VERSION=$(cat VERSION)
                    STAGING_SECRET=$(python3 -c \
                        'import secrets; print(secrets.token_hex(32))')

                    docker run -d \
                        --name "$STAGING_CONTAINER" \
                        --network "$DOCKER_NETWORK" \
                        -p 5001:5000 \
                        -e SECRET_KEY="$STAGING_SECRET" \
                        -e APP_VERSION="${APP_VERSION}-staging.${BUILD_NUMBER}" \
                        -v sit223-staging-data:/app/data \
                        "${IMAGE_NAME}:ci-${BUILD_NUMBER}"

                    if ! wait_healthy "$STAGING_CONTAINER"; then
                        echo "Staging deployment failed its health check."
                        docker logs "$STAGING_CONTAINER" || true
                        exit 1
                    fi

                    curl -fsS http://127.0.0.1:5001/health \
                        | tee artifacts/staging-health.json

                    echo
                    echo "DEPLOY RESULT: PASSED"
                    echo "Staging URL: http://localhost:5001"
                '''
            }
        }

        stage('Release') {
            steps {
                sh '''
                    set -eu

                    echo "========== RELEASE STAGE =========="

                    wait_healthy() {
                        container_name="$1"
                        attempt=1
                        health_state="starting"

                        while [ "$attempt" -le 18 ]; do
                            health_state=$(docker inspect \
                                --format='{{.State.Health.Status}}' \
                                "$container_name" 2>/dev/null || echo "missing")

                            echo "${container_name} health check ${attempt}: ${health_state}"

                            if [ "$health_state" = "healthy" ]; then
                                return 0
                            fi

                            if [ "$health_state" = "unhealthy" ] \
                                || [ "$health_state" = "missing" ]; then
                                return 1
                            fi

                            attempt=$((attempt + 1))
                            sleep 5
                        done

                        return 1
                    }

                    APP_VERSION=$(cat VERSION)
                    RELEASE_TAG="${APP_VERSION}-build.${BUILD_NUMBER}"
                    SOURCE_IMAGE="${IMAGE_NAME}:ci-${BUILD_NUMBER}"
                    RELEASE_IMAGE="${IMAGE_NAME}:${RELEASE_TAG}"

                    docker tag "$SOURCE_IMAGE" "$RELEASE_IMAGE"
                    docker tag "$SOURCE_IMAGE" "${IMAGE_NAME}:${APP_VERSION}"
                    docker tag "$SOURCE_IMAGE" "${IMAGE_NAME}:latest"

                    {
                        echo "Release tag: ${RELEASE_TAG}"
                        echo "Release image: ${RELEASE_IMAGE}"
                        echo "Environment: production"
                        echo "Build number: ${BUILD_NUMBER}"
                        echo "Git commit: ${GIT_COMMIT:-unknown}"
                    } > artifacts/release-metadata.txt

                    PREVIOUS_IMAGE=$(docker inspect \
                        --format='{{.Config.Image}}' \
                        "$PRODUCTION_CONTAINER" 2>/dev/null || true)

                    echo "${PREVIOUS_IMAGE:-none}" \
                        > artifacts/previous-production-image.txt

                    CANDIDATE="${PRODUCTION_CONTAINER}-candidate-${BUILD_NUMBER}"
                    CANDIDATE_VOLUME="sit223-candidate-data-${BUILD_NUMBER}"
                    CANDIDATE_SECRET=$(python3 -c \
                        'import secrets; print(secrets.token_hex(32))')

                    docker rm -f "$CANDIDATE" >/dev/null 2>&1 || true
                    docker volume rm "$CANDIDATE_VOLUME" \
                        >/dev/null 2>&1 || true

                    docker run -d \
                        --name "$CANDIDATE" \
                        --network "$DOCKER_NETWORK" \
                        -e SECRET_KEY="$CANDIDATE_SECRET" \
                        -e APP_VERSION="$RELEASE_TAG" \
                        -v "${CANDIDATE_VOLUME}:/app/data" \
                        "$RELEASE_IMAGE"

                    if ! wait_healthy "$CANDIDATE"; then
                        echo "Release candidate failed."
                        docker logs "$CANDIDATE" || true
                        docker rm -f "$CANDIDATE" || true
                        docker volume rm "$CANDIDATE_VOLUME" || true
                        exit 1
                    fi

                    echo "Release candidate validation: PASSED"

                    docker rm -f "$CANDIDATE"
                    docker volume rm "$CANDIDATE_VOLUME"

                    docker rm -f "$PRODUCTION_CONTAINER" \
                        >/dev/null 2>&1 || true

                    PRODUCTION_SECRET=$(python3 -c \
                        'import secrets; print(secrets.token_hex(32))')

                    docker run -d \
                        --name "$PRODUCTION_CONTAINER" \
                        --network "$DOCKER_NETWORK" \
                        -p 5002:5000 \
                        -e SECRET_KEY="$PRODUCTION_SECRET" \
                        -e APP_VERSION="$RELEASE_TAG" \
                        -v sit223-production-data:/app/data \
                        "$RELEASE_IMAGE"

                    if ! wait_healthy "$PRODUCTION_CONTAINER"; then
                        echo "New production release failed."
                        docker logs "$PRODUCTION_CONTAINER" || true
                        docker rm -f "$PRODUCTION_CONTAINER" || true

                        if [ -n "$PREVIOUS_IMAGE" ]; then
                            echo "Attempting rollback to ${PREVIOUS_IMAGE}"

                            ROLLBACK_SECRET=$(python3 -c \
                                'import secrets; print(secrets.token_hex(32))')

                            docker run -d \
                                --name "$PRODUCTION_CONTAINER" \
                                --network "$DOCKER_NETWORK" \
                                -p 5002:5000 \
                                -e SECRET_KEY="$ROLLBACK_SECRET" \
                                -e APP_VERSION="rollback" \
                                -v sit223-production-data:/app/data \
                                "$PREVIOUS_IMAGE"

                            wait_healthy "$PRODUCTION_CONTAINER" || true
                        else
                            echo "No previous production image was available."
                        fi

                        exit 1
                    fi

                    curl -fsS http://127.0.0.1:5002/health \
                        | tee artifacts/production-health.json

                    docker image inspect "$RELEASE_IMAGE" \
                        > artifacts/release-image-inspect.json

                    echo
                    echo "RELEASE RESULT: PASSED"
                    echo "Production image: ${RELEASE_IMAGE}"
                    echo "Production URL: http://localhost:5002"
                    echo "Rollback image: ${PREVIOUS_IMAGE:-none}"
                '''
            }
        }

        stage('Monitoring and Alerting') {
            steps {
                sh '''
                    set -eu

                    echo "========== MONITORING AND ALERTING STAGE =========="

                    wait_http() {
                        url="$1"
                        service_name="$2"
                        attempt=1

                        while [ "$attempt" -le 18 ]; do
                            if curl -fsS "$url" >/dev/null 2>&1; then
                                echo "${service_name}: ready"
                                return 0
                            fi

                            echo "${service_name} readiness check ${attempt}: waiting"
                            attempt=$((attempt + 1))
                            sleep 5
                        done

                        return 1
                    }

                    wait_healthy() {
                        container_name="$1"
                        attempt=1

                        while [ "$attempt" -le 18 ]; do
                            health_state=$(docker inspect \
                                --format='{{.State.Health.Status}}' \
                                "$container_name" 2>/dev/null || echo "missing")

                            echo "${container_name} health check ${attempt}: ${health_state}"

                            if [ "$health_state" = "healthy" ]; then
                                return 0
                            fi

                            if [ "$health_state" = "unhealthy" ] \
                                || [ "$health_state" = "missing" ]; then
                                return 1
                            fi

                            attempt=$((attempt + 1))
                            sleep 5
                        done

                        return 1
                    }

                    docker network inspect "$DOCKER_NETWORK" \
                        >/dev/null 2>&1 \
                        || docker network create "$DOCKER_NETWORK"

                    docker rm -f \
                        "$PROMETHEUS_CONTAINER" \
                        "$ALERTMANAGER_CONTAINER" \
                        "$ALERT_RECEIVER_CONTAINER" \
                        >/dev/null 2>&1 || true

                    docker build \
                        -t "sit223-alert-receiver:build-${BUILD_NUMBER}" \
                        monitoring/alert-receiver

                    docker run -d \
                        --name "$ALERT_RECEIVER_CONTAINER" \
                        --network "$DOCKER_NETWORK" \
                        -p 5003:5001 \
                        -v sit223-alert-data:/data \
                        "sit223-alert-receiver:build-${BUILD_NUMBER}"

                    docker run -d \
                        --name "$ALERTMANAGER_CONTAINER" \
                        --network "$DOCKER_NETWORK" \
                        -p 9093:9093 \
                        -v "$WORKSPACE/monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" \
                        -v sit223-alertmanager-data:/alertmanager \
                        prom/alertmanager:v0.33.1 \
                        --config.file=/etc/alertmanager/alertmanager.yml \
                        --storage.path=/alertmanager

                    docker run -d \
                        --name "$PROMETHEUS_CONTAINER" \
                        --network "$DOCKER_NETWORK" \
                        -p 9090:9090 \
                        -v "$WORKSPACE/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
                        -v "$WORKSPACE/monitoring/alerts.yml:/etc/prometheus/alerts.yml:ro" \
                        -v sit223-prometheus-data:/prometheus \
                        prom/prometheus:v3.13.1 \
                        --config.file=/etc/prometheus/prometheus.yml \
                        --storage.tsdb.path=/prometheus \
                        --web.enable-lifecycle

                    wait_http \
                        http://127.0.0.1:5003/health \
                        "Alert receiver"

                    wait_http \
                        http://127.0.0.1:9093/-/ready \
                        "Alertmanager"

                    wait_http \
                        http://127.0.0.1:9090/-/ready \
                        "Prometheus"

                    docker exec "$ALERT_RECEIVER_CONTAINER" \
                        python -c \
                        "from pathlib import Path; Path('/data/alerts.jsonl').unlink(missing_ok=True)"

                    echo "Waiting for Prometheus to report the production target as UP."

                    TARGET_READY=0
                    ATTEMPT=1

                    while [ "$ATTEMPT" -le 18 ]; do
                        curl -fsS \
                            http://127.0.0.1:9090/api/v1/targets \
                            > artifacts/prometheus-targets.json

                        if python3 - <<'PY_CHECK_TARGET'
import json

with open("artifacts/prometheus-targets.json", encoding="utf-8") as report:
    payload = json.load(report)

targets = payload.get("data", {}).get("activeTargets", [])

target_is_up = any(
    target.get("labels", {}).get("job") == "sit223-taskmanager"
    and target.get("health") == "up"
    for target in targets
)

raise SystemExit(0 if target_is_up else 1)
PY_CHECK_TARGET
                        then
                            TARGET_READY=1
                            break
                        fi

                        echo "Prometheus target check ${ATTEMPT}: waiting"
                        ATTEMPT=$((ATTEMPT + 1))
                        sleep 5
                    done

                    if [ "$TARGET_READY" -ne 1 ]; then
                        echo "Prometheus did not report the application as UP."
                        cat artifacts/prometheus-targets.json
                        exit 1
                    fi

                    echo "Prometheus production target: UP"

                    echo "Stopping production briefly to simulate an incident."
                    docker stop "$PRODUCTION_CONTAINER" >/dev/null

                    FIRING_ALERT_FOUND=0
                    ATTEMPT=1

                    while [ "$ATTEMPT" -le 18 ]; do
                        curl -fsS \
                            http://127.0.0.1:5003/alerts \
                            > artifacts/alert-notifications.json

                        if python3 - <<'PY_CHECK_FIRING'
import json

with open("artifacts/alert-notifications.json", encoding="utf-8") as report:
    records = json.load(report)

found = any(
    record.get("status") == "firing"
    and any(
        alert.get("labels", {}).get("alertname") == "TaskManagerDown"
        for alert in record.get("alerts", [])
    )
    for record in records
)

raise SystemExit(0 if found else 1)
PY_CHECK_FIRING
                        then
                            FIRING_ALERT_FOUND=1
                            break
                        fi

                        echo "Firing alert check ${ATTEMPT}: waiting"
                        ATTEMPT=$((ATTEMPT + 1))
                        sleep 5
                    done

                    if [ "$FIRING_ALERT_FOUND" -ne 1 ]; then
                        echo "The TaskManagerDown alert was not received."
                        docker start "$PRODUCTION_CONTAINER" >/dev/null
                        wait_healthy "$PRODUCTION_CONTAINER" || true
                        exit 1
                    fi

                    echo "TaskManagerDown firing alert: RECEIVED"

                    docker start "$PRODUCTION_CONTAINER" >/dev/null

                    if ! wait_healthy "$PRODUCTION_CONTAINER"; then
                        echo "Production did not recover after incident simulation."
                        docker logs "$PRODUCTION_CONTAINER" || true
                        exit 1
                    fi

                    RESOLVED_ALERT_FOUND=0
                    ATTEMPT=1

                    while [ "$ATTEMPT" -le 18 ]; do
                        curl -fsS \
                            http://127.0.0.1:5003/alerts \
                            > artifacts/alert-notifications.json

                        if python3 - <<'PY_CHECK_RESOLVED'
import json

with open("artifacts/alert-notifications.json", encoding="utf-8") as report:
    records = json.load(report)

found = any(
    record.get("status") == "resolved"
    and any(
        alert.get("labels", {}).get("alertname") == "TaskManagerDown"
        for alert in record.get("alerts", [])
    )
    for record in records
)

raise SystemExit(0 if found else 1)
PY_CHECK_RESOLVED
                        then
                            RESOLVED_ALERT_FOUND=1
                            break
                        fi

                        echo "Resolved alert check ${ATTEMPT}: waiting"
                        ATTEMPT=$((ATTEMPT + 1))
                        sleep 5
                    done

                    if [ "$RESOLVED_ALERT_FOUND" -ne 1 ]; then
                        echo "The resolved notification was not received."
                        exit 1
                    fi

                    curl -fsS \
                        http://127.0.0.1:9090/api/v1/rules \
                        > artifacts/prometheus-rules.json

                    curl -fsS \
                        http://127.0.0.1:5003/alerts \
                        > artifacts/alert-notifications.json

                    echo "TaskManagerDown resolved alert: RECEIVED"

                    echo
                    echo "========== MONITORING SERVICES =========="

                    docker ps \
                        --filter name=sit223-prometheus \
                        --filter name=sit223-alertmanager \
                        --filter name=sit223-alert-receiver \
                        --filter name=sit223-taskmanager-production

                    echo
                    echo "MONITORING AND ALERTING RESULT: PASSED"
                    echo "Prometheus: http://localhost:9090"
                    echo "Alertmanager: http://localhost:9093"
                    echo "Alert receiver: http://localhost:5003/alerts"
                '''
            }
        }
    }

    post {
        always {
            archiveArtifacts(
                artifacts: 'reports/**/*, artifacts/**/*, htmlcov/**/*',
                allowEmptyArchive: true,
                fingerprint: true
            )
        }

        success {
            echo 'All seven Jenkins pipeline stages completed successfully.'
        }

        failure {
            echo 'The pipeline failed. Relevant reports and logs were preserved.'

            sh '''
                docker ps -a \
                    --filter name=sit223-taskmanager \
                    --filter name=sit223-prometheus \
                    --filter name=sit223-alertmanager \
                    --filter name=sit223-alert-receiver \
                    || true
            '''
        }
    }
}
