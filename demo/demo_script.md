# RegLens — 3-minute demo shot list

Under 3:00. Judges may stop watching at 3:00, so the write-back (the payoff) must
land by ~2:30. Record in two takes and cut together; use `--no-mcp` for the live
agent run so nothing can fail on camera, and show the *real* MCP tool list once
(step 4) to prove the integration.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:20 | Title card, then DataHub UI showing Northstar's graph | "A mid-size bank gets a new regulation, RCS-2026. Someone has to decide: implement now, defer, or do the minimum. Today that's a room full of people guessing." |
| 0:20–0:45 | `customer_risk_profile` in DataHub, expand downstream lineage | "Nobody has the full picture of what it touches. But DataHub does — the lineage is right here." |
| 0:45–1:15 | Terminal: `python -m reglens.agent.mcp_client` (tool list), then run the agent | "RegLens reads that graph through DataHub's MCP server and finds the blast radius automatically — 9 assets, including the risk-scoring model." |
| 1:15–1:50 | The Impact & Decision Card in the terminal | "Then it costs three paths. Not just build cost — the cost of *inaction*, probability times consequence, and the opportunity cost of the strategic programme this would displace. Every number shows its assumption and a confidence." |
| 1:50–2:15 | The recommendation + human approval prompt | "It recommends minimum compliance now — cheaper expected total than deferring or going all-in — and a human approves." |
| 2:15–2:45 | Refresh `customer_risk_profile` in DataHub: glossary term + description now present | "And here's the part that matters: it writes the decision back into DataHub. The next person to open this asset inherits the whole assessment." |
| 2:45–3:00 | Title card | "RegLens. The regulation tells you what's changing. DataHub tells you what it hits. RegLens tells you what to do about it — and remembers." |

## Recording tips
- Pre-seed the graph and pre-generate a PAT before recording.
- Increase terminal font size; the card should be readable at 1080p.
- Keep the DataHub tab and the terminal side by side for the write-back reveal.
- No copyrighted music. Silence or a royalty-free bed only.
