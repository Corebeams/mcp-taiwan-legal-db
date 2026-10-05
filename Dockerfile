FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
  MCP_TAIWAN_LEGAL_DB_HOME=/data/cache

WORKDIR /app

COPY pyproject.toml README.md ./
COPY mcp_server/ ./mcp_server/
COPY server.py ./

RUN pip install --no-cache-dir . \
  && python -m playwright install --with-deps chromium \
  && useradd --create-home --uid 1000 --user-group mcp \
  && mkdir -p /data/cache \
  && chown -R mcp:mcp /data \
  && rm -rf /var/lib/apt/lists/*

USER mcp

EXPOSE 8000

CMD ["python", "server.py"]