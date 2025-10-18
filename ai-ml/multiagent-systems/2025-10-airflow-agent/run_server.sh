#!/bin/bash
# FastAPI Server Startup Script

echo "🚀 Starting Airflow Monitoring Agent Server..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment not found. Creating one..."
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Please create one with required configuration."
    echo "See README.md for details."
    exit 1
fi

# Start server
echo "✅ Starting FastAPI server on http://localhost:8000"
echo "📚 API Documentation: http://localhost:8000/docs"
echo ""

python -m uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
