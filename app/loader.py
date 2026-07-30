from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from sqlalchemy import delete, select

from .database import Base, SessionLocal, engine
from .models import (
    BoldRawDocument,
    IngestionBatch,
    InsectEvidence,
    InsectTaxon,
    PlantEvidence,
    PlantTaxon,
)

BOLD_ENDPOINT = "https://portal.boldsystems.org/api"
CENTRE_LATITUDE = 58.780833
CENTRE_LONGITUDE = -94.186944
RADIUS_KM = 50.0
EVIDENCE_LIMIT = 100
CANDIDATE_DOCUMENT_CAP = 30_000
PAGE_LENGTH = 500
QUERIES = {
    "plant": "tax:kingdom:Plantae;inst:name:Churchill Northern Studies Centre",
    "insect": "tax:class:Insecta;geo:province/state:Manitoba",
}
RANKS = (
    "kingdom",
    "phylum",
    "class_name",
    "order_name",
    "family",
    "subfamily",
    "tribe",
    "genus",
    "species",
    "subspecies",
)
SOURCE_KEYS = {
    "sample_id": ("sampleid",),
    "collection_date": ("collection_date_start",),
    "collector": ("collectors",),
    "site": ("site",),
    "locality": ("region", "sector"),
    "province_state": ("province/state",),
    "country": ("country/ocean",),
    "institution_name": ("inst",),
    "institution_code": ("institution_code", "inst_code"),
    "collection_code": ("collection_code",),
    "catalog_number": ("museumid", "catalog_number"),
}


def normalize(value):
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def distance_km(latitude, longitude):
    radius = 6371.0088
    lat1, lat2 = map(math.radians, (CENTRE_LATITUDE, latitude))
    dlat = lat2 - lat1
    dlon = math.radians(longitude - CENTRE_LONGITUDE)
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def valid_coordinates(document):
    coord = document.get("coord")
    if not isinstance(coord, (list, tuple)) or len(coord) != 2:
        return None
    try:
        latitude, longitude = float(coord[0]), float(coord[1])
    except (TypeError, ValueError):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    distance = distance_km(latitude, longitude)
    return (latitude, longitude, distance) if distance <= RADIUS_KM else None


def classify_document(document):
    kingdom = normalize(document.get("kingdom"))
    class_name = normalize(document.get("class"))
    if kingdom and kingdom.casefold() == "plantae":
        return "plant"
    if class_name and class_name.casefold() == "insecta":
        return "insect"
    return None


def taxonomy_path(document):
    return {
        "kingdom": normalize(document.get("kingdom")),
        "phylum": normalize(document.get("phylum")),
        "class_name": normalize(document.get("class")),
        "order_name": normalize(document.get("order")),
        "family": normalize(document.get("family")),
        "subfamily": normalize(document.get("subfamily")),
        "tribe": normalize(document.get("tribe")),
        "genus": normalize(document.get("genus")),
        "species": normalize(document.get("species")),
        "subspecies": normalize(document.get("subspecies")),
    }


def merge_taxonomy_paths(paths):
    merged = {rank: None for rank in RANKS}
    conflict = False
    for path in paths:
        for rank in RANKS:
            value = normalize(path.get(rank))
            if not value:
                continue
            if merged[rank] is None:
                merged[rank] = value
            elif merged[rank].casefold() != value.casefold():
                conflict = True
    return merged, conflict


def finest_taxon(path):
    for rank in reversed(RANKS):
        if path.get(rank):
            return path[rank], rank.removesuffix("_name")
    return None, None


