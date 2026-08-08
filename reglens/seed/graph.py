"""Pure graph definition for Northstar Bank — NO external dependencies.

Single source of truth for the fictional bank's assets + lineage. Both the DataHub
seed script (which needs the SDK) and the agent's deterministic fallback (which
must run with nothing installed) import from here.
"""
from __future__ import annotations

PLATFORM = "snowflake"   # overridden at seed time by config.BANK_PLATFORM
ENV = "PROD"

# (short_name, subtype, description, [ (field, type), ... ], owner)
ASSETS = [
    ("retail.customer", "Table", "Retail customer master.",
     [("customer_id", "string"), ("full_name", "string"), ("date_of_birth", "date"),
      ("country", "string"), ("segment", "string")], "retail_analytics"),
    ("corporate.customer_corporate", "Table", "Corporate customer master.",
     [("customer_id", "string"), ("legal_name", "string"), ("industry_code", "string"),
      ("country", "string")], "corporate_banking"),
    ("core.account", "Table", "Account-level balances and product holdings.",
     [("account_id", "string"), ("customer_id", "string"), ("product", "string"),
      ("balance", "number")], "retail_analytics"),
    ("core.transaction", "Table", "Posted transactions across retail and corporate.",
     [("txn_id", "string"), ("account_id", "string"), ("amount", "number"),
      ("counterparty_country", "string"), ("ts", "timestamp")], "retail_analytics"),
    ("risk.customer_kyc", "Table", "KYC attributes used in risk assessment.",
     [("customer_id", "string"), ("pep_flag", "boolean"), ("sanctions_hit", "boolean"),
      ("kyc_review_date", "date")], "risk_data_office"),
    ("risk.risk_factors_reference", "Table", "Reference weights for risk factors.",
     [("factor_code", "string"), ("factor_weight", "number"),
      ("methodology_version", "string")], "risk_data_office"),
    # --- KEY NODE: the regulation lands here ---
    ("risk.customer_risk_profile", "Table",
     "Per-customer risk tier. Directly in scope for RCS-2026.",
     [("customer_id", "string"), ("risk_tier", "string"), ("risk_score", "number"),
      ("methodology_version", "string"), ("scored_at", "timestamp")], "risk_data_office"),
    ("risk.exposure_positions", "Table", "Exposure by customer for capital calc.",
     [("customer_id", "string"), ("exposure_amount", "number"),
      ("asset_class", "string")], "capital_management"),
    ("risk.customer_segmentation", "Table", "Behavioural segmentation inputs.",
     [("customer_id", "string"), ("segment", "string"), ("ltv", "number")],
     "retail_analytics"),
    ("risk.transaction_monitoring_alerts", "Table", "AML/monitoring alerts.",
     [("alert_id", "string"), ("customer_id", "string"), ("severity", "string")],
     "risk_data_office"),
    ("ml.risk_scoring_model", "ML Model",
     "Model that assigns risk tiers. Retrain/revalidate is the expensive part of RCS-2026.",
     [("feature_vector", "string"), ("predicted_tier", "string"),
      ("model_version", "string")], "risk_data_office"),
    ("pipe.risk_scoring_pipeline", "Pipeline",
     "Scores customers nightly using the model.",
     [("run_id", "string"), ("status", "string")], "risk_data_office"),
    ("pipe.regulatory_reporting_pipeline", "Pipeline",
     "Assembles the regulatory risk report.",
     [("run_id", "string"), ("status", "string")], "regulatory_reporting_team"),
    ("pipe.capital_reporting_pipeline", "Pipeline",
     "Feeds the capital adequacy calculation.",
     [("run_id", "string"), ("status", "string")], "capital_management"),
    ("report.regulatory_risk_report", "Table",
     "Regulatory risk report submitted to the supervisor. In scope for RCS-2026.",
     [("report_date", "date"), ("customer_id", "string"), ("risk_tier", "string"),
      ("capital_charge", "number")], "regulatory_reporting_team"),
    ("report.capital_adequacy_input", "Table",
     "Capital adequacy calculation input.",
     [("report_date", "date"), ("rwa", "number"), ("tier1_ratio", "number")],
     "capital_management"),
    ("dash.capital_reporting_dashboard", "Dashboard",
     "Board-level capital reporting dashboard.",
     [("metric", "string"), ("value", "number")], "capital_management"),
    ("dash.risk_committee_report", "Dashboard",
     "Monthly risk committee report.",
     [("metric", "string"), ("value", "number")], "risk_data_office"),
    ("dash.supervisory_submission_pack", "Dashboard",
     "Supervisory submission pack.",
     [("section", "string"), ("content", "string")], "regulatory_reporting_team"),
]

# upstream -> downstream (by short names)
LINEAGE = [
    ("retail.customer", "risk.customer_risk_profile"),
    ("risk.customer_kyc", "risk.customer_risk_profile"),
    ("risk.risk_factors_reference", "risk.customer_risk_profile"),
    ("core.transaction", "risk.customer_risk_profile"),
    ("risk.customer_risk_profile", "ml.risk_scoring_model"),
    ("ml.risk_scoring_model", "pipe.risk_scoring_pipeline"),
    ("pipe.risk_scoring_pipeline", "report.regulatory_risk_report"),
    ("risk.exposure_positions", "report.regulatory_risk_report"),
    ("report.regulatory_risk_report", "pipe.capital_reporting_pipeline"),
    ("pipe.capital_reporting_pipeline", "report.capital_adequacy_input"),
    ("report.capital_adequacy_input", "dash.capital_reporting_dashboard"),
    ("report.regulatory_risk_report", "dash.supervisory_submission_pack"),
    ("risk.customer_risk_profile", "dash.risk_committee_report"),
]

SUBTYPE_TO_ENTITY = {
    "ML Model": "mlModel",
    "Pipeline": "dataFlow",
    "Dashboard": "dashboard",
    "Table": "dataset",
}

NAME_TO_META = {name: (subtype, desc) for name, subtype, desc, _s, _o in ASSETS}


def dataset_urn(name: str, platform: str = PLATFORM) -> str:
    """Standard DataHub dataset URN string — no SDK needed."""
    return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},{ENV})"
