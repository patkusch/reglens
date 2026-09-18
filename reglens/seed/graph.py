"""Pure graph definition for Northstar Bank — NO external dependencies.

Single source of truth for the fictional bank's assets + lineage. Both the DataHub
seed script (which needs the SDK) and the agent's deterministic fallback (which
must run with nothing installed) import from here.

Every asset is a real DataHub entity of its own type, with the URN DataHub uses
for that type:

    Table     -> dataset    urn:li:dataset:(urn:li:dataPlatform:<p>,<name>,<env>)
    Dashboard -> dashboard  urn:li:dashboard:(<tool>,<id>)
    ML Model  -> mlModel    urn:li:mlModel:(urn:li:dataPlatform:<p>,<name>,<env>)
    Pipeline  -> dataJob    urn:li:dataJob:(urn:li:dataFlow:(<orchestrator>,<flow>,<env>),<job>)

A pipeline is one DataFlow holding one DataJob. Lineage in DataHub runs through
the DataJob (a DataFlow has no lineage of its own), so the DataJob is the node
that shows up in a lineage walk.
"""
from __future__ import annotations

from reglens.config import BANK_ENV, BANK_PLATFORM

PLATFORM = BANK_PLATFORM      # the platform the datasets are seeded under
ENV = BANK_ENV
DASHBOARD_TOOL = "powerbi"    # the BI tool the dashboards live in
MODEL_PLATFORM = "mlflow"     # the model registry the ML model lives in
ORCHESTRATOR = "airflow"      # the scheduler the pipelines run in

# (short_name, kind, description, [ (field, type), ... ], owner)
#
# `kind` is the label used only to decide which DataHub entity type to create.
# Fields are seeded as a schema for Tables only; DataHub's Dashboard, MLModel and
# DataJob entities have no schema aspect, so theirs are not written anywhere.
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
    ("pipe.risk_model_training", "Pipeline",
     "Trains and revalidates the risk scoring model on the customer risk profile.",
     [("run_id", "string"), ("status", "string")], "risk_data_office"),
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
    ("risk.customer_risk_profile", "pipe.risk_model_training"),
    ("pipe.risk_model_training", "ml.risk_scoring_model"),
    ("ml.risk_scoring_model", "pipe.risk_scoring_pipeline"),
    ("pipe.risk_scoring_pipeline", "report.regulatory_risk_report"),
    ("risk.exposure_positions", "report.regulatory_risk_report"),
    ("report.regulatory_risk_report", "pipe.capital_reporting_pipeline"),
    ("pipe.capital_reporting_pipeline", "report.capital_adequacy_input"),
    ("report.capital_adequacy_input", "dash.capital_reporting_dashboard"),
    ("report.regulatory_risk_report", "dash.supervisory_submission_pack"),
    ("risk.customer_risk_profile", "dash.risk_committee_report"),
]

KIND_TO_ENTITY = {
    "Table": "dataset",
    "Dashboard": "dashboard",
    "ML Model": "mlModel",
    "Pipeline": "dataJob",
}

# The lineage edges DataHub can actually store, as (upstream type, downstream type).
# Checked against the SDK's lineage handlers and the relationship annotations on
# the metadata aspects:
#   dataset  -> dataset    UpstreamLineage
#   dataset  -> dataJob    DataJobInputOutput.inputDatasets
#   dataJob  -> dataset    DataJobInputOutput.outputDatasets
#   dataJob  -> mlModel    MLModelProperties.trainingJobs   (TrainedBy)
#   mlModel  -> dataJob    MLModelProperties.downstreamJobs (UsedBy)
#   dataset  -> dashboard  DashboardInfo.datasetEdges       (Consumes)
#   dataset  -> chart      ChartInfo.inputEdges                (Consumes)
#   chart    -> dashboard  DashboardInfo.chartEdges         (Contains)
# There is no dataset -> mlModel edge and no dataJob -> dashboard edge: a model is
# always reached through the job that trains it and left through the job that
# uses it.
DATAHUB_LINEAGE_EDGES = {
    ("dataset", "dataset"),
    ("dataset", "dataJob"),
    ("dataJob", "dataset"),
    ("dataJob", "mlModel"),
    ("mlModel", "dataJob"),
    ("dataset", "dashboard"),
    ("dataset", "chart"),
    ("chart", "dashboard"),
}

NAME_TO_META = {name: (kind, desc) for name, kind, desc, _s, _o in ASSETS}


def entity_type_of(name: str) -> str:
    """The DataHub entity type of a seeded asset (dataset, dashboard, mlModel, dataJob)."""
    kind, _desc = NAME_TO_META.get(name, ("Table", ""))
    return KIND_TO_ENTITY[kind]


def dataset_urn(name: str, platform: str | None = None) -> str:
    """Standard DataHub dataset URN string — no SDK needed."""
    return f"urn:li:dataset:(urn:li:dataPlatform:{platform or PLATFORM},{name},{ENV})"


def dashboard_urn(name: str, tool: str | None = None) -> str:
    return f"urn:li:dashboard:({tool or DASHBOARD_TOOL},{name})"


def ml_model_urn(name: str, platform: str | None = None) -> str:
    return f"urn:li:mlModel:(urn:li:dataPlatform:{platform or MODEL_PLATFORM},{name},{ENV})"


def data_flow_urn(name: str, orchestrator: str | None = None) -> str:
    return f"urn:li:dataFlow:({orchestrator or ORCHESTRATOR},{name},{ENV})"


def data_job_urn(name: str, orchestrator: str | None = None) -> str:
    """A pipeline's single DataJob: same id as its DataFlow."""
    return f"urn:li:dataJob:({data_flow_urn(name, orchestrator)},{name})"


def urn_for(name: str) -> str:
    """The URN DataHub uses for this seeded asset, by its entity type."""
    return {
        "dataset": dataset_urn,
        "dashboard": dashboard_urn,
        "mlModel": ml_model_urn,
        "dataJob": data_job_urn,
    }[entity_type_of(name)](name)
