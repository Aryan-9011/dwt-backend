#!/bin/sh
# Generate .mcp.json in the workspace using the GEMINI_API_KEY env var
# This runs before uvicorn starts so Claude Code can find nano-banana MCP

cat > /app/workspace/.mcp.json <<EOF
{
  "mcpServers": {
    "nano-banana": {
      "command": "npx",
      "args": ["-y", "nano-banana-mcp"],
      "env": {
        "GEMINI_API_KEY": "${GEMINI_API_KEY}"
      }
    }
  }
}
EOF

echo "Generated /app/workspace/.mcp.json with GEMINI_API_KEY"

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
