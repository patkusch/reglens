# Impact & Decision Card — RCS-2026

**Enhanced Customer Risk Classification Standard**

- **Impact:** HIGH
- **Deadline:** 12 months
- **Assessed:** 2026-09-18
- **Affected assets:** 10

| Decision | Action | Inaction | Opportunity | Expected total |
|---|--:|--:|--:|--:|
| ACT_NOW | £6,420,000 | £0 | £5,000,000 | **£11,420,000** |
| MINIMUM_COMPLIANCE | £2,349,000 | £840,000 | £1,000,000 | **£4,189,000** |
| DEFER | £770,400 | £4,400,000 | £0 | **£5,170,400** |

## Recommendation: MINIMUM_COMPLIANCE  (confidence 0.53)

MINIMUM_COMPLIANCE has the lowest expected total cost (£4,189,000) vs next-best DEFER (£5,170,400); margin £981,400. Meets the letter via rule patch; full model rebuild scheduled later.

### Affected assets
- `risk.customer_risk_profile` (dataset) — Per-customer risk tier. Directly in scope for RCS-2026.
- `pipe.risk_model_training` (dataJob) — Trains and revalidates the risk scoring model on the customer risk profile.
- `dash.risk_committee_report` (dashboard) — Monthly risk committee report.
- `ml.risk_scoring_model` (mlModel) — Model that assigns risk tiers. Retrain/revalidate is the expensive part of RCS-2026.
- `pipe.risk_scoring_pipeline` (dataJob) — Scores customers nightly using the model.
- `report.regulatory_risk_report` (dataset) — Regulatory risk report submitted to the supervisor. In scope for RCS-2026.
- `pipe.capital_reporting_pipeline` (dataJob) — Feeds the capital adequacy calculation.
- `dash.supervisory_submission_pack` (dashboard) — Supervisory submission pack.
- `report.capital_adequacy_input` (dataset) — Capital adequacy calculation input.
- `dash.capital_reporting_dashboard` (dashboard) — Board-level capital reporting dashboard.