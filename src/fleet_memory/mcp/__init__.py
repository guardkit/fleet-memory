"""FastMCP server for fleet-memory: stdio-only MCP interface for Claude Desktop.

This package provides the MCP server that replaces the Graphiti MCP.
Communicates over stdio transport only (no HTTP/SSE).

Wave-1 (TASK-MCP-001): Server scaffolding, lifespan, stdio entry point
Wave-3 (TASK-MCP-002-006): Individual tool registrations
Wave-5 (TASK-MCP-007): Final integration and testing
"""

from __future__ import annotations

__all__ = ["ServerContext", "create_mcp_server", "register_all"]

from fleet_memory.mcp.server import ServerContext, create_mcp_server, register_all
