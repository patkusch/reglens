<div align="center">

# 🔍 RegLens

### A regulatory-change **investment-decision** agent, built on DataHub.

*Don't just find what a regulation touches — decide what to do about it.*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Built on DataHub](https://img.shields.io/badge/Built%20on-DataHub-1890FF)](https://datahubproject.io/)
[![Powered by MCP](https://img.shields.io/badge/Powered%20by-MCP-6E56CF)](https://modelcontextprotocol.io/)
[![Hackathon](https://img.shields.io/badge/Build%20with%20DataHub-Agents%20That%20Do%20Real%20Work-black)](#)

</div>

---

Most tools answer *"what does this regulation affect?"* **RegLens answers the
question a bank actually has to act on:** *"should we implement this now, defer it,
or do the minimum — and what does each cost?"*

It reads a bank's live data environment **through the DataHub MCP server** to
discover what a regulation touches (via lineage), costs three implementation paths
with a transparent scenario engine, and **writes the decision back into DataHub**
so the next person or agent inherits the assessment instead of rediscovering it.

> 🏆 Built for *Build with DataHub: The Agent Hackathon* — category **Agents That Do Real Work**.

### Why it's different

- 🎯 **Decision, not description** — costs `ACT NOW` / `DEFER` / `MIN. COMPLIANCE`, not just impact.
- 🔗 **Reads *and* writes the graph** — discovers via lineage, then contributes the decision back.
- 🧮 **Transparent economics** — every £ carries an assumption *and* a confidence.
- 🙋 **Human in the loop** — nothing is written until a person approves.

---

## ⏱️ The 60-second story

```
        RCS-2026 (a new regulation)
                    │
                    ▼
     RegLens searches DataHub + walks lineage        ← MCP READ
                    │
                    ▼
      10 affected assets discovered automatically
      (3 datasets · 1 ML model · 3 pipelines · 3 dashboards)
                    │
                    ▼
     Scenario engine costs ACT NOW / DEFER / MIN. COMPLIANCE
     (every £ carries an assumption + a confidence)
                    │
                    ▼
          Impact & Decision Card  →  human approves     ← HUMAN GATE
                    │
                    ▼
   Decision written back onto every affected asset       ← MCP / SDK WRITE
   (glossary term + description, visible in DataHub UI)
```

Example output is in [`examples/`](examples/) — the
[Impact & Decision Card](examples/sample_impact_card.md), the full
[assessment JSON](examples/sample_assessment.json), and the exact
[write-back payload](examples/sample_writeback.json).

---

## 🚀 Setup runbook

> **De-risk in this order.** The only thing that can sink this project is the
> DataHub + MCP round-trip. Get steps 1–4 green *before* touching agent logic.
> Everything after that is guaranteed buildable.

### 0. Prerequisites
- Docker Desktop with **~8 GB RAM** allocated (DataHub quickstart needs it)
- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) (`pip install uv`) — used to run the MCP server via `uvx`

### 1. Bring up DataHub locally
```bash
pip install acryl-datahub
datahub docker quickstart          # spins up DataHub in Docker, ~few minutes
```
Open **http://localhost:9002** (login `datahub` / `datahub`).

### 2. Configure RegLens
```bash
cp .env.template .env
# In the DataHub UI: Settings → Access Tokens → Generate a Personal Access Token
# Paste it into .env as DATAHUB_TOKEN, then:
source .env
pip install -r requirements.txt
```

### 3. Seed the fictional bank (20 assets + lineage)
```bash
python -m reglens.seed.seed_northstar
```
The seed writes each asset as the DataHub entity it really is: tables as
datasets, the three reports as **dashboards**, the risk model as an **ML model**,
and each pipeline as a **data flow holding one data job**. Then in the UI, search
**`customer_risk_profile`** and open its **downstream lineage** — you should see
the chain out to `capital_reporting_dashboard`, passing through the model. That
lineage is what the agent traverses.

### 4. ✅ Prove the MCP round-trip (the critical handshake)
```bash
python -m reglens.agent.mcp_client        # prints the tools your MCP server exposes
```
If this lists tools including a `search`/`lineage` read tool and a
glossary/description mutation tool, **you are done de-risking — ship is now a
matter of build, not luck.**

### 5. Run the agent
```bash
# Full path: read via MCP, cost, human-approve, write back via SDK
python -m reglens.agent.reglens_agent --reg RCS-2026

# Safe-for-camera path: deterministic discovery, no MCP dependency
python -m reglens.agent.reglens_agent --reg RCS-2026 --no-mcp

# See the card + write-back plan without touching DataHub
python -m reglens.agent.reglens_agent --reg RCS-2026 --no-mcp --dry-run
```
After a real write-back, refresh `customer_risk_profile` in the UI: the glossary
term `RegLens.RCS-2026.<decision>` and the assessment description are now on the
asset — and on the dashboards, the model and the jobs too, each written as its
own kind of entity. **That's the money shot.** 💰

### 6. Check the glass box
```bash
pip install -r requirements-dev.txt && python -m pytest -q
```
No DataHub needed. The tests walk the seeded lineage, re-derive every scenario
total from the named assumptions, check the recommendation is the cheapest
expected path, re-run the demo against
[`examples/sample_assessment.json`](examples/sample_assessment.json) so the
committed example cannot drift from the code, and drive a real (subprocess,
stdio) MCP round trip against a fake DataHub MCP server to prove the lineage
parser reads whatever the server actually returns — a mix of datasets,
dashboards, an ML model, data jobs and a chart, each with the URN and fields
DataHub uses for its type. They also build the seeded dashboards, model and jobs
with the real DataHub SDK classes and check the exact aspects and lineage that
would be sent, and run the write-back against a stand-in client.

---

## 🧑‍⚖️ How it uses DataHub (for the judges)

| Judging axis | What RegLens does |
|---|---|
| **Use of DataHub** | Reads the context graph through the **MCP server** (search + lineage traversal) to discover impact, then **contributes back** to the graph (glossary term + description on every affected asset). Goes beyond reading metadata. |
| **Technical execution** | Runs end-to-end: seed → discover → cost → approve → write back. Deterministic core path always works; MCP + LLM are layered on top. |
| **Originality** | Not impact analysis — *investment-decision* support. Costs inaction (P × consequence) and opportunity cost of displaced strategic work, not just implementation. |
| **Real-world usefulness** | Change-capacity triage is a real, expensive problem for every regulated bank. |
| **Submission quality** | This README, a <3-min demo ([`demo/demo_script.md`](demo/demo_script.md)), and sample outputs in `examples/`. |

> 💡 **The write-back is the point.** It maps directly to *"Agents That Do Real Work:
> takes action, and writes results back so the next person or agent inherits the
> knowledge."*

---

## 🏗️ Architecture

```
reglens/
  seed/
    graph.py            # the fictional bank: 20 assets + lineage (dependency-free)
    seed_northstar.py   # writes graph.py into DataHub via the SDK, one real entity type per asset
    regulations.py      # RCS-2026 (fictional reg, fictional regulator)
  engine/
    scenario_engine.py  # transparent cost model — every £ has an assumption + confidence
    impact_card.py      # renders the Impact & Decision Card + write-back payload
  agent/
    mcp_client.py       # async wrapper over the DataHub MCP server (stdio via uvx)
    lineage_parser.py   # parses the MCP server's actual get_lineage response shape
    reglens_agent.py    # orchestrator + CLI + human-approval gate
    writeback.py        # reliable SDK write-back path
  models.py             # shared dataclasses
```

### What's real vs. what's still simplified
- ✅ **Real:** DataHub graph, MCP read round-trip — including genuinely parsing
  the lineage result — scenario engine, SDK write-back, human gate.
- ✅ **MCP lineage parse:** `discover_impact_via_mcp()` parses the server's
  actual `get_lineage` response (`reglens/agent/lineage_parser.py`) — every URN,
  name, entity type and hop count in the resulting assets comes from that
  response, not from `reglens/seed/graph.py`. Proven in
  `tests/test_mcp_lineage_roundtrip.py`, which drives a real stdio MCP round
  trip against a fake DataHub MCP server whose lineage graph has a different
  shape (a fan-out, a six-hop chain, a convergence, a cycle) from the seeded
  Northstar graph, so the old shortcut couldn't have passed it by coincidence.
  It still falls back to the deterministic closure if the server is
  unreachable or the response is unexpected, so the demo never dies mid-take.
- ✅ **Real entity types, no more dataset stand-ins.** Reports and the model
  used to be seeded as `Dataset`s with a subtype tag. They are now what they
  claim to be:

  | In the bank | DataHub entity | URN |
  |---|---|---|
  | tables | `Dataset` | `urn:li:dataset:(urn:li:dataPlatform:snowflake,<name>,PROD)` |
  | the three dashboards | `Dashboard` | `urn:li:dashboard:(powerbi,<id>)` |
  | the risk model | `MLModel` | `urn:li:mlModel:(urn:li:dataPlatform:mlflow,<name>,PROD)` |
  | each pipeline | `DataFlow` + `DataJob` | `urn:li:dataJob:(urn:li:dataFlow:(airflow,<flow>,PROD),<job>)` |

  Each lineage edge is stored the way DataHub stores it for that pair of types:
  dashboards read datasets through `DashboardInfo.datasetEdges`; jobs read and
  write datasets through `DataJobInputOutput`; the model is linked to jobs
  through `MLModelProperties.trainingJobs` and `.downstreamJobs`. The parser
  decides a node's kind from the entity type in its URN, not from any tag, and
  the write-back sends each assessment to the entity type its URN names
  (`DashboardInfo`, `MLModelProperties`, `DataJob` and `Dataset` aspects).
- ⚠️ **One thing had to change in the graph to make this honest.** DataHub has
  no direct dataset → model edge: a model is reached through the job that
  trains it. So the seed gained a training job (`pipe.risk_model_training`),
  and the blast radius is now 10 assets, not 9. The engine now recognises a
  model and a report by their entity type instead of by name, so the sample
  card's figures moved slightly (recommendation and confidence unchanged).

**Still simplified**
- **Not yet run against a live DataHub.** The seed, the write-back and the
  fake MCP server are checked offline: the real SDK classes build every entity
  and the tests read their URNs, aspects and lineage back, and the response
  shapes come from the `mcp-server-datahub` source, not from a live server. The
  first run against `datahub docker quickstart` is still to do.
- **The seed is thin.** It writes owners, descriptions and (for tables only) a
  schema. It does not seed tags, custom properties, domains or glossary terms;
  the only term in the graph is the one RegLens writes back. Dashboards, the
  model and jobs have no schema (DataHub has none for them), so the model's
  and dashboards' example fields in `graph.py` are not written anywhere.
- **Each pipeline is one flow with one job**, the job named after the flow.
  Real pipelines have many tasks.
- **The write-back replaces the description** on each asset with the
  assessment (on dashboards and the model that is their own description, on
  tables and jobs the human-edited one), as it did before. It does not append.
- **The fallback still reads `graph.py`.** With `--no-mcp` (or if the server
  is down) discovery walks the seeded graph, not DataHub.
- **The cost model is unchanged** and still a set of named assumptions; report
  tables are still recognised by name ("report", "submission", "pack").
- **The MCP mutation helpers in `mcp_client.py` are unused and stale.** Their
  argument names don't match the real `update_description` and
  `add_glossary_terms` tools (`entity_urn`, `term_urns`/`entity_urns`); the agent
  writes back through the SDK, so it is not affected.

> ⚠️ The regulation **RCS-2026** and its issuer are **fictional on purpose**, so RegLens
> makes no claim about real-world regulation.

---

## 📄 License

Apache 2.0 — see [LICENSE](LICENSE).
