# Changelog

## November 2026
- Tests for the agent's flow and the DataHub write-back, using stand-ins: the approval gate, dry runs, warnings and partial failures.
- A citation file (Apache-2.0) and a contributing guide. Two unused imports removed.

## October 2026
- CI tests Python 3.10 to 3.14, with read-only access, a 15-minute limit and superseded pull request runs cancelled. Weekly Dependabot, a security policy and a CI badge.
- Tests for how settings are read from the environment, and that the demo regulation is well formed and marked as made up.

## September 2026
- Lineage is read from the real DataHub MCP response instead of a seeded copy.
- Dashboards and the model are seeded as real DataHub entities. The README lists what is still simplified.
- The MCP write-back helpers call the real DataHub tools. They are optional, and the README says why they are not wired in.
- Tests for the graph, the scenario arithmetic, the recommendation and the decision card.
- The minimum `mcp` version raised to 1.28.1 for a security fix (PYSEC-2026-3483).
- An install-and-import check, and current CI action versions.

## August 2026
- First version: an agent that weighs a regulatory change against the data and dashboards it touches in DataHub, and recommends what to invest in.
