#!/bin/bash

# Risk Management Agent Quick Start Script

echo "🛡️  Risk Management Agent Quick Start"
echo "====================================="

# Check if .env file exists in backend
if [ ! -f "backend/.env" ]; then
    echo "❌ .env file not found in backend directory"
    echo "Please run the setup first:"
    echo "cd backend && python3 setup_env.py"
    exit 1
fi

# Function to check if a port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null ; then
        return 0
    else
        return 1
    fi
}

# Check if backend dependencies are installed
if [ ! -d "backend/venv" ]; then
    echo "📦 Setting up backend virtual environment..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
fi

# Check if frontend dependencies are installed
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd frontend
    npm install
    cd ..
fi

echo "🚀 Starting Risk Management Agent..."

# Start backend in background
echo "Starting backend server on port 8000..."
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 3

# Check if backend started successfully
if check_port 8000; then
    echo "✅ Backend server is running on https://api.agentic.complynexus.com"
    echo "   API Documentation: https://api.agentic.complynexus.com/docs"
else
    echo "❌ Backend server failed to start"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# Start frontend in background
echo "Starting frontend server on port 5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait a moment for frontend to start
sleep 5

# Check if frontend started successfully
if check_port 5173; then
    echo "✅ Frontend server is running on http://localhost:5173"
else
    echo "❌ Frontend server failed to start"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 1
fi

echo ""
echo "🎉 Risk Management Agent is ready!"
echo "📱 Open http://localhost:5173 in your browser"
echo "🔧 API Documentation: https://api.agentic.complynexus.com/docs"
echo ""
echo "Features available:"
echo "  • AI-powered risk assessment"
echo "  • Compliance management guidance"
echo "  • Risk summary generation"
echo "  • Quick action templates"
echo ""
echo "Press Ctrl+C to stop the application"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping Risk Management Agent..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "✅ Application stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Keep script running
wait 