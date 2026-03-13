MATCH (n:DemoBankingAccount)
DETACH DELETE n;

MATCH (n:DemoBankingPerson)
DETACH DELETE n;

MERGE (a1:DemoBankingAccount {id: "A1"})
SET a1.owner = "Alice";

MERGE (b7:DemoBankingAccount {id: "B7"})
SET b7.owner = "Bob";

MERGE (c2:DemoBankingAccount {id: "C2"})
SET c2.owner = "Charlie";

MATCH (a1:DemoBankingAccount {id: "A1"}), (b7:DemoBankingAccount {id: "B7"})
MERGE (a1)-[t1:TRANSFER {txId: "TX-991", demo: "banking"}]->(b7)
SET t1.currency = "EUR",
    t1.amount = 15000;

MATCH (a1:DemoBankingAccount {id: "A1"}), (c2:DemoBankingAccount {id: "C2"})
MERGE (a1)-[t2:TRANSFER {txId: "TX-992", demo: "banking"}]->(c2)
SET t2.currency = "USD",
    t2.amount = 700;

MERGE (p1:DemoBankingPerson {id: "P1"})
SET p1.fullName = "Alice Johnson";

MERGE (p2:DemoBankingPerson {id: "P2"})
SET p2.fullName = null;
