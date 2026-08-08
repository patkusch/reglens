"""Central config. Reads from environment; see .env.template."""
import os

# --- DataHub connection (used by the seed script and the SDK write-back path) ---
DATAHUB_GMS_URL = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")
DATAHUB_TOKEN = os.getenv("DATAHUB_TOKEN", "")  # PAT from DataHub UI > Settings > Access Tokens

# --- MCP server (how the agent reads/writes the graph) ---
# We launch the official DataHub MCP server over stdio with `uvx`.
MCP_COMMAND = os.getenv("MCP_COMMAND", "uvx")
MCP_ARGS = os.getenv("MCP_ARGS", "mcp-server-datahub").split()
# Mutations (write-back) are OFF by default in the MCP server. RegLens needs them ON.
MCP_MUTATION_ENABLED = os.getenv("TOOLS_IS_MUTATION_ENABLED", "true")

# --- Optional LLM driver for the "regulatory analysis" reasoning step ---
# The core loop runs fully deterministic without this. Set a key to enable the agentic path.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# The platform we seed the fictional bank under (any string works in DataHub).
BANK_PLATFORM = os.getenv("BANK_PLATFORM", "snowflake")
BANK_ENV = "PROD"
