import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.loader import (
    classify_document,
    distance_km,
    fetch_group,
    finest_taxon,
    merge_taxonomy_paths,
    rebuild_derived,
    store_raw_documents,
    taxonomy_path,
    valid_coordinates,
)
from app.models import (
    BoldRawDocument,
    IngestionBatch,
    InsectEvidence,
    InsectTaxon,
    PlantEvidence,
    PlantTaxon,
)


def batch(db):
    value = IngestionBatch(
        status="completed",
        bold_endpoint="https://portal.boldsystems.org/api",
        plant_query='{"query":"plant"}',
        insect_query='{"query":"insect"}',
        centre_latitude=58.780833,
        centre_longitude=-94.186944,
        radius_km=50,
        candidate_document_cap=30_000,
        target_evidence_count=100,
    )
    db.add(value)
    db.commit()
    return value


def doc(record_id="P-1.rbcLa", process="P-1", group="plant", **changes):
    value = {
        "record_id": record_id,
        "processid": process,
        "sampleid": "S-1",
        "kingdom": "Plantae" if group == "plant" else "Animalia",
        "phylum": "Tracheophyta" if group == "plant" else "Arthropoda",
        "class": "Magnoliopsida" if group == "plant" else "Insecta",
        "order": "Rosales" if group == "plant" else "Diptera",
        "family": "Rosaceae" if group == "plant" else "Muscidae",
        "genus": "Dryas" if group == "plant" else "Musca",
        "species": "Dryas integrifolia" if group == "plant" else "Musca domestica",
        "coord": [58.780833, -94.186944],
        "marker_code": "rbcLa",
        "nuc": "SECRET-SEQUENCE",
    }
    value.update(changes)
    return value


def load(db, group, documents):
    store_raw_documents(db, batch(db), group, documents)
    db.commit()
    return rebuild_derived(db)


def test_haversine_and_radius_inclusion():
    assert distance_km(58.780833, -94.186944) == pytest.approx(0)
    assert valid_coordinates(doc(coord=[59.20, -94.186944])) is not None
    assert valid_coordinates(doc(coord=[60, -94.186944])) is None


def test_classification_and_complete_taxonomy():
    assert classify_document(doc()) == "plant"
    assert classify_document(doc(group="insect")) == "insect"
    assert classify_document({}) is None
    path = taxonomy_path(doc(subspecies="Dryas integrifolia subsp. chamissonis"))
    assert list(path) == [
        "kingdom", "phylum", "class_name", "order_name", "family",
        "subfamily", "tribe", "genus", "species", "subspecies",
    ]
    assert finest_taxon(path) == ("Dryas integrifolia subsp. chamissonis", "subspecies")
    assert finest_taxon(taxonomy_path(doc(genus=None, species=None))) == ("Rosaceae", "family")


def test_compatible_and_conflicting_path_merge():
    partial = taxonomy_path(doc(genus=None, species=None))
    complete = taxonomy_path(doc())
    merged, conflict = merge_taxonomy_paths([partial, complete])
    assert not conflict and merged["species"] == "Dryas integrifolia"
    _, conflict = merge_taxonomy_paths(
        [complete, taxonomy_path(doc(species="Dryas octopetala"))]
    )
    assert conflict


def test_markers_collapse_to_evidence_and_reverse_relationships(db):
    rows = [
        doc(subfamily="Rosoideae"),
        doc("P-1.matK", marker_code="matK", subfamily="Rosoideae"),
        doc("P-2.rbcLa", process="P-2", sampleid="S-2", subfamily="Rosoideae"),
    ]
    counts = load(db, "plant", rows)
    assert counts["plant_evidence"] == 2 and counts["plant_taxa"] == 1
    assert db.scalar(select(func.count()).select_from(PlantEvidence)) == 2
    taxon = db.scalar(select(PlantTaxon))
    assert len(taxon.evidence) == 2
    evidence = db.scalar(
        select(PlantEvidence).where(PlantEvidence.source_record_id == "P-1")
    )
    assert evidence.evidence_type == "specimen"
    assert evidence.data_source == "BOLD"
    assert evidence.process_id == evidence.source_record_id == "P-1"
    assert evidence.source_document_count == 2 and len(evidence.raw_documents) == 2
    assert all(
        row.plant_evidence_id and row.insect_evidence_id is None
        for row in evidence.raw_documents
    )
    assert json.loads(evidence.raw_documents[0].raw_json)["nuc"] == "SECRET-SEQUENCE"


def test_conflicting_evidence_flagged_and_excluded(db):
    load(db, "plant", [doc(), doc("P-1.matK", species="Dryas octopetala")])
    evidence = db.scalar(select(PlantEvidence))
    assert evidence.taxonomy_conflict and evidence.taxon_id is None
    assert db.scalar(select(func.count()).select_from(PlantTaxon)) == 0


def test_uniqueness_is_data_source_and_source_record_id(db):
    load(db, "plant", [doc()])
    first = db.scalar(select(PlantEvidence))
    db.add(
        PlantEvidence(
            evidence_type="observation",
            data_source=first.data_source,
            source_record_id=first.source_record_id,
            process_id=None,
            latitude=first.latitude,
            longitude=first.longitude,
            distance_km=0,
            source_document_count=0,
            taxonomy_conflict=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_rebuild_idempotency_radius_and_group_separation(db):
    b = batch(db)
    store_raw_documents(db, b, "plant", [doc()])
    store_raw_documents(db, b, "insect", [doc("I-1.COI", process="I-1", group="insect")])
    store_raw_documents(db, b, "insect", [doc("I-OUT.COI", process="I-OUT", group="insect", coord=[60, -94])])
    db.commit()
    first = rebuild_derived(db)
    second = rebuild_derived(db)
    assert first == second
    assert db.scalar(select(func.count()).select_from(PlantEvidence)) == 1
    assert db.scalar(select(func.count()).select_from(InsectEvidence)) == 1
    assert db.scalar(select(func.count()).select_from(PlantTaxon)) == 1
    assert db.scalar(select(func.count()).select_from(InsectTaxon)) == 1
    assert all(item.distance_km <= 50 for item in db.scalars(select(PlantEvidence)))
    assert all(item.distance_km <= 50 for item in db.scalars(select(InsectEvidence)))


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, documents):
        self.documents = documents

    def get(self, url, params, timeout):
        if url.endswith("/query"):
            return Response({"query_id": "query-1"})
        start = params["start"]
        length = params["length"]
        return Response({"data": self.documents[start : start + length]})


def test_fetch_limit_collapses_markers_and_reports_cap():
    documents = [
        doc("P-1.rbcLa"),
        doc("P-1.matK"),
        doc("P-2.rbcLa", process="P-2"),
        doc("P-3.rbcLa", process="P-3"),
    ]
    accepted, examined, cap_reached = fetch_group(
        "query", FakeClient(documents), evidence_limit=2, candidate_cap=3
    )
    assert [item["record_id"] for item in accepted] == [
        "P-1.rbcLa", "P-1.matK", "P-2.rbcLa"
    ]
    assert examined == 3 and cap_reached
