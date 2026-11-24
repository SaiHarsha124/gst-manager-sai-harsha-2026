#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then python3 -m venv backend/.venv; fi
backend/.venv/bin/python -m pip install -r backend/requirements.txt
( cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000 ) &
if [ ! -d frontend/node_modules ]; then (cd frontend && npm install); fi
(cd frontend && npm run dev) &
echo "API docs: http://localhost:8000/docs"
echo "Frontend: http://localhost:5173"
wait
