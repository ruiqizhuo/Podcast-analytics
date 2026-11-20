# Podcast Analytics — Live API Pipeline, Snowflake Star Schema and Neo4j Graph

Cloud Native Data Engineering, Assignment 3. Domain: podcast hosting plus creator-side subscription and retention analytics
(same domain as Assignments 1 and 2). Warehouse: Snowflake. NoSQL: Neo4j Aura Free.

## Layout

| Path | Purpose |
|---|---|
| `pipeline/01_ingest_api.py` | Live API ingestion (Apple RSS charts + iTunes Lookup): paging by id batches, retries and rate limiting, 6 quality checks, Bronze JSON lines |
| `pipeline/build_normalization.py` | Assignment 2 flat table -> 11 normalized tables (Assignment 2 rules) |
| `pipeline/02_silver.py` | Bronze -> Silver: clean, quarantine failed rows, join API and A2 data, **PII masking** (HMAC-SHA256, salt from `PII_SALT`) |
| `pipeline/03_gold.py` | Gold: 3 summary tables (category overview, plan retention, category retention vs API chart coverage) |
| `pipeline/04_star_schema.py` | Star schema (2 facts, 5 dimensions, simulated SCD2 on `dim_creator`) + integrity checks |
| `pipeline/05_load_snowflake.py` | Create Snowflake objects, PUT + COPY INTO, row-count and Gold-view checks |
| `pipeline/06_run_queries.py` | Run SQL files with Snowflake's own metrics (result cache off, repeated runs, medians) |
| `pipeline/07_load_neo4j.py` | Load the graph into Neo4j Aura (constraints, MERGE, count checks) |
| `pipeline/08_run_cypher.py` | Run the Cypher queries |
| `pipeline/probe_apis.py` | Early probe of candidate APIs (offset test) |
| `pipeline/seed/genre_to_a2_top_category.csv` | Hand-made genre -> category mapping (a manual judgment) |
| `sql/warehouse_script.sql` | **Single warehouse script**: DDL, load statements, Q1-Q5, Q5 optimization, Part 4a queries (generated from the other files in `sql/`) |
| `cypher/neo4j_script.cypher` | **Single Neo4j script**: constraints, load statements, all six Cypher queries (generated from `cypher/01_queries.cypher`) |
| `report/build_report.py`, `report/build_deliverable_scripts.py` | Build the Word report and the two single-file scripts |
| `report/Ruiqi_Zhuo_Assignment3_Report.docx` | The submitted written report (Word) |
| `docs/screenshots/` | Screenshots and the ER figure used in the report |
| `logs/` | Evidence of the runs: live API log, quality-check report, query metrics |
| `data/` | Generated locally and **not** committed (the raw Assignment 2 flat table holds synthetic but unmasked names and e-mails) |

## Run order (as used in this project)

```bash
pip install -r requirements.txt
python pipeline/01_ingest_api.py                 # live API pull -> data/bronze, logs/
python pipeline/build_normalization.py           # needs the Assignment 2 flat table (seed 42)
python pipeline/02_silver.py                     # needs PII_SALT
python pipeline/03_gold.py
python pipeline/04_star_schema.py
python pipeline/05_load_snowflake.py             # needs SNOWFLAKE_*
python pipeline/06_run_queries.py --file sql/04_part4a_queries.sql --label part4a
python pipeline/07_load_neo4j.py                 # needs NEO4J_*
python pipeline/08_run_cypher.py
python report/build_deliverable_scripts.py       # regenerates the two single-file scripts
```

The flat dataset comes from the Assignment 2 generator (`generate_podcast_flat_data.py`, seed 42), which is not part of this folder.

## Environment variables (names only; see `.env.example`)

`PII_SALT`, `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.

## Notes and honest limits

- The SCD2 plan history is **simulated** (fixed seed 42, rules are assumptions); the listening data is synthetic.
- The Neo4j load used `neo4j+ssc://` (encrypted, certificate not verified) because `neo4j+s://` failed on the author's network.
- The 30-day retention analysis uses a deliberate month-end cutoff (subscriptions through 2026-08-31).
- The full list of assumptions and unverified items is in Section 7 of the report.

## Security

No credentials are stored in this repository. Database, cloud and masking secrets are read from environment variables only.
