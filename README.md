# Churchill BOLD evidence prototype

This read-only, teacher-facing FastAPI demo presents plant and insect taxa recorded near Churchill, Manitoba. It preserves traceability from each complete taxonomy path through an evidence record to the original BOLD marker documents. It is a capped prototype, not a definitive checklist, and its insect records must not be interpreted as confirmed pollinators.

## Data model and terminology

The stack is Python, FastAPI, server-rendered Jinja2, SQLAlchemy, and SQLite. Plant and insect structures remain separate:

```text
BOLD GET /api/query
  -> BOLD GET /api/documents/{query_id} (paged, capped candidate scan)
  -> bold_raw_documents (complete original marker documents and hashes)
  -> group by BOLD process_id
  -> plant_evidence / insect_evidence (one BOLD process_id per evidence row)
  -> plant_taxa / insect_taxa (unique complete compatible taxonomy paths)
  -> read-only FastAPI + Jinja2 pages
```

For current imports, every evidence row has `evidence_type="specimen"`, `data_source="BOLD"`, and `source_record_id=process_id`. Uniqueness is based on `(data_source, source_record_id)`, while `process_id` remains nullable so future evidence can come from checklists, museum records, observations, or professor-provided files. Multiple BOLD marker documents for one process ID remain complete raw documents but collapse into one evidence row.

`ingestion_batches` records each attempt, request definitions, endpoint, timestamps, geographic rule, target and cap, candidate/accepted counts, cap status, and errors. Each raw document links to either plant or insect evidence. Compatible evidence links to a taxon; genuine marker-document taxonomy conflicts are flagged and excluded from normal taxon aggregation. Missing BOLD values remain null, and lower taxonomy ranks are never inferred.

## Source, geography, and sample

The current data source is the official BOLD Data Portal at `https://portal.boldsystems.org/api`. Churchill is provisionally defined as a 50 km great-circle radius around latitude `58.780833`, longitude `-94.186944`, WGS84 / EPSG:4326. This is not an official scientific boundary.

The existing queries are:

- Plants: `tax:kingdom:Plantae;inst:name:Churchill Northern Studies Centre`
- Insects: `tax:class:Insecta;geo:province/state:Manitoba`

The Manitoba insect query retrieves candidates only. Documents without valid coordinates and documents beyond 50 km are never saved. The loader targets up to 100 unique evidence records per group and scans at most 30,000 candidate documents per group by default. It reports the available count if fewer qualify and never relaxes the boundary or fabricates data.

The target and cap are configurable with `--evidence-limit` and `--candidate-cap`, or the `BOLD_EVIDENCE_LIMIT` and `BOLD_CANDIDATE_DOCUMENT_CAP` environment variables.

## Website

The shared navigation has three top-level pages:

- `/` — summaries, conflict and raw-document counts, and previews of up to 10 taxa per group
- `/plants` — complete paginated plant taxon table
- `/insects` — complete paginated insect taxon table

Taxon lists use server-side pagination with 25 rows per page, `?page=N`, Previous/Next controls, nearby page numbers, and safe normalization of invalid or out-of-range values. Taxon detail pages list all supporting evidence; evidence detail pages show public provenance and marker metadata without exposing raw JSON or DNA sequences. `/health` returns application health.

## Exact commands

Set up the local environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Development always uses `data/churchill_dev.sqlite3`. These wrappers export its
absolute `DATABASE_URL`; tests run against that explicit development database:

```bash
scripts/dev-test.sh
scripts/dev-server.sh
scripts/dev-fetch.sh
scripts/dev-rebuild.sh
```

The development server defaults to `http://127.0.0.1:8001/`, leaving port 8000
for production.

## Production operations

Production is changed only by an explicit root-run deployment:

```bash
sudo /home/codexuser/churchill-data/scripts/deploy-production.sh \
  --skip-public-check
sudo /home/codexuser/churchill-data/scripts/sync-production-to-development.sh
```

Deployments test first, safely back up and validate SQLite, create an immutable
release with its own virtual environment and manifest, smoke-test it, atomically
switch the active symlink, and restart only the web service. Failed verification
restores the previous release, service, and replaced database. Future deployments
reject dirty Git state unless `--allow-dirty` is explicit; `--rebuild-database`
rebuilds a candidate from preserved raw documents and validates it before use.

Use `--public-url https://EXISTING.trycloudflare.com` to verify an existing
Quick Tunnel after the local checks. Use `--skip-public-check` for local-only
verification of `http://127.0.0.1:8000/health` and
`http://127.0.0.1:8000/`; this never changes or checks the tunnel service.
Initial migrations do not require `--public-url` and default to local-only
verification when neither public-check option is supplied.

## Boundaries

This remains a small SQLite prototype. Search, filters, maps, authentication,
PostgreSQL, client-side frameworks, and firewall changes are outside this work.
Database files, downloads, backups, caches, credentials, and virtual environments
remain untracked. Ordinary development never writes production paths or services,
and deployment never restarts the tunnel service.
