MATCH (n:DemoFamilyPerson)
DETACH DELETE n;

MERGE (ann:DemoFamilyPerson {id: "ANN"})
SET ann.name = "Ann";

MERGE (bob:DemoFamilyPerson {id: "BOB"})
SET bob.name = "Bob";

MERGE (cara:DemoFamilyPerson {id: "CARA"})
SET cara.name = "Cara";

MERGE (dan:DemoFamilyPerson {id: "DAN"})
SET dan.name = "Dan";

MATCH (ann:DemoFamilyPerson {id: "ANN"}), (bob:DemoFamilyPerson {id: "BOB"})
MERGE (ann)-[:PARENT_OF {demo: "family"}]->(bob);

MATCH (bob:DemoFamilyPerson {id: "BOB"}), (cara:DemoFamilyPerson {id: "CARA"})
MERGE (bob)-[:PARENT_OF {demo: "family"}]->(cara);

MATCH (ann:DemoFamilyPerson {id: "ANN"}), (dan:DemoFamilyPerson {id: "DAN"})
MERGE (ann)-[:PARENT_OF {demo: "family"}]->(dan);

