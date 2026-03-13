MATCH (:DemoFamilyPerson)-[r:CHILD_OF {demo: "family"}]->(:DemoFamilyPerson)
RETURN count(r) AS child_of_edges;

MATCH (:DemoFamilyPerson)-[r:DESCENDED_FROM {demo: "family"}]->(:DemoFamilyPerson)
RETURN count(r) AS descended_from_edges;

MATCH (x:DemoFamilyPerson)-[:DESCENDED_FROM {demo: "family"}]->(y:DemoFamilyPerson)
RETURN collect(x.id + "->" + y.id) AS descended_pairs;

