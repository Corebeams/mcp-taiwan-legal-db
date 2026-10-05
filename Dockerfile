FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
  MCP_TAIWAN_LEGAL_DB_HOME=/data/cache

WORKDIR /app

COPY pyproject.toml README.md ./
COPY mcp_server/ ./mcp_server/
COPY server.py ./

# mcp-taiwan-legal-db 1.1.0 起使用 MCP SDK 2.x，不再沿用舊版固定 SDK 1.x 的安裝方式。
# 直接依 fork 的 pyproject.toml 安裝；升級前需確認 server.py 的啟動設定仍相容 MCP SDK 2.x。
RUN pip install --no-cache-dir . \
  && python -m playwright install --with-deps chromium \
  && useradd --create-home --uid 1000 --user-group mcp \
  && mkdir -p /data/cache \
  && chown -R mcp:mcp /data \
  && rm -rf /var/lib/apt/lists/*

# 以一般使用者執行：Chromium 會以 --no-sandbox 開啟外部網頁，不以 root 執行降低被攻破時的影響。
# 套件的執行期資料不寫入 site-packages，改由 MCP_TAIWAN_LEGAL_DB_HOME 指到 /data/cache：
# - 查詢快取、WAF cookie、法規清單更新資料都存放在 /data/cache
# - 部署時掛載 /data/cache 可在重建 container 後保留資料
USER mcp

EXPOSE 8000

CMD ["python", "server.py"]