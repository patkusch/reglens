"""Thin async wrapper around the official DataHub MCP server (over stdio via uvx).

This is the required, on-camera integration: RegLens reads the graph THROUGH the
MCP server rather than the SDK, so the "agent interrogates DataHub's context graph"
story is literally true.

Tool names verified from the DataHub MCP docs for READS:
    search, get_entities, get_lineage, list_schema_fields, get_lineage_paths_between
MUTATION tool names vary by MCP server version — we discover them at runtime with
list_tools() and match by keyword, so you don't have to hard-code a name that might
drift. Run `python -m reglens.agent.mcp_client` to print the exact tools your
server exposes.
"""
from __future__ import annotations

import asyncio
import os

from reglens.config import MCP_ARGS, MCP_COMMAND, MCP_MUTATION_ENABLED

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_AVAILABLE = True
except Exception:  # noqa: BLE001
    _MCP_AVAILABLE = False


def _server_params() -> "StdioServerParameters":
    env = dict(os.environ)
    # RegLens needs the write-back tools switched on.
    env["TOOLS_IS_MUTATION_ENABLED"] = MCP_MUTATION_ENABLED
    return StdioServerParameters(command=MCP_COMMAND, args=MCP_ARGS, env=env)


class DataHubMCP:
    """Async context manager exposing call_tool + convenience helpers."""

    def __init__(self) -> None:
        if not _MCP_AVAILABLE:
            raise RuntimeError(
                "The 'mcp' package is not installed. `pip install mcp`, or run the "
                "agent with --no-mcp to use the deterministic fallback."
            )
        self._session: ClientSession | None = None
        self._stdio_ctx = None
        self.tool_names: list[str] = []

    async def __aenter__(self) -> "DataHubMCP":
        self._stdio_ctx = stdio_client(_server_params())
        read, write = await self._stdio_ctx.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        tools = await self._session.list_tools()
        self.tool_names = [t.name for t in tools.tools]
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session:
            await self._session.__aexit__(*exc)
        if self._stdio_ctx:
            await self._stdio_ctx.__aexit__(*exc)

    async def call(self, name: str, **args) -> object:
        assert self._session is not None
        res = await self._session.call_tool(name, args)
        return res

    def _find_tool(self, *keywords: str) -> str | None:
        for name in self.tool_names:
            low = name.lower()
            if all(k in low for k in keywords):
                return name
        return None

    # ---- reads ----
    async def search(self, query: str) -> object:
        name = self._find_tool("search") or "search"
        return await self.call(name, query=query)

    async def get_lineage(self, urn: str, direction: str = "DOWNSTREAM") -> object:
        name = self._find_tool("lineage") or "get_lineage"
        return await self.call(name, urn=urn, direction=direction)

    # ---- write-back (mutation) ----
    async def add_glossary_term(self, urn: str, term: str) -> object:
        name = self._find_tool("add", "glossary") or self._find_tool("glossary")
        if not name:
            raise RuntimeError(f"No glossary mutation tool found in: {self.tool_names}")
        return await self.call(name, urn=urn, term=term)

    async def update_description(self, urn: str, description: str) -> object:
        name = self._find_tool("description") or self._find_tool("update", "doc")
        if not name:
            raise RuntimeError(f"No description mutation tool found in: {self.tool_names}")
        return await self.call(name, urn=urn, description=description)


async def _print_tools() -> None:
    async with DataHubMCP() as mcp:
        print("DataHub MCP server tools available:")
        for n in mcp.tool_names:
            print(f"  - {n}")


if __name__ == "__main__":
    asyncio.run(_print_tools())
