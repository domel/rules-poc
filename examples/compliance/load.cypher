MATCH (n:DemoComplianceAccount)
DETACH DELETE n;

MERGE (a1:DemoComplianceAccount {id: "A1"})
SET a1.owner = "Alice";

MERGE (b1:DemoComplianceAccount {id: "B1"})
SET b1.owner = "Bob";

MERGE (c1:DemoComplianceAccount {id: "C1"})
SET c1.owner = "Carol";

MATCH (a1:DemoComplianceAccount {id: "A1"}), (b1:DemoComplianceAccount {id: "B1"})
MERGE (a1)-[t1:TX {txId: "CTX-001", demo: "compliance"}]->(b1)
SET t1.amount = 12000,
    t1.country = "PL";

MATCH (a1:DemoComplianceAccount {id: "A1"}), (b1:DemoComplianceAccount {id: "B1"})
MERGE (a1)-[t2:TX {txId: "CTX-002", demo: "compliance"}]->(b1)
SET t2.amount = 15000,
    t2.country = "PL";

MATCH (a1:DemoComplianceAccount {id: "A1"}), (c1:DemoComplianceAccount {id: "C1"})
MERGE (a1)-[t3:TX {txId: "CTX-003", demo: "compliance"}]->(c1)
SET t3.amount = 4000,
    t3.country = null;

