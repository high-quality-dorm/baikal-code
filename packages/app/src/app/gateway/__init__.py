"""Клиент к шлюзу db_mcp (MCP, stdio transport)."""

from app.gateway.client import GatewayClient, GatewayError

__all__ = ["GatewayClient", "GatewayError"]
