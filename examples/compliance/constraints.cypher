CREATE CONSTRAINT demo_compliance_account_id_unique IF NOT EXISTS
FOR (a:DemoComplianceAccount) REQUIRE a.id IS UNIQUE;

