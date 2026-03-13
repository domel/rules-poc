MATCH (:DemoComplianceAccount)-[r:RISK_TRANSFER {demo: "compliance"}]->(:DemoComplianceAccount)
RETURN count(r) AS risk_transfer_edges;

MATCH (:DemoComplianceAccount)-[t:TX {demo: "compliance"}]->(:DemoComplianceAccount)
WHERE t.country_auto = "UNKNOWN"
RETURN count(t) AS country_defaulted_edges;

MATCH (:DemoComplianceAccount)-[r:FREQUENT_RECEIVER {demo: "compliance"}]->(:DemoComplianceAccount)
RETURN count(r) AS frequent_receiver_edges;

