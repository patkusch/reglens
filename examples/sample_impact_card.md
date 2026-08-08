# Impact & Decision Card — RCS-2026

**Enhanced Customer Risk Classification Standard**

- **Impact:** HIGH
- **Deadline:** 12 months
- **Assessed:** 2026-08-08
- **Affected assets:** 9

| Decision | Action | Inaction | Opportunity | Expected total |
|---|--:|--:|--:|--:|
| ACT_NOW | £6,504,000 | £0 | £5,000,000 | **£11,504,000** |
| MINIMUM_COMPLIANCE | £2,395,200 | £840,000 | £1,000,000 | **£4,235,200** |
| DEFER | £780,480 | £4,400,000 | £0 | **£5,180,480** |

## Recommendation: MINIMUM_COMPLIANCE  (confidence 0.53)

MINIMUM_COMPLIANCE has the lowest expected total cost (£4,235,200) vs next-best DEFER (£5,180,480); margin £945,280. Meets the letter via rule patch; full model rebuild scheduled later.

### Affected assets
- `risk.customer_risk_profile` (dataset) — Per-customer risk tier. Directly in scope for RCS-2026.
- `ml.risk_scoring_model` (mlModel) — Model that assigns risk tiers. Retrain/revalidate is the expensive part of RCS-2026.
- `dash.risk_committee_report` (dashboard) — Monthly risk committee report.
- `pipe.risk_scoring_pipeline` (dataFlow) — Scores customers nightly using the model.
- `report.regulatory_risk_report` (dataset) — Regulatory risk report submitted to the supervisor. In scope for RCS-2026.
- `pipe.capital_reporting_pipeline` (dataFlow) — Feeds the capital adequacy calculation.
- `dash.supervisory_submission_pack` (dashboard) — Supervisory submission pack.
- `report.capital_adequacy_input` (dataset) — Capital adequacy calculation input.
- `dash.capital_reporting_dashboard` (dashboard) — Board-level capital reporting dashboard.