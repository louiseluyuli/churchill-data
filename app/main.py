import math
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from .database import Base, SessionLocal, engine
from .models import (
    BoldRawDocument,
    InsectEvidence,
    InsectTaxon,
    PlantEvidence,
    PlantTaxon,
)

Base.metadata.create_all(engine)
app = FastAPI(title="Churchill BOLD evidence prototype")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
TAXA_PER_PAGE = 25


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def summary(db, taxon_model, evidence_model, group):
    taxa = list(
        db.scalars(
            select(taxon_model)
            .options(selectinload(taxon_model.evidence))
            .order_by(taxon_model.finest_taxon_name, taxon_model.id)
            .limit(10)
        )
    )
    return {
        "taxa": taxa,
        "taxon_count": db.scalar(select(func.count()).select_from(taxon_model)) or 0,
        "species_count": db.scalar(
            select(func.count())
            .select_from(taxon_model)
            .where(taxon_model.finest_taxon_rank == "species")
        )
        or 0,
        "evidence_count": db.scalar(select(func.count()).select_from(evidence_model)) or 0,
        "raw_count": db.scalar(
            select(func.count())
            .select_from(BoldRawDocument)
            .where(BoldRawDocument.organism_group == group)
        )
        or 0,
        "conflict_count": db.scalar(
            select(func.count())
            .select_from(evidence_model)
            .where(evidence_model.taxonomy_conflict.is_(True))
        )
        or 0,
    }


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request, db=Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "plants": summary(db, PlantTaxon, PlantEvidence, "plant"),
            "insects": summary(db, InsectTaxon, InsectEvidence, "insect"),
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


def parse_page(raw_page):
    try:
        return max(1, int(raw_page))
    except (TypeError, ValueError):
        return 1


def taxa_page(request, db, taxon_model, group, title):
    total = db.scalar(select(func.count()).select_from(taxon_model)) or 0
    total_pages = max(1, math.ceil(total / TAXA_PER_PAGE))
    page = min(parse_page(request.query_params.get("page")), total_pages)
    taxa = list(
        db.scalars(
            select(taxon_model)
            .options(selectinload(taxon_model.evidence))
            .order_by(taxon_model.finest_taxon_name, taxon_model.id)
            .offset((page - 1) * TAXA_PER_PAGE)
            .limit(TAXA_PER_PAGE)
        )
    )
    return templates.TemplateResponse(
        request=request,
        name="taxa.html",
        context={
            "taxa": taxa,
            "group": group,
            "title": title,
            "page": page,
            "total_pages": total_pages,
            "total_taxa": total,
            "page_numbers": range(max(1, page - 3), min(total_pages, page + 3) + 1),
        },
    )


@app.get("/plants", response_class=HTMLResponse)
async def plants(request: Request, db=Depends(get_db)):
    return taxa_page(request, db, PlantTaxon, "plant", "Plant taxa")


@app.get("/insects", response_class=HTMLResponse)
async def insects(request: Request, db=Depends(get_db)):
    return taxa_page(request, db, InsectTaxon, "insect", "Insect taxa")


def taxon_page(request, db, taxon_id, taxon_model, group):
    taxon = db.scalar(
        select(taxon_model)
        .where(taxon_model.id == taxon_id)
        .options(selectinload(taxon_model.evidence))
    )
    if not taxon:
        raise HTTPException(404, "Taxon not found")
    raw_count = sum(item.source_document_count for item in taxon.evidence)
    return templates.TemplateResponse(
        request=request,
        name="taxon_detail.html",
        context={"taxon": taxon, "group": group, "raw_count": raw_count},
    )


@app.get("/plants/taxa/{taxon_id}", response_class=HTMLResponse)
async def plant_taxon(request: Request, taxon_id: int, db=Depends(get_db)):
    return taxon_page(request, db, taxon_id, PlantTaxon, "plant")


@app.get("/insects/taxa/{taxon_id}", response_class=HTMLResponse)
async def insect_taxon(request: Request, taxon_id: int, db=Depends(get_db)):
    return taxon_page(request, db, taxon_id, InsectTaxon, "insect")


def evidence_page(request, db, evidence_id, evidence_model, group):
    evidence = db.scalar(
        select(evidence_model)
        .where(evidence_model.id == evidence_id)
        .options(
            selectinload(evidence_model.taxon),
            selectinload(evidence_model.raw_documents),
        )
    )
    if not evidence:
        raise HTTPException(404, "Evidence not found")
    return templates.TemplateResponse(
        request=request,
        name="evidence_detail.html",
        context={"evidence": evidence, "group": group},
    )


@app.get("/plants/evidence/{evidence_id}", response_class=HTMLResponse)
async def plant_evidence(request: Request, evidence_id: int, db=Depends(get_db)):
    return evidence_page(request, db, evidence_id, PlantEvidence, "plant")


@app.get("/insects/evidence/{evidence_id}", response_class=HTMLResponse)
async def insect_evidence(request: Request, evidence_id: int, db=Depends(get_db)):
    return evidence_page(request, db, evidence_id, InsectEvidence, "insect")
