# RegLens

**A regulatory-change *investment decision* agent, built on DataHub.**

Most tools answer *"what does this regulation affect?"* RegLens answers the
question a bank actually has to act on: *"should we implement this now, defer it,
or do the minimum — and what does each cost?"*

It reads a bank's live data environment **through the DataHub MCP server** to
discover what a regulation touches (via lineage), costs three implementation paths
with a transparent scenario engine, and **writes the decision back into DataHub**
so the next person or agent inherits the assessment instead of rediscovering it.

> Built for *Build with DataHub: The Agent Hackathon*. Challenge category:
> **Agents That Do Real Work**.

---

## The 60-second story

```
        RCS-2026 (a new regulation)
                    │
                    ▼
     RegLens searches DataHub + walks lineage        ← MCP READ
                    │
                    ▼
      9 affected assets discovered automatically
      (3 datasets · 1 ML model · 2 pipelines · 3 reports)
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

## Setup runbook

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

### 3. Seed the fictional bank (~22 assets + lineage)
```bash
python -m reglens.seed.seed_northstar
```
Then in the UI, search **`customer_risk_profile`** and open its **downstream
lineage** — you should see the chain out to `capital_reporting_dashboard`. That
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
asset. **That's the money shot.**

---

## How it uses DataHub (for the judges)

| Judging axis | What RegLens does |
|---|---|
| **Use of DataHub** | Reads the context graph through the **MCP server** (search + lineage traversal) to discover impact, then **contributes back** to the graph (glossary term + description on every affected asset). Goes beyond reading metadata. |
| **Technical execution** | Runs end-to-end: seed → discover → cost → approve → write back. Deterministic core path always works; MCP + LLM are layered on top. |
| **Originality** | Not impact analysis — *investment-decision* support. Costs inaction (P × consequence) and opportunity cost of displaced strategic work, not just implementation. |
| **Real-world usefulness** | Change-capacity triage is a real, expensive problem for every regulated bank. |
| **Submission quality** | This README, a <3-min demo ([`demo/demo_script.md`](demo/demo_script.md)), and sample outputs in `examples/`. |

**The write-back is the point.** It maps directly to *"Agents That Do Real Work:
takes action, and writes results back so the next person or agent inherits the
knowledge."*

---

## Architecture

```
reglens/
  seed/
    graph.py            # the fictional bank: ~22 assets + lineage (dependency-free)
    seed_northstar.py   # writes graph.py into DataHub via the SDK
    regulations.py      # RCS-2026 (fictional reg, fictional regulator)
  engine/
    scenario_engine.py  # transparent cost model — every £ has an assumption + confidence
    impact_card.py      # renders the Impact & Decision Card + write-back payload
  agent/
    mcp_client.py       # async wrapper over the DataHub MCP server (stdio via uvx)
    reglens_agent.py    # orchestrator + CLI + human-approval gate
    writeback.py        # reliable SDK write-back path
  models.py             # shared dataclasses
```

### What's real vs. what's a documented shortcut
- **Real:** DataHub graph, MCP read round-trip, scenario engine, SDK write-back,
  human gate.
- **Shortcut (documented, safe to ship):** the MCP lineage result is proven to
  round-trip but parsed via the deterministic closure of the *same* seeded graph —
  so the card is always populated. Tightening that parse against your MCP server's
  result shape is the first `TODO`. Reports/pipelines/model are seeded as datasets
  with subtypes for uniform lineage; promoting them to real `Dashboard`/`MLModel`
  entities is an optional upgrade, also marked `TODO`.

The regulation **RCS-2026** and its issuer are **fictional on purpose**, so RegLens
makes no claim about real-world regulation.

---

## License
Apache 2.0 — see [LICENSE](LICENSE).
