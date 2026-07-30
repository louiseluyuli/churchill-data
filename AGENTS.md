# Permanent project instructions

- Stack: Python, FastAPI, server-rendered Jinja2, SQLAlchemy, and SQLite. Run tests with `pytest -q`.
- Never fabricate biological, taxonomic, locality, institution, collection, or catalog data. Missing BOLD values stay null.
- Preserve complete original BOLD documents and their hashes; public HTML must not show raw JSON or DNA sequences.
- Preserve complete available taxonomy paths and never infer lower ranks. Flag genuine marker-document conflicts.
- Keep plant and insect taxon/evidence tables separate. Maintain taxon → evidence → raw-document traceability.
- Use evidence-centered terminology. Current BOLD evidence uses `evidence_type="specimen"`, `data_source="BOLD"`, and `source_record_id=process_id`; future evidence may include checklists, museum records, observations, or professor-provided files.
- Keep the website organized as Home, Plants, and Insects. Plant and insect taxon lists use server-side pagination with 25 taxa per page.
- The loader targets up to 100 unique evidence records per group and defaults to a 30,000 candidate-document cap per group. Never relax the 50 km boundary to reach the target.
- Codex edits and runs commands only in the development workspace at `/home/codexuser/churchill-data`.
- Development uses `/home/codexuser/churchill-data/data/churchill_dev.sqlite3`; use the repository scripts so `DATABASE_URL` is always explicit.
- Never modify `/srv/churchill`, `/var/lib/churchill`, `/etc/churchill`, or production systemd services during ordinary development tasks.
- Never run tests against the production database. Production changes require an explicit deployment task.
- Always back up production before a database replacement or migration.
- Do not restart `churchill-tunnel.service` unless explicitly requested.
- Exact development commands: `scripts/dev-fetch.sh`, `scripts/dev-rebuild.sh`, `scripts/dev-test.sh`, and `scripts/dev-server.sh`.
- Do not commit or push unless explicitly requested.
