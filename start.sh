#!/bin/bash
echo "VC Scout - Starting..."
echo ""

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 required."
    exit 1
fi

cd "$(dirname "$0")"

# Backend
echo "[1/3] Setting up backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q 2>/dev/null

echo "[2/3] Starting backend (port 8000)..."
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Frontend
echo "[3/3] Starting frontend (port 5173)..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install --silent 2>/dev/null
fi
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "Ready!"
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
