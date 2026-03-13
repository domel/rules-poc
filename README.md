# gqlrules - wrapper-only GQL Rules runner for Neo4j (Python 3.10)

## 1. What this is

`gqlrules` is a lightweight proof-of-concept runner for the GQL Rules project. It:

- parses `.gqlr` rule-program files (rule headers, `MODE`, `BODY`/`HEAD` blocks),
- does **not** parse the inner Cypher itself (wrapper-only design),
- concatenates `BODY + HEAD` into executable Cypher statements,
- runs rules iteratively until a **fixpoint** is reached (no further changes),
- writes execution metrics to JSON and, optionally, CSV.

This PoC is optimized for a **locally running Neo4j** instance available at:

- Neo4j Browser: `http://localhost:7474`
- Bolt: `bolt://localhost:7687`

Docker is intentionally not used in this artifact.

---

## 2. Scope and current limitations

- The parser is **wrapper-only**: it understands the outer `.gqlr` structure, but it does not parse or validate the Cypher inside `BODY` and `HEAD`.
- In v0.1, each rule is expected to end with:

```text
RETURN <int> AS changes
```

  This is required to detect whether a fixpoint has been reached.
- The artifact is intended for **local Neo4j execution** and research reproducibility, not as a production-grade rule engine.

---

## 3. Requirements

- Python **3.10** or newer
- Neo4j (Desktop or Server) running locally
- Python package `neo4j` (installed from the project dependencies)
- (optional) APOC, if your rules call `apoc.*`

---

## 4. Local Neo4j setup

1. Make sure Neo4j is running and the Browser is available at:
   - `http://localhost:7474`

2. Make sure Bolt is available at:
   - `bolt://localhost:7687`

3. Make sure you know:
   - the username (usually `neo4j`)
   - the password configured in Neo4j Desktop/Server

If you use APOC, enable the relevant APOC settings in your Neo4j installation. In Neo4j Desktop this is usually handled through the `Plugins` panel.

---

## 5. Installation (development mode)

Run the following commands from the `implementation-PoC/` directory:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[dev]
```

If you do not need the development extras, use:

```bash
pip install -e .
```

The package installs the CLI entry point:

```bash
gqlr --help
```

If you do not install the package, you can still run the CLI with:

```bash
PYTHONPATH=src python3 -m gqlrules.cli --help
```

---

## 6. Environment variables

It is recommended to use environment variables instead of passing credentials on the command line:

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="YourPassword"
export NEO4J_DATABASE="neo4j"
```

On Windows PowerShell:

```powershell
$env:NEO4J_URI="bolt://localhost:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="YourPassword"
$env:NEO4J_DATABASE="neo4j"
```

CLI defaults in the current PoC implementation are:

- `--uri bolt://localhost:7687`
- `--user neo4j`
- `--password domeldomel`
- `--database neo4j`

The password default is only a convenience fallback in the research artifact. In any real setup, override it explicitly.

---

## 7. `.gqlr` format (v0.1)

Minimal example:

```text
RULE suspiciousTransfers MODE LOG {
  BODY:
    MATCH (a:Account)-[t:TRANSFER]->(b:Account)
    WHERE t.amount > 10000
  HEAD:
    MERGE (t)-[:HAS_FLAG]->(:Flag {name:"SUSPICIOUS"})
    RETURN count(*) AS changes
}
```

Important notes:

- the outer wrapper (`RULE`, `MODE`, `BODY`, `HEAD`) is parsed by the PoC,
- the Cypher inside `BODY` and `HEAD` is passed through as text,
- each rule must end with `RETURN ... AS changes`.

---

## 8. CLI usage

### 8.1 Parse

Print the parsed AST as JSON:

```bash
gqlr parse examples/banking/program.gqlr
```

### 8.2 Compile

Generate `.cypher` artifacts and a manifest:

```bash
gqlr compile examples/banking/program.gqlr --out out/
```

### 8.3 Run

Execute the program to fixpoint and write a report:

```bash
gqlr run examples/banking/program.gqlr --reports-dir reports/
```

Optional useful flags:

- `--csv` to also write a per-rule CSV report
- `--max-rounds <N>` to bound the fixpoint loop
- `--shuffle --seed <N>` to perturb rule order for determinism checks

If you do not use environment variables:

```bash
gqlr run examples/banking/program.gqlr \
  --uri bolt://localhost:7687 \
  --user neo4j \
  --password "domeldomel" \
  --database neo4j
```

### 8.4 Demo

Run a bundled end-to-end scenario:

```bash
gqlr demo banking
```

Documented demo scenarios:

- `banking` - transfers, flagging rules, and defaults
- `family` - derived family relations and transitive closure
- `compliance` - high-value events, default metadata, and frequent-recipient patterns

Examples:

```bash
gqlr demo family
gqlr demo compliance
```

Without installing the package:

```bash
PYTHONPATH=src python3 -m gqlrules.cli demo banking
```

By default, a demo run will:

- execute `examples/<demo>/constraints.cypher` if present,
- execute `examples/<demo>/load.cypher` if present,
- run the rules to fixpoint,
- execute `examples/<demo>/postconditions.cypher` if present,
- write reports under `reports/`.

---

## 9. Bundled examples

The `examples/` directory contains:

- `banking/`, `family/`, `compliance/` - main end-to-end demo scenarios
- `minimal/` - small parser/compiler examples, including invalid inputs
- `mode_robustness/` - examples for `STRICT`, `LOG`, and `IGNORE`
- `closure_scale/` - synthetic recursive-closure input used in evaluation

---

## 10. Reports

After `run` (and also after `demo`), the PoC writes:

- `reports/<run_id>.json`
- `reports/<run_id>.csv` if `--csv` is enabled

Reports include, among other things:

- number of rounds,
- per-round timing,
- per-rule changes,
- termination status,
- errors or diagnostics reflected by the chosen `MODE`.

The `out/` and `reports/` directories are generated locally and are intentionally excluded from version control.

---

## 11. MODE behavior

- `IGNORE`: rule errors do not stop execution; the failing rule contributes `changes=0`
- `LOG`: same continuation behavior as `IGNORE`, but the report contains fuller error information
- `STRICT`: the first rule error aborts the whole run

---

## 12. Reproducibility and evaluation scripts

This directory also contains the scripts used for the evaluation artifact described in the paper:

- `scripts/run_evaluation.py`
- `scripts/run_large_scale_e5.py`

They can be run without package installation via:

```bash
PYTHONPATH=src python3 scripts/run_evaluation.py --help
PYTHONPATH=src python3 scripts/run_large_scale_e5.py --help
```

For the exact evaluation protocol, expected inputs, and generated artifacts, see [Reproducibility.md](./Reproducibility.md).

---

## 13. Tests

Unit tests:

```bash
pytest -q
```

Integration tests require a live Neo4j instance and the following environment variables:

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- optionally `NEO4J_DATABASE`

Example:

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="domeldomel"
export NEO4J_DATABASE="neo4j"
pytest -q -m integration
```

---

## 14. Troubleshooting

### Cannot connect to Neo4j

- check that Neo4j is running,
- check that Browser works on port `7474`,
- check that Bolt works on port `7687`,
- check username, password, and database name.

### A rule does not return `changes`

Add:

```text
RETURN ... AS changes
```

at the end of the rule head.

### APOC is unavailable

- enable the APOC plugin in Neo4j, or
- remove or rewrite the parts of your rules that call `apoc.*`.

---

## 15. Status

This is a research PoC / artifact with a deliberately simple execution model (wrapper-only).
The next natural development step is manual stratification and, optionally, hybrid dependency analysis.
