#!/usr/bin/env bash
# Runs the backend unit tests with coverage and prints per-area line coverage (Section 9.3).
# Usage: ./run_tests.sh            (uses local python3, creating .venv-tests if needed)
#        ./run_tests.sh --docker   (runs inside python:3.12-slim, needs only Docker)
#        ./run_tests.sh --write    (also rewrites COVERAGE.json with the measured figures)
set -euo pipefail
cd "$(dirname "$0")"
WRITE=""
for a in "$@"; do [ "$a" = "--write" ] && WRITE="COVERAGE.json"; done

if [ "${1:-}" = "--docker" ]; then
  exec docker run --rm -v "$PWD":/w -w /w python:3.12-slim bash -c \
    "pip install -q -r backend/requirements-dev.txt && python -m pytest tests -q -p no:warnings \
     --cov=backend/app --cov-report=term --cov-report=json:/tmp/cov.json && python tools/coverage_areas.py /tmp/cov.json"
fi

PY=python3
if ! $PY -c "import fastapi, networkx, pytest_cov, httpx" 2>/dev/null; then
  [ -d .venv-tests ] || python3 -m venv .venv-tests
  .venv-tests/bin/pip install -q -r backend/requirements-dev.txt || .venv-tests/bin/pip install -q fastapi \
    "uvicorn[standard]" networkx "psycopg[binary]" redis pytest pytest-cov httpx
  PY=.venv-tests/bin/python
fi
$PY -m pytest tests -q -p no:warnings --cov=backend/app --cov-report=term --cov-report=json:.coverage.json
$PY tools/coverage_areas.py .coverage.json $WRITE
