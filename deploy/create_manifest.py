#!/usr/bin/env python3
"""Write a deterministic release manifest."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("release")
    parser.add_argument("timestamp")
    args = parser.parse_args()
    source, release = Path(args.source), Path(args.release)
    status = subprocess.run(
        ["git", "status", "--short"], cwd=source, check=True,
        text=True, stdout=subprocess.PIPE,
    ).stdout.rstrip("\n")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source, check=True,
        text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    hashes = {}
    for path in sorted(release.rglob("*")):
        relative = path.relative_to(release).as_posix()
        if path.is_file() and not relative.startswith(".venv/") and relative != "release-manifest.json":
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "timestamp": args.timestamp,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "working_tree_dirty": bool(status),
        "git_status_short": status.splitlines(),
        "application_file_sha256": hashes,
    }
    (release / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
