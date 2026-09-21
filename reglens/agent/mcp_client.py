"""Thin async wrapper around the official DataHub MCP server (over stdio via uvx).

This is the required, on-camera integration: RegLens reads the graph THROUGH the
MCP server rather than the SDK, so the "agent interrogates DataHub's context graph"
story is literally true.

Tool names verified from the DataHub MCP docs for READS:
    search, get_entities, get_lineage, list_schema_fields, get_lineage_paths_between

The two MUTATION helpers (`update_description`, `add_glossary_term(s)`) call the
real server's tools by their exact registered names and argument names, quoted
below from its source. They are an OPTIONAL path: the agent does not call them
(it writes back through the DataHub SDK, see agent/writeback.py) and they are
tested against the fake MCP server in tests/fixtures only, never against a live
DataHub. Run `python -m reglens.agent.mcp_client` to print the tools your server
exposes and whether the mutation ones are among them.
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack

from reglens.config import MCP_ARGS, MCP_COMMAND, MCP_MUTATION_ENABLED

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_AVAILABLE = True
except Exception:  # noqa: BLE001
    _MCP_AVAILABLE = False


# ---- The real mutation tools, quoted from the server's source ----------------------
#
# Source: https://github.com/acryldata/mcp-server-datahub, commit 38e4523 (main,
# 2026-09-16). Paths are relative to the repo root.
#
# src/mcp_server_datahub/tools/descriptions.py
#
#     @min_version(cloud="0.3.16", oss="1.4.0")
#     def update_description(
#         entity_urn: str,
#         operation: Literal["replace", "append", "remove"] = "replace",
#         description: Optional[str] = None,
#         column_path: Optional[str] = None,
#     ) -> dict:
#     # "description ... Required for 'replace' and 'append', ignored for 'remove'."
#     # Returns {"success": bool, "urn": str, "column_path": ..., "message": str}.
#     # Raises (=> an MCP error result) if the description is empty for replace/append.
#
# src/mcp_server_datahub/tools/terms.py
#
#     @min_version(cloud="0.3.16", oss="1.4.0")
#     def add_glossary_terms(
#         term_urns: List[str],
#         entity_urns: List[str],
#         column_paths: Optional[List[Optional[str]]] = None,
#     ) -> dict:
#     # Returns {"success": bool, "message": str}. Every URN in `term_urns` must
#     # already exist in DataHub as a glossary term, or the call raises ValueError
#     # ("The following glossary term URNs do not exist in DataHub ...").
#     # `column_paths`, if given, must be the same length as `entity_urns`.
#
# src/mcp_server_datahub/mcp_server.py, register_mutation_tools()
#
#     enabled = get_boolean_env_variable("TOOLS_IS_MUTATION_ENABLED")   # default false
#     if not enabled:
#         return                                    # NO mutation tool is registered
#     ...
#     _register_tool(mcp_instance, "add_terms", add_glossary_terms, tags={"mutation"})
#     _register_tool(mcp_instance, "update_description", update_description)
#
# Two things to notice. The glossary tool is REGISTERED as `add_terms`, not under its
# Python name `add_glossary_terms`, so the name a client must call is `add_terms`.
# And both tools are hidden from list_tools unless the server process was started with
# TOOLS_IS_MUTATION_ENABLED=true (`_server_params` below sets it), and, because of
# `@min_version`, also when the DataHub server behind it is older than OSS 1.4.0 /
# Cloud 0.3.16. From the client the two cases look the same: the tool is not listed.
UPDATE_DESCRIPTION_TOOL = "update_description"
ADD_TERMS_TOOL = "add_terms"


class MutationToolsUnavailable(RuntimeError):
    """The DataHub MCP server does not list the mutation tool that was asked for."""


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
        self._stack: AsyncExitStack | None = None
        self.tool_names: list[str] = []

    async def __aenter__(self) -> "DataHubMCP":
        # One exit stack owns the subprocess transport and the session, so they are
        # closed in reverse order whether or not the body of the `async with` raised.
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(_server_params()))
            self._session = await stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            tools = await self._session.list_tools()
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        self.tool_names = [t.name for t in tools.tools]
        return self

    async def __aexit__(self, *exc) -> None:
        # Close the session and the subprocess WITHOUT handing them the body's
        # exception: passing it in makes anyio wrap it in an ExceptionGroup (and
        # sometimes fail to leave a cancel scope), so a caller could no longer
        # catch the RuntimeError / MutationToolsUnavailable it raised inside the
        # block. Returning None lets that exception propagate as itself.
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.aclose()

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

    async def get_lineage(
        self,
        urn: str,
        direction: str = "DOWNSTREAM",
        max_hops: int = 3,
        max_results: int = 100,
    ) -> object:
        """Fetch lineage for `urn` in the given direction.

        The real DataHub MCP server's `get_lineage` tool takes `upstream: bool`,
        not a `direction` string (verified against acryldata/mcp-server-datahub's
        `tools/lineage.py`) — `direction` here is just this wrapper's friendlier
        parameter name. `max_hops=3` is documented by that tool as "equivalent
        to unlimited hops", which is what gives RegLens the full downstream
        closure in a single call.
        """
        name = self._find_tool("lineage") or "get_lineage"
        upstream = direction.upper() == "UPSTREAM"
        return await self.call(
            name, urn=urn, upstream=upstream, max_hops=max_hops, max_results=max_results
        )

    # ---- write-back (mutation) — optional, not used by the agent ----
    def _require_tool(self, name: str) -> str:
        """Return `name` if the server lists it, else raise a clear error.

        The server does not register its mutation tools unless it was started
        with TOOLS_IS_MUTATION_ENABLED=true (or if GMS is older than the tool's
        `min_version`), so an absent tool is the signal, not a call that fails
        later with a bare "unknown tool".
        """
        if name not in self.tool_names:
            raise MutationToolsUnavailable(
                f"The DataHub MCP server does not expose the '{name}' tool, so RegLens "
                "cannot write back through MCP. The server only registers its mutation "
                "tools when it is started with TOOLS_IS_MUTATION_ENABLED=true (RegLens "
                f"sends {MCP_MUTATION_ENABLED!r}; set it in the environment to override), "
                "and only when the DataHub server behind it is OSS 1.4.0+ or Cloud "
                f"0.3.16+. Tools the server did list: {sorted(self.tool_names)}. "
                "Use the SDK write-back (reglens.agent.writeback) instead."
            )
        return name

    async def update_description(
        self,
        urn: str,
        description: str | None,
        operation: str = "replace",
        column_path: str | None = None,
    ) -> dict:
        """Set, append to or remove the description of `urn` (or of one column).

        Calls the real `update_description(entity_urn, operation, description,
        column_path)` tool and returns its decoded result. A tool error raises.
        """
        name = self._require_tool(UPDATE_DESCRIPTION_TOOL)
        args: dict = {"entity_urn": urn, "operation": operation}
        if description is not None:
            args["description"] = description
        if column_path is not None:
            args["column_path"] = column_path
        return self.decode_result(await self.call(name, **args))

    async def add_glossary_terms(
        self,
        term_urns: list[str],
        entity_urns: list[str],
        column_paths: list[str | None] | None = None,
    ) -> dict:
        """Attach every term in `term_urns` to every entity in `entity_urns`.

        Calls the real `add_terms` tool (`add_glossary_terms(term_urns, entity_urns,
        column_paths)` in its source) and returns its decoded result. The terms must
        already exist in DataHub or the server rejects the call, and that error raises.
        """
        name = self._require_tool(ADD_TERMS_TOOL)
        args: dict = {"term_urns": term_urns, "entity_urns": entity_urns}
        if column_paths is not None:
            args["column_paths"] = column_paths
        return self.decode_result(await self.call(name, **args))

    async def add_glossary_term(self, urn: str, term: str) -> dict:
        """One term on one entity. `term` is a glossary term URN or a bare term name."""
        term_urn = term if term.startswith("urn:li:") else f"urn:li:glossaryTerm:{term}"
        return await self.add_glossary_terms([term_urn], [urn])

    @staticmethod
    def decode_result(res: object) -> dict:
        """Decode a `call_tool` result into the plain dict the server sent back.

        MCP tool results can carry a structured-content dict directly (when the
        server declares an output schema), or only the legacy `content` list of
        text blocks, whose first text block is the JSON payload — the DataHub
        MCP server currently does the latter. Both are handled here rather than
        assumed, and an error result raises instead of being silently treated
        as an empty/successful payload. The attribute is `is_error`/
        `structured_content` on `mcp>=2` and `isError`/`structuredContent` on
        `mcp<2` (the SDK's own v1->v2 migration renamed them) — both spellings
        are checked so this works whichever the environment resolved.
        """
        is_error = getattr(res, "is_error", None)
        if is_error is None:
            is_error = getattr(res, "isError", False)
        if is_error:
            raise RuntimeError(f"MCP tool call returned an error: {res!r}")

        structured = getattr(res, "structured_content", None)
        if structured is None:
            structured = getattr(res, "structuredContent", None)
        if isinstance(structured, dict):
            return structured

        for block in getattr(res, "content", None) or []:
            text = getattr(block, "text", None)
            if text:
                return json.loads(text)
        raise ValueError(f"Could not decode a JSON payload out of MCP result: {res!r}")


async def _print_tools() -> None:
    async with DataHubMCP() as mcp:
        print("DataHub MCP server tools available:")
        for n in mcp.tool_names:
            print(f"  - {n}")
        missing = [t for t in (UPDATE_DESCRIPTION_TOOL, ADD_TERMS_TOOL) if t not in mcp.tool_names]
        if missing:
            print(f"Mutation tools not exposed: {', '.join(missing)} "
                  "(the server needs TOOLS_IS_MUTATION_ENABLED=true). "
                  "The agent's SDK write-back does not need them.")
        else:
            print("Mutation tools exposed: the optional MCP write-back helpers can run.")


if __name__ == "__main__":
    asyncio.run(_print_tools())
