MATCH (n:DemoModeInput)
DETACH DELETE n;

CREATE (:DemoModeInput {demo: "mode_robustness", id: "bad", den: 0});

