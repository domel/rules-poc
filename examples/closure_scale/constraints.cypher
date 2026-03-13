CREATE CONSTRAINT demo_scale_node_id_unique IF NOT EXISTS
FOR (n:DemoScaleNode) REQUIRE n.id IS UNIQUE;

