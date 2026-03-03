#!/bin/zsh
# Newman Trading System — start backend + frontend with logs

PROJ=/Users/agent/Projects/newmanMarch3
LOG_DIR="$PROJ/logs"
mkdir -p "$LOG_DIR"

echo "=== Newman Trading System ===" | tee -a "$LOG_DIR/startup.log"
echo "Started: $(date)" | tee -a "$LOG_DIR/startup.log"

# ── Kill any stale processes ────────────────────────────────────────────────
pkill -f "uvicorn app.main:app" 2>/dev/null && echo "Killed stale backend" || true
pkill -f "next dev" 2>/dev/null && echo "Killed stale frontend" || true
sleep 1

# ── Backend ─────────────────────────────────────────────────────────────────
echo "Starting backend on :8000..."
cd "$PROJ/backend"
nohup "$PROJ/backend/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info \
  >> "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID" | tee -a "$LOG_DIR/startup.log"

# ── Wait for backend to be ready ────────────────────────────────────────────
echo -n "Waiting for backend..."
for i in {1..15}; do
  if curl -sf http://localhost:8000/ > /dev/null 2>&1; then
    echo " ready."
    break
  fi
  echo -n "."
  sleep 1
done

# ── Frontend ────────────────────────────────────────────────────────────────
echo "Starting frontend on :3000..."
cd "$PROJ/frontend"
nohup npm run dev >> "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID" | tee -a "$LOG_DIR/startup.log"

echo ""
echo "✅ Newman Trading System running"
echo "   Backend:   http://localhost:8000"
echo "   Frontend:  http://localhost:3000"
echo "   API docs:  http://localhost:8000/docs"
echo "   Logs:      $LOG_DIR/"
echo ""
echo "PIDs: backend=$BACKEND_PID, frontend=$FRONTEND_PID" | tee -a "$LOG_DIR/startup.log"
