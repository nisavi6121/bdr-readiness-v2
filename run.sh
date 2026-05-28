#!/usr/bin/env bash
set -e

echo "==> Running pipeline..."
python generation/generate.py
python backend/pipeline/01_clean.py
python backend/pipeline/02_features.py
python backend/pipeline/03_score.py
python backend/pipeline/04_rank.py

echo "==> Starting API server (http://localhost:8000)..."
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "==> Starting Vite dev server (http://localhost:5173)..."
cd frontend && npm run dev &
VITE_PID=$!

trap "kill $API_PID $VITE_PID 2>/dev/null" EXIT
wait
