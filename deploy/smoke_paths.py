#!/usr/bin/env python3
"""Print representative paths for every public route shape."""
import argparse
import sqlite3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    args = parser.parse_args()
    db = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    paths = ["/health", "/", "/plants", "/insects"]
    for prefix, table in (
        ("/plants/taxa", "plant_taxa"),
        ("/insects/taxa", "insect_taxa"),
        ("/plants/evidence", "plant_evidence"),
        ("/insects/evidence", "insect_evidence"),
    ):
        row = db.execute(f"SELECT id FROM {table} ORDER BY id LIMIT 1").fetchone()
        if row:
            paths.append(f"{prefix}/{row[0]}")
    print("\n".join(paths))


if __name__ == "__main__":
    main()
