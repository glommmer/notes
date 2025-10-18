#!/bin/bash
# Streamlit Client Startup Script

echo "🎨 Starting Airflow Monitoring Agent UI..."
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

# Start Streamlit
echo "✅ Starting Streamlit UI on http://localhost:8501"
echo ""

streamlit run app/main.py --server.port 8501
