# Podcast Analytics — Cloud Native Data Engineering (Assignments 1-3)

One domain across three assignments: podcast hosting plus creator-side subscription and retention analytics.

| Folder | What is in it |
|---|---|
| `Assignment1/` | Design diagrams: the AWS architecture (`4.drawio.png`, editable `aws.drawio`) and the relational design (`EER.png`) |
| `Assignment2/` | MySQL schema and queries (`Assignment2_SQL_Script.sql`), the CSV loader (`Data/load_to_mysql.py`, reads credentials from environment variables) and the synthetic data generator (`generate_podcast_flat_data.py`, seed 42) |
| `Assignment3/` | Live API pipeline (Bronze/Silver/Gold, PII masking), Snowflake star schema with SCD2, Neo4j graph, single-file `warehouse_script.sql` and `neo4j_script.cypher`, the written report and screenshots. Start with `Assignment3/README.md` |

Not in this repository on purpose: generated data files (the raw flat table is synthetic but contains unmasked names and e-mails),
billing and security-configuration documents, credentials, and private working notes. Credentials are always read from environment variables.
