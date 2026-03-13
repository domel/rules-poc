MATCH (:DemoBankingAccount)-[r:SUSPICIOUS_TRANSFER {demo: "banking"}]->(:DemoBankingAccount)
RETURN count(r) AS suspicious_transfer_edges;

MATCH (:DemoBankingAccount)-[t:TRANSFER {txId: "TX-991", demo: "banking"}]->(:DemoBankingAccount)
RETURN count(t) AS tx991_transfer_edges,
       collect(distinct t.sources) AS tx991_sources;

MATCH (p:DemoBankingPerson)
RETURN collect({id: p.id, effective_name: coalesce(p.fullName, p.fullName_auto)}) AS person_names;
