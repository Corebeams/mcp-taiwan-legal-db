"""以 Streamable HTTP 啟動 mcp-taiwan-legal-db（由 Dockerfile 的 CMD 執行）"""

from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.server import mcp

# 允許連線的 Host：測試站部署時的 container 名稱、本機 docker compose 的 service 名稱，以及本機存取
# container port 8000 會出現在 Host header，因此每個名稱都另外允許 <名稱>:*
HOSTS = [
    "law-sme-ai-api--mcp-taiwan-legal-db",
    "mcp-taiwan-legal-db",
    "localhost",
    "127.0.0.1",
]

# 以一般使用者執行無法使用 1024 以下的 port
mcp.run(
    transport="streamable-http",
    host="0.0.0.0",
    port=8000,
    transport_security=TransportSecuritySettings(
        allowed_hosts=[allowed for host in HOSTS for allowed in (host, f"{host}:*")]
    ),
)