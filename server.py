"""Run mcp-taiwan-legal-db over Streamable HTTP."""

from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.server import mcp

_HOSTS = [
    "law-sme-ai-api--mcp-taiwan-legal-db",
    "mcp-taiwan-legal-db",
    "localhost",
    "127.0.0.1",
]

mcp.run(
    transport="streamable-http",
    host="0.0.0.0",
    port=8000,
    transport_security=TransportSecuritySettings(
        allowed_hosts=[allowed for host in _HOSTS for allowed in (host, f"{host}:*")]
    ),
)