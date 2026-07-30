#!/usr/bin/env python3
"""Validate database integrity and invariant scientific relationships."""
import argparse
import hashlib
import sqlite3


def scalar(db, sql, parameters=()):
    return db.execute(sql, parameters).fetchone()[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("--baseline", help="require counts to equal key=value lines")
    parser.add_argument("--write-baseline", help="write current counts to this file")
    args = parser.parse_args()
    db = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    failures = []
    integrity = scalar(db, "PRAGMA integrity_check")
    if integrity != "ok":
        failures.append(f"integrity_check={integrity}")
    foreign_keys = list(db.execute("PRAGMA foreign_key_check"))
    if foreign_keys:
        failures.append(f"foreign_key_violations={len(foreign_keys)}")
    counts = {
        table: scalar(db, f"SELECT count(*) FROM {table}")
        for table in (
            "ingestion_batches", "plant_taxa", "insect_taxa",
            "plant_evidence", "insect_evidence", "bold_raw_documents",
        )
    }
    for group in ("plant", "insect"):
        evidence = f"{group}_evidence"
        link = f"{group}_evidence_id"
        if scalar(db, f"SELECT count(*) FROM {evidence} WHERE distance_km > 50 OR distance_km < 0"):
            failures.append(f"{group}_distance_out_of_range")
        if scalar(db, f"SELECT count(*) FROM {evidence} WHERE evidence_type != 'specimen' OR data_source != 'BOLD' OR source_record_id != process_id"):
            failures.append(f"{group}_evidence_identity_invalid")
        if scalar(db, f"SELECT count(*) FROM {evidence} WHERE taxon_id IS NULL AND taxonomy_conflict = 0"):
            failures.append(f"{group}_unlinked_nonconflict_evidence")
        if scalar(db, f"SELECT count(*) FROM bold_raw_documents WHERE organism_group=? AND {link} IS NULL", (group,)):
            failures.append(f"{group}_unlinked_raw_documents")
        if scalar(db, f"SELECT count(*) FROM {evidence} e WHERE e.source_document_count != (SELECT count(*) FROM bold_raw_documents r WHERE r.{link}=e.id)"):
            failures.append(f"{group}_source_document_count_mismatch")
    bad_hashes = sum(
        hashlib.sha256(raw.encode()).hexdigest() != expected
        for raw, expected in db.execute("SELECT raw_json, raw_json_hash FROM bold_raw_documents")
    )
    if bad_hashes:
        failures.append(f"raw_hash_mismatches={bad_hashes}")
    if args.baseline:
        expected = {}
        with open(args.baseline, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    key, value = line.strip().split("=", 1)
                    expected[key] = int(value)
        for key, value in expected.items():
            if counts.get(key) != value:
                failures.append(f"{key}={counts.get(key)} expected={value}")
    for key, value in counts.items():
        print(f"{key}={value}")
    if args.write_baseline:
        with open(args.write_baseline, "w", encoding="utf-8") as handle:
            for key, value in counts.items():
                handle.write(f"{key}={value}\n")
    if failures:
        raise SystemExit("validation failed: " + ", ".join(failures))
    print("validation=ok")


if __name__ == "__main__":
    main()