def taxonomy_key(path):
    values = [
        normalize(path.get(rank)).casefold() if normalize(path.get(rank)) else ""
        for rank in RANKS
    ]
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def canonical_json(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fetch_group(query, client=None, *, evidence_limit=EVIDENCE_LIMIT, candidate_cap=CANDIDATE_DOCUMENT_CAP):
    http = client or requests.Session()
    response = http.get(
        f"{BOLD_ENDPOINT}/query", params={"query": query, "extent": "large"}, timeout=60
    )
    response.raise_for_status()
    query_id = response.json()["query_id"]
    selected_process_ids: list[str] = []
    accepted = []
    candidate_count = 0
    start = 0
    exhausted = False
    while candidate_count < candidate_cap:
        length = min(PAGE_LENGTH, candidate_cap - candidate_count)
        response = http.get(
            f"{BOLD_ENDPOINT}/documents/{quote(query_id, safe='')}",
            params={"length": length, "start": start},
            timeout=60,
        )
        response.raise_for_status()
        page = response.json().get("data", [])
        if not page:
            exhausted = True
            break
        candidate_count += len(page)
        for document in page:
            process_id = normalize(document.get("processid"))
            if (
                not process_id
                or not normalize(document.get("record_id"))
                or valid_coordinates(document) is None
            ):
                continue
            if process_id not in selected_process_ids and len(selected_process_ids) < evidence_limit:
                selected_process_ids.append(process_id)
            if process_id in selected_process_ids:
                accepted.append(document)
        start += len(page)
        if len(page) < length:
            exhausted = True
            break
    return accepted, candidate_count, not exhausted and candidate_count >= candidate_cap


def store_raw_documents(db, batch, group, documents):
    inserted = 0
    for document in documents:
        record_id = normalize(document.get("record_id"))
        process_id = normalize(document.get("processid"))
        if not record_id or not process_id or valid_coordinates(document) is None:
            continue
        if (
            db.scalar(select(BoldRawDocument.id).where(BoldRawDocument.record_id == record_id))
            is not None
        ):
            continue
        raw = canonical_json(document)
        db.add(
            BoldRawDocument(
                batch=batch,
                organism_group=group,
                record_id=record_id,
                process_id=process_id,
                marker_code=normalize(document.get("marker_code")),
                source_record_url=normalize(
                    document.get("specimen_linkout") or document.get("record_url")
                ),
                raw_json=raw,
                raw_json_hash=hashlib.sha256(raw.encode()).hexdigest(),
            )
        )
        inserted += 1
    db.flush()
    return inserted


def _first(documents, keys):
    for document in documents:
        for key in keys:
            value = normalize(document.get(key))
            if value:
                return value
    return None


def _dataset(documents):
    values = []
    for document in documents:
        raw = document.get("bold_recordset_code_arr")
        candidates = raw if isinstance(raw, list) else [raw]
        for candidate in candidates:
            value = normalize(candidate)
            if value and value not in values:
                values.append(value)
    return ", ".join(values) or None


def rebuild_derived(db):
    for raw in db.scalars(select(BoldRawDocument)):
        raw.plant_evidence_id = None
        raw.insect_evidence_id = None
    db.flush()
    db.execute(delete(PlantEvidence))
    db.execute(delete(InsectEvidence))
    db.execute(delete(PlantTaxon))
    db.execute(delete(InsectTaxon))
    db.flush()
    counts = {}
    for group, evidence_model, taxon_model in (
        ("plant", PlantEvidence, PlantTaxon),
        ("insect", InsectEvidence, InsectTaxon),
    ):
        grouped = defaultdict(list)
        for row in db.scalars(
            select(BoldRawDocument).where(BoldRawDocument.organism_group == group)
        ):
            grouped[row.process_id].append(row)
        taxon_cache = {}
        conflicts = 0
        made = 0
        for process_id, raw_rows in grouped.items():
            documents = [json.loads(row.raw_json) for row in raw_rows]
            valid = [coordinates for document in documents if (coordinates := valid_coordinates(document))]
            if not valid:
                continue
            path, conflict = merge_taxonomy_paths([taxonomy_path(d) for d in documents])
            name, rank = finest_taxon(path)
            taxon = None
            if not conflict and name and rank:
                key = taxonomy_key(path)
                taxon = taxon_cache.get(key)
                if taxon is None:
                    taxon = taxon_model(
                        taxonomy_key=key,
                        finest_taxon_name=name,
                        finest_taxon_rank=rank,
                        **path,
                    )
                    db.add(taxon)
                    db.flush()
                    taxon_cache[key] = taxon
            if conflict:
                conflicts += 1
            latitude, longitude, distance = valid[0]
            fields = {
                field: _first(documents, keys) for field, keys in SOURCE_KEYS.items()
            }
            evidence = evidence_model(
                taxon=taxon,
                evidence_type="specimen",
                data_source="BOLD",
                source_record_id=process_id,
                process_id=process_id,
                latitude=latitude,
                longitude=longitude,
                distance_km=distance,
                source_dataset=_dataset(documents),
                source_document_count=len(raw_rows),
                taxonomy_conflict=conflict,
                **fields,
            )
            db.add(evidence)
            db.flush()
            made += 1
            for row in raw_rows:
                if group == "plant":
                    row.plant_evidence = evidence
                else:
                    row.insect_evidence = evidence
        counts.update(
            {
                f"{group}_evidence": made,
                f"{group}_taxa": len(taxon_cache),
                f"{group}_conflicts": conflicts,
            }
        )
    db.commit()
    return counts


def fetch_and_store(
    db,
    client=None,
    *,
    evidence_limit=EVIDENCE_LIMIT,
    candidate_cap=CANDIDATE_DOCUMENT_CAP,
):
    def request_meta(query):
        return json.dumps(
            {
                "query": {"query": query, "extent": "large"},
                "documents": {
                    "length": PAGE_LENGTH,
                    "start": "paged",
                    "candidate_cap": candidate_cap,
                },
            },
            sort_keys=True,
        )

    batch = IngestionBatch(
        status="running",
        bold_endpoint=BOLD_ENDPOINT,
        plant_query=request_meta(QUERIES["plant"]),
        insect_query=request_meta(QUERIES["insect"]),
        centre_latitude=CENTRE_LATITUDE,
        centre_longitude=CENTRE_LONGITUDE,
        radius_km=RADIUS_KM,
        candidate_document_cap=candidate_cap,
        target_evidence_count=evidence_limit,
    )
    db.add(batch)
    db.commit()
    try:
        for group in ("plant", "insect"):
            documents, candidates, cap_reached = fetch_group(
                QUERIES[group],
                client,
                evidence_limit=evidence_limit,
                candidate_cap=candidate_cap,
            )
            inserted = store_raw_documents(db, batch, group, documents)
            setattr(batch, f"{group}_candidate_document_count", candidates)
            setattr(batch, f"{group}_candidate_cap_reached", cap_reached)
            setattr(batch, f"{group}_accepted_raw_document_count", inserted)
            setattr(
                batch,
                f"{group}_accepted_evidence_count",
                len({normalize(d.get("processid")) for d in documents}),
            )
        batch.status = "completed"
        batch.completed_at = datetime.now(timezone.utc)
        db.commit()
        return batch, rebuild_derived(db)
    except Exception as exc:
        db.rollback()
        failed = db.get(IngestionBatch, batch.id)
        failed.status = "failed"
        failed.completed_at = datetime.now(timezone.utc)
        failed.error_summary = f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("fetch", "rebuild"), nargs="?", default="fetch")
    parser.add_argument(
        "--evidence-limit",
        type=int,
        default=int(os.getenv("BOLD_EVIDENCE_LIMIT", EVIDENCE_LIMIT)),
    )
    parser.add_argument(
        "--candidate-cap",
        type=int,
        default=int(os.getenv("BOLD_CANDIDATE_DOCUMENT_CAP", CANDIDATE_DOCUMENT_CAP)),
    )
    args = parser.parse_args()
    if args.evidence_limit < 1 or args.candidate_cap < 1:
        parser.error("limits must be positive integers")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if args.command == "fetch":
            batch, result = fetch_and_store(
                db,
                evidence_limit=args.evidence_limit,
                candidate_cap=args.candidate_cap,
            )
            result = {
                "batch_id": batch.id,
                "plant_candidate_documents": batch.plant_candidate_document_count,
                "insect_candidate_documents": batch.insect_candidate_document_count,
                "plant_candidate_cap_reached": batch.plant_candidate_cap_reached,
                "insect_candidate_cap_reached": batch.insect_candidate_cap_reached,
                **result,
            }
        else:
            result = rebuild_derived(db)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
