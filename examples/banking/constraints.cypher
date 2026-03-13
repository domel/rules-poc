CREATE CONSTRAINT demo_account_id_unique IF NOT EXISTS
FOR (a:DemoBankingAccount) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT demo_person_id_unique IF NOT EXISTS
FOR (p:DemoBankingPerson) REQUIRE p.id IS UNIQUE;
