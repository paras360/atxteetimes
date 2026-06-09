#!/bin/bash
# ATX Tee Times - Start Script
# Runs both backend and frontend from parent directory

set -e

echo "🚀 Starting ATX Tee Times..."
echo ""

# Check if backend .env exists
if [ ! -f "backend/.env" ]; then
    echo "❌ Error: backend/.env not found!"
    echo "Please create backend/.env with your configuration."
    echo "See README.md for details."
    exit 1
fi

# Kill any existing processes on these ports
echo "🧹 Cleaning up any existing processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:5173 | xargs kill -9 2>/dev/null || true
sleep 1

# Start backend
echo "🔧 Starting backend on http://localhost:8000..."
cd backend
uv run uvicorn app.main:app --reload --port 8000 > ../backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Wait for backend to be ready
echo "⏳ Waiting for backend to start..."
sleep 3

# Check if backend is running
if ! curl -s http://localhost:8000/api/health > /dev/null; then
    echo "❌ Backend failed to start. Check backend.log for errors."
    cat backend.log
    exit 1
fi

echo "✅ Backend running (PID: $BACKEND_PID)"

# Start frontend
echo "🎨 Starting frontend on http://localhost:5173..."
cd frontend
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

# Wait for frontend to be ready
echo "⏳ Waiting for frontend to start..."
sleep 3

echo "✅ Frontend running (PID: $FRONTEND_PID)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 ATX Tee Times is running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📱 Frontend:  http://localhost:5173"
echo "🔧 Backend:   http://localhost:8000"
echo "📚 API Docs:  http://localhost:8000/docs"
echo ""
echo "💡 Logs:"
echo "   Backend:  tail -f backend.log"
echo "   Frontend: tail -f frontend.log"
echo ""
echo "🛑 To stop: ./stop.sh or Ctrl+C"
echo ""

# Save PIDs to file for stop script
echo "$BACKEND_PID" > .backend.pid
echo "$FRONTEND_PID" > .frontend.pid

# Follow logs (Ctrl+C to exit, processes keep running)
echo "📋 Showing combined logs (Ctrl+C to exit)..."
echo ""
tail -f backend.log frontend.log

