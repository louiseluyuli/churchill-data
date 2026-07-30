from sqlalchemy import select

from app.loader import rebuild_derived, store_raw_documents
from app.models import InsectEvidence, InsectTaxon, PlantEvidence, PlantTaxon
from .test_loader import batch, doc


def seeded(db, count=1):
    b = batch(db)
    plants = [
        doc(
            f"P-{number}.rbcLa",
            process=f"P-{number}",
            species=f"Dryas species {number}",
        )
        for number in range(1, count + 1)
    ]
    insects = [
        doc(
            f"I-{number}.COI",
            process=f"I-{number}",
            group="insect",
            species=f"Musca species {number}",
            specimen_linkout=f"https://example.org/bold/I-{number}",
        )
        for number in range(1, count + 1)
    ]
    store_raw_documents(db, b, "plant", plants)
    store_raw_documents(db, b, "insect", insects)
    db.commit()
    rebuild_derived(db)


def test_homepage_summaries_previews_and_navigation(client, db):
    seeded(db, 12)
    response = client.get("/")
    assert response.status_code == 200
    assert "Current evidence comes from BOLD" in response.text
    assert 'id="plant-taxa-preview"' in response.text
    assert 'id="insect-taxa-preview"' in response.text
    assert response.text.count('href="/plants/taxa/') == 10
    assert response.text.count('href="/insects/taxa/') == 10
    for label, url in (("Home", "/"), ("Plants", "/plants"), ("Insects", "/insects")):
        assert f'href="{url}">{label}</a>' in response.text


def test_taxon_lists_paginate_and_handle_invalid_pages(client, db):
    seeded(db, 30)
    first = client.get("/plants")
    second = client.get("/plants?page=2")
    insects = client.get("/insects?page=2")
    invalid = client.get("/plants?page=not-a-number")
    low = client.get("/plants?page=-3")
    high = client.get("/plants?page=999")
    assert all(item.status_code == 200 for item in [first, second, insects, invalid, low, high])
    assert "Page 1 of 2" in first.text and "Previous" in first.text and "Next" in first.text
    assert first.text.count('href="/plants/taxa/') == 50  # evidence count and taxon name links
    assert second.text.count('href="/plants/taxa/') == 10
    assert "Page 2 of 2" in insects.text
    assert "Page 1 of 2" in invalid.text and "Page 1 of 2" in low.text
    assert "Page 2 of 2" in high.text


def test_taxon_and_evidence_detail_pages(client, db):
    seeded(db)
    plant_taxon = db.scalar(select(PlantTaxon))
    insect_taxon = db.scalar(select(InsectTaxon))
    plant = db.scalar(select(PlantEvidence))
    insect = db.scalar(select(InsectEvidence))
    checks = [
        (f"/plants/taxa/{plant_taxon.id}", "Supporting evidence"),
        (f"/insects/taxa/{insect_taxon.id}", insect.process_id),
        (f"/plants/evidence/{plant.id}", "BOLD process ID"),
        (f"/insects/evidence/{insect.id}", "I-1.COI"),
    ]
    for url, needle in checks:
        response = client.get(url)
        assert response.status_code == 200 and needle in response.text


def test_public_html_hides_raw_json_and_sequence(client, db):
    seeded(db)
    evidence = db.scalar(select(PlantEvidence))
    pages = [
        client.get("/").text,
        client.get("/plants").text,
        client.get(f"/plants/evidence/{evidence.id}").text,
    ]
    assert all(
        "SECRET-SEQUENCE" not in page
        and "raw_json" not in page
        and "churchill_bold.sqlite3" not in page
        for page in pages
    )


def test_health_and_not_found(client):
    response = client.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    assert client.get("/plants/taxa/999999").status_code == 404
    assert client.get("/insects/evidence/999999").status_code == 404
