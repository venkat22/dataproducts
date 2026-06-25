"""Seed the database with realistic demo data products and contracts."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, init_db
import models

PRODUCTS = [
    {
        "name": "Daily Dealer Sales Analytics",
        "description": "Comprehensive daily sales performance data across all dealer channels. Sourced from SAP S/4HANA and Salesforce CRM. Covers order volumes, revenue by dealer tier, regional breakdowns, and YoY comparisons. Refreshed by 6am daily for morning dashboards.",
        "domain": "Sales",
        "owner_name": "Aisling O'Malley",
        "owner_email": "aisling.omalley@vertiv.com",
        "classification": "Internal",
        "source_systems": "SAP S/4HANA, Salesforce CRM",
        "update_frequency": "Daily",
        "output_format": "Table",
        "sla": "99.9% availability, refreshed by 6am daily",
        "contains_pii": False,
        "tags": "sales,dealer,daily,revenue,orders",
    },
    {
        "name": "Customer 360 Profile",
        "description": "Unified customer view aggregating CRM, support tickets, purchase history, and contract data. Contains full customer contact details, firmographic attributes, and engagement scores. Used by Sales, Marketing, and Customer Success teams for personalised outreach and churn risk scoring.",
        "domain": "Marketing",
        "owner_name": "Marcus Chen",
        "owner_email": "marcus.chen@vertiv.com",
        "classification": "Confidential",
        "source_systems": "Salesforce CRM, ServiceNow, SAP ERP",
        "update_frequency": "Hourly",
        "output_format": "View",
        "sla": "99.5% availability, max latency 30 min",
        "contains_pii": True,
        "tags": "customer,crm,360,pii,churn,engagement",
    },
    {
        "name": "Finance GL & P&L Summary",
        "description": "General Ledger transactions and Profit & Loss summaries aggregated at cost-centre and business-unit level. Sourced from SAP FICO. Used for monthly management reporting, variance analysis, and regulatory submissions. Data is locked at month-end close.",
        "domain": "Finance",
        "owner_name": "Roberta Walsh",
        "owner_email": "roberta.walsh@vertiv.com",
        "classification": "Restricted",
        "source_systems": "SAP FICO, Oracle EPM",
        "update_frequency": "Daily",
        "output_format": "Table",
        "sla": "99.9% availability, month-end lock within 3 business days",
        "contains_pii": False,
        "tags": "finance,gl,pnl,reporting,restricted",
    },
    {
        "name": "Supply Chain Inventory & Demand Forecast",
        "description": "Real-time inventory levels across all warehouses combined with 90-day demand forecast from the ML forecasting engine. Covers SKU-level stock positions, reorder points, and supply risk indicators. Critical for procurement planning and avoiding stock-outs.",
        "domain": "Supply Chain",
        "owner_name": "Priya Nair",
        "owner_email": "priya.nair@vertiv.com",
        "classification": "Internal",
        "source_systems": "SAP SCM, Blue Yonder, Oracle WMS",
        "update_frequency": "Hourly",
        "output_format": "Table",
        "sla": "99.9% availability, max 15 min lag",
        "contains_pii": False,
        "tags": "supply-chain,inventory,forecast,procurement,sku",
    },
    {
        "name": "HR Workforce Analytics",
        "description": "Headcount, attrition, hiring pipeline, and compensation band data aggregated from Workday HCM. Covers active employees, contractors, and open requisitions. Used by HR Business Partners and senior leadership for workforce planning. Contains sensitive personal data.",
        "domain": "Human Resources",
        "owner_name": "James Thornton",
        "owner_email": "james.thornton@vertiv.com",
        "classification": "Restricted",
        "source_systems": "Workday HCM, SAP SuccessFactors",
        "update_frequency": "Daily",
        "output_format": "Dashboard",
        "sla": "99% availability, refreshed overnight",
        "contains_pii": True,
        "tags": "hr,workforce,headcount,attrition,pii,hiring",
    },
    {
        "name": "Marketing Campaign Performance",
        "description": "End-to-end campaign attribution data spanning email, paid search, display, and events channels. Tracks impressions, clicks, MQL conversions, and pipeline influenced. Integrates with Salesforce for closed-loop revenue attribution. Refreshed every 4 hours.",
        "domain": "Marketing",
        "owner_name": "Sofia Ramos",
        "owner_email": "sofia.ramos@vertiv.com",
        "classification": "Internal",
        "source_systems": "Salesforce Marketing Cloud, Google Analytics, HubSpot",
        "update_frequency": "Hourly",
        "output_format": "Dashboard",
        "sla": "98% availability, 4-hour refresh cycle",
        "contains_pii": False,
        "tags": "marketing,campaigns,attribution,pipeline,mql",
    },
    {
        "name": "Product Quality & Warranty Claims",
        "description": "Field failure reports, warranty claims, and NFF (no-fault-found) rates by product family and manufacturing plant. Sourced from ServiceNow field service module and SAP QM. Used by engineering and quality teams to drive continuous improvement initiatives.",
        "domain": "Manufacturing",
        "owner_name": "Lars Eriksson",
        "owner_email": "lars.eriksson@vertiv.com",
        "classification": "Internal",
        "source_systems": "ServiceNow, SAP QM, Siemens MES",
        "update_frequency": "Daily",
        "output_format": "Table",
        "sla": "99% availability, daily refresh by 7am",
        "contains_pii": False,
        "tags": "quality,warranty,manufacturing,field-service,nff",
    },
    {
        "name": "Pricing & Quote Analytics",
        "description": "Quote-to-order conversion rates, discount approval chains, and win/loss analysis by product line and region. Sources from CPQ tool and Salesforce Opportunities. Enables pricing strategy teams to identify margin leakage and optimise discount guardrails.",
        "domain": "Sales",
        "owner_name": "Aisling O'Malley",
        "owner_email": "aisling.omalley@vertiv.com",
        "classification": "Confidential",
        "source_systems": "Salesforce CPQ, SAP SD",
        "update_frequency": "Daily",
        "output_format": "Table",
        "sla": "99% availability, refreshed by 8am",
        "contains_pii": False,
        "tags": "pricing,quotes,margin,discounts,sales",
    },
    {
        "name": "IoT Sensor & Asset Telemetry",
        "description": "Real-time telemetry stream from connected UPS and thermal management assets in customer data centres. Covers temperature, power draw, battery state-of-health, and alert events. Powers predictive maintenance models and Vertiv's remote monitoring service.",
        "domain": "Manufacturing",
        "owner_name": "Kaveh Rostami",
        "owner_email": "kaveh.rostami@vertiv.com",
        "classification": "Internal",
        "source_systems": "Vertiv Liebert IntelliSlot, AWS IoT Core",
        "update_frequency": "Realtime",
        "output_format": "Stream",
        "sla": "99.95% availability, sub-60s latency",
        "contains_pii": False,
        "tags": "iot,telemetry,assets,predictive-maintenance,realtime",
    },
    {
        "name": "Net Revenue Retention (NRR) Dashboard",
        "description": "Monthly NRR, GRR, expansion, contraction, and churn metrics segmented by customer tier, product line, and geography. Sourced from Salesforce and the billing system. The single source of truth for investor reporting and board-level KPIs.",
        "domain": "Finance",
        "owner_name": "Roberta Walsh",
        "owner_email": "roberta.walsh@vertiv.com",
        "classification": "Restricted",
        "source_systems": "Salesforce, Zuora Billing, SAP FICO",
        "update_frequency": "Monthly",
        "output_format": "Dashboard",
        "sla": "99.9% availability, published within 5 business days of month close",
        "contains_pii": False,
        "tags": "nrr,retention,churn,kpi,board,finance",
    },
]

CONTRACTS = {
    "Daily Dealer Sales Analytics": {
        "version": "2.1.0",
        "status": "active",
        "schema_fields": [
            {"name": "dealer_id", "type": "string", "required": True, "pii": False, "description": "Unique dealer identifier"},
            {"name": "dealer_name", "type": "string", "required": True, "pii": False, "description": "Legal name of the dealer"},
            {"name": "region", "type": "string", "required": True, "pii": False, "description": "Sales region code"},
            {"name": "order_date", "type": "date", "required": True, "pii": False, "description": "Date of order placement"},
            {"name": "order_value_usd", "type": "number", "required": True, "pii": False, "description": "Net order value in USD"},
            {"name": "product_family", "type": "string", "required": False, "pii": False, "description": "Vertiv product family"},
            {"name": "units_ordered", "type": "integer", "required": True, "pii": False, "description": "Number of units"},
        ],
        "quality_rules": [
            {"field": "dealer_id", "rule": "not_null", "description": "Dealer ID must always be present"},
            {"field": "dealer_id", "rule": "unique", "description": "One row per dealer per day"},
            {"field": "order_value_usd", "rule": "range", "description": "Must be > 0"},
            {"field": "order_date", "rule": "freshness", "description": "Latest partition must be within 24 hours"},
        ],
        "slo_availability": "99.9%",
        "slo_freshness": "Refreshed by 6am daily",
        "slo_max_latency": "",
    },
    "Customer 360 Profile": {
        "version": "1.3.0",
        "status": "active",
        "schema_fields": [
            {"name": "customer_id", "type": "string", "required": True, "pii": False, "description": "Salesforce Account ID"},
            {"name": "customer_name", "type": "string", "required": True, "pii": True, "description": "Legal company name"},
            {"name": "contact_email", "type": "string", "required": False, "pii": True, "description": "Primary contact email"},
            {"name": "contact_phone", "type": "string", "required": False, "pii": True, "description": "Primary contact phone"},
            {"name": "industry", "type": "string", "required": False, "pii": False, "description": "Industry vertical"},
            {"name": "churn_risk_score", "type": "number", "required": False, "pii": False, "description": "ML churn probability 0-1"},
            {"name": "last_engagement_date", "type": "date", "required": False, "pii": False, "description": "Last CRM activity date"},
        ],
        "quality_rules": [
            {"field": "customer_id", "rule": "not_null", "description": "Every row must have a customer ID"},
            {"field": "customer_id", "rule": "unique", "description": "One profile per customer"},
            {"field": "churn_risk_score", "rule": "range", "description": "Score must be between 0 and 1"},
        ],
        "slo_availability": "99.5%",
        "slo_freshness": "Updated hourly, max 30 min lag",
        "slo_max_latency": "< 500ms p95",
    },
    "IoT Sensor & Asset Telemetry": {
        "version": "3.0.0",
        "status": "active",
        "schema_fields": [
            {"name": "asset_id", "type": "string", "required": True, "pii": False, "description": "Unique asset identifier"},
            {"name": "event_timestamp", "type": "timestamp", "required": True, "pii": False, "description": "UTC event time"},
            {"name": "temperature_c", "type": "number", "required": False, "pii": False, "description": "Inlet temperature °C"},
            {"name": "power_kw", "type": "number", "required": False, "pii": False, "description": "Current power draw kW"},
            {"name": "battery_health_pct", "type": "integer", "required": False, "pii": False, "description": "Battery state of health 0-100"},
            {"name": "alert_code", "type": "string", "required": False, "pii": False, "description": "Alert event code, null if healthy"},
        ],
        "quality_rules": [
            {"field": "asset_id", "rule": "not_null", "description": "Asset ID required on every event"},
            {"field": "event_timestamp", "rule": "freshness", "description": "Events must arrive within 60 seconds"},
            {"field": "battery_health_pct", "rule": "range", "description": "Must be 0-100"},
        ],
        "slo_availability": "99.95%",
        "slo_freshness": "Sub-60 second latency",
        "slo_max_latency": "< 60s end-to-end",
    },
}

def seed():
    init_db()
    db = SessionLocal()
    try:
        # Clear existing data
        db.query(models.DataContract).delete()
        db.query(models.DataProduct).delete()
        db.commit()
        print("Cleared existing data.")

        # Insert products
        created = {}
        for data in PRODUCTS:
            p = models.DataProduct(**data)
            db.add(p)
            db.flush()
            created[data["name"]] = p.id
            print(f"  + {data['name']} (id={p.id})")

        db.commit()

        # Insert contracts
        for product_name, contract_data in CONTRACTS.items():
            pid = created.get(product_name)
            if not pid:
                continue

            cd = dict(contract_data)  # shallow copy so pop doesn't mutate original
            schema_fields = cd.pop("schema_fields")
            quality_rules = cd.pop("quality_rules")

            c = models.DataContract(
                product_id=pid,
                schema_fields=schema_fields,   # plain list of dicts → JSON column
                quality_rules=quality_rules,
                **cd,
            )
            db.add(c)
            print(f"    ✓ contract for '{product_name}'")

        db.commit()
        print(f"\n✅ Seeded {len(PRODUCTS)} products, {len(CONTRACTS)} contracts.")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
