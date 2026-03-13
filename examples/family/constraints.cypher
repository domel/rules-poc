CREATE CONSTRAINT demo_family_person_id_unique IF NOT EXISTS
FOR (p:DemoFamilyPerson) REQUIRE p.id IS UNIQUE;

