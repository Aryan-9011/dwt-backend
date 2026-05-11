FROM python:3.11-slim

# Install Node.js 20 + Claude Code CLI (for agent pipeline)
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create non-root user (Claude Code refuses --dangerously-skip-permissions as root)
RUN useradd -m -u 1001 appuser && \
    chmod +x entrypoint.sh && \
    mkdir -p outputs/carousel workspace/outputs/automation/carousel-pipeline && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["./entrypoint.sh"]
