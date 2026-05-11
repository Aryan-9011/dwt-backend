#!/bin/bash
# Start backend locally with FULL AGENT MODE
# This uses the Claude Code agent system (real web research + nano-banana images)
# Run from the backend/ directory: ./start-local.sh

cd "$(dirname "$0")"

export USE_AGENTS=true
export BASE_URL=http://localhost:8000

# Load credentials
if [ -f "../credentials/.env" ]; then
  export $(grep -v '^#' ../credentials/.env | xargs)
fi

echo "Starting DWT backend in AGENT MODE..."
echo "  USE_AGENTS=true  → full agent pipeline (web research + Claude agents + nano-banana)"
echo "  BASE_URL=$BASE_URL"
echo ""

python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
