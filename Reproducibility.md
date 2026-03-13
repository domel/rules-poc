# Reproducibility

This file contains the reproducibility protocol for the evaluation artifact implemented in this directory.

## 1) Scope

The evaluation covers experiments E1-E6 implemented by `scripts/run_evaluation.py` and is executed by:

```bash
PYTHONPATH=src python3 scripts/run_evaluation.py \
  --uri bolt://localhost:7687 \
  --user neo4j \
  --password domeldomel \
  --database neo4j \
  --reports-dir reports \
  --determinism-seeds 10 \
  --scale-sizes 50,100,200 \
  --e6-repeats 10
```

## 2) Environment

### Software

- OS: Linux Mint 21.2 Victoria (base: Ubuntu 22.04 jammy)
- Kernel: `6.8.0-60-generic` (`x86_64`)
- Shell: Bash `5.1.16`
- Python: `3.10`
- Neo4j endpoint: `bolt://localhost:7687`, database `neo4j`

### Hardware (key facts)

- Machine: Intel NUC13ANKi7 (Intel NUC13ANBi7 board)
- CPU: 13th Gen Intel Core i7-1360P, 12 cores (4P + 8E), max turbo up to 5.0/3.7 GHz
- RAM: 62.36 GiB total (as reported by `inxi`)
- Storage: Samsung 990 PRO 1TB NVMe SSD

### Full host snapshot (provided)

- Desktop: Cinnamon 5.8.4
- GPU: Intel i915 (Mesa Intel Graphics RPL-P)
- Network: Intel Ethernet (`enp86s0` up, 100 Mbps full duplex in the captured snapshot)
- Package count: 3536
- Process count in snapshot: 422

## 3) Clean-Start Protocol

Before running E1–E6, the database was reset to an empty state:

1. drop all constraints,
2. drop all non-lookup indexes,
3. `MATCH (n) DETACH DELETE n`.

Post-reset verification:

- `remaining_nodes = 0`
- `remaining_relationships = 0`

This ensures no contamination from prior runs.

## 4) Experiment Parameters

- Determinism seeds (E3): `10` runs (`seed = 0..9`)
- Scaling sizes (E5): `N in {50, 100, 200}`
- Diagnostics overhead repeats (E6): `10`
- Runner mode: fixpoint evaluation with per-round `changes`

## 5) Generated Artifacts (clean rerun)

Main outputs from the clean rerun:

- `reports/evaluation_20260303T190552Z.json`
- `reports/evaluation_20260303T190552Z.md`
- `reports/evaluation_20260303T190552Z_e3_samples.csv`
- `reports/evaluation_20260303T190552Z_e5_scaling.csv`

Per-scenario run reports for E1 are additionally written under:

- `reports/e1/`

These outputs are generated locally during reruns and are not intended to be versioned in the repository by default.

## 5a) Large-Scale E5 Extension (review response)

To address scalability concerns with larger inputs, a dedicated large-scale run is available:

```bash
PYTHONPATH=src python3 scripts/run_large_scale_e5.py \
  --uri bolt://localhost:7687 \
  --user neo4j \
  --password domeldomel \
  --database neo4j \
  --reports-dir reports \
  --chain-sizes 200,400 \
  --tree-sizes 200,400,800,1600,3200
```

Artifacts from the recorded run:

- `reports/evaluation_large_e5_20260303T194537Z.json`
- `reports/evaluation_large_e5_20260303T194537Z.csv`
- `reports/evaluation_large_e5_20260303T194537Z.md`

## 6) Validation Checklist

After execution, verify:

1. `evaluation_*.json` exists and contains sections `e1`..`e6`.
2. `e1.*.pass == true` for `banking`, `family`, `compliance`.
3. `e2.*.second_run_after_fixpoint.total_changes == 0`.
4. `e3.unique_hashes == 1`.
5. `e4` shows:
   - `STRICT` not finished (`strict_error`),
   - `LOG` and `IGNORE` finished.
6. `e5` includes all `(shape, N)` combinations for chain/tree and expected monotonic trend.
