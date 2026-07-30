from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
    bold_endpoint: Mapped[str] = mapped_column(String(255))
    plant_query: Mapped[str] = mapped_column(Text)
    insect_query: Mapped[str] = mapped_column(Text)
    centre_latitude: Mapped[float] = mapped_column(Float)
    centre_longitude: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float)
    candidate_document_cap: Mapped[int] = mapped_column(Integer)
    target_evidence_count: Mapped[int] = mapped_column(Integer)
    plant_candidate_document_count: Mapped[int] = mapped_column(Integer, default=0)
    insect_candidate_document_count: Mapped[int] = mapped_column(Integer, default=0)
    plant_candidate_cap_reached: Mapped[bool] = mapped_column(Boolean, default=False)
    insect_candidate_cap_reached: Mapped[bool] = mapped_column(Boolean, default=False)
    plant_accepted_raw_document_count: Mapped[int] = mapped_column(Integer, default=0)
    insect_accepted_raw_document_count: Mapped[int] = mapped_column(Integer, default=0)
    plant_accepted_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    insect_accepted_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    raw_documents: Mapped[list["BoldRawDocument"]] = relationship(back_populates="batch")


class TaxonFields:
    id: Mapped[int] = mapped_column(primary_key=True)
    taxonomy_key: Mapped[str] = mapped_column(String(64), unique=True)
    kingdom: Mapped[str | None] = mapped_column(String(255))
    phylum: Mapped[str | None] = mapped_column(String(255))
    class_name: Mapped[str | None] = mapped_column(String(255), index=True)
    order_name: Mapped[str | None] = mapped_column(String(255), index=True)
    family: Mapped[str | None] = mapped_column(String(255), index=True)
    subfamily: Mapped[str | None] = mapped_column(String(255))
    tribe: Mapped[str | None] = mapped_column(String(255))
    genus: Mapped[str | None] = mapped_column(String(255), index=True)
    species: Mapped[str | None] = mapped_column(String(255), index=True)
    subspecies: Mapped[str | None] = mapped_column(String(255))
    finest_taxon_name: Mapped[str] = mapped_column(String(255), index=True)
    finest_taxon_rank: Mapped[str] = mapped_column(String(24), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PlantTaxon(TaxonFields, Base):
    __tablename__ = "plant_taxa"
    evidence: Mapped[list["PlantEvidence"]] = relationship(back_populates="taxon")


class InsectTaxon(TaxonFields, Base):
    __tablename__ = "insect_taxa"
    evidence: Mapped[list["InsectEvidence"]] = relationship(back_populates="taxon")


class EvidenceFields:
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_type: Mapped[str] = mapped_column(String(64), index=True)
    data_source: Mapped[str] = mapped_column(String(64), index=True)
    source_record_id: Mapped[str] = mapped_column(String(255), index=True)
    process_id: Mapped[str | None] = mapped_column(String(255), index=True)
    sample_id: Mapped[str | None] = mapped_column(String(255))
    collection_date: Mapped[str | None] = mapped_column(String(64))
    collector: Mapped[str | None] = mapped_column(String(512))
    site: Mapped[str | None] = mapped_column(String(512))
    locality: Mapped[str | None] = mapped_column(String(512))
    province_state: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float)
    institution_name: Mapped[str | None] = mapped_column(String(512))
    institution_code: Mapped[str | None] = mapped_column(String(255))
    collection_code: Mapped[str | None] = mapped_column(String(255))
    catalog_number: Mapped[str | None] = mapped_column(String(255))
    source_dataset: Mapped[str | None] = mapped_column(Text)
    source_document_count: Mapped[int] = mapped_column(Integer)
    taxonomy_conflict: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PlantEvidence(EvidenceFields, Base):
    __tablename__ = "plant_evidence"
    __table_args__ = (
        UniqueConstraint("data_source", "source_record_id", name="uq_plant_evidence_source"),
    )
    taxon_id: Mapped[int | None] = mapped_column(ForeignKey("plant_taxa.id"), index=True)
    taxon: Mapped[PlantTaxon | None] = relationship(back_populates="evidence")
    raw_documents: Mapped[list["BoldRawDocument"]] = relationship(
        back_populates="plant_evidence",
        foreign_keys="BoldRawDocument.plant_evidence_id",
    )


class InsectEvidence(EvidenceFields, Base):
    __tablename__ = "insect_evidence"
    __table_args__ = (
        UniqueConstraint("data_source", "source_record_id", name="uq_insect_evidence_source"),
    )
    taxon_id: Mapped[int | None] = mapped_column(ForeignKey("insect_taxa.id"), index=True)
    taxon: Mapped[InsectTaxon | None] = relationship(back_populates="evidence")
    raw_documents: Mapped[list["BoldRawDocument"]] = relationship(
        back_populates="insect_evidence",
        foreign_keys="BoldRawDocument.insect_evidence_id",
    )


class BoldRawDocument(Base):
    __tablename__ = "bold_raw_documents"
    __table_args__ = (
        CheckConstraint(
            "NOT (plant_evidence_id IS NOT NULL AND insect_evidence_id IS NOT NULL)",
            name="ck_raw_document_one_evidence_group",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingestion_batches.id"), index=True)
    organism_group: Mapped[str] = mapped_column(
        String(12), CheckConstraint("organism_group IN ('plant', 'insect')")
    )
    record_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    process_id: Mapped[str] = mapped_column(String(255), index=True)
    marker_code: Mapped[str | None] = mapped_column(String(255))
    source_record_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw_json: Mapped[str] = mapped_column(Text)
    raw_json_hash: Mapped[str] = mapped_column(String(64), index=True)
    plant_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("plant_evidence.id"), index=True
    )
    insect_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("insect_evidence.id"), index=True
    )
    batch: Mapped[IngestionBatch] = relationship(back_populates="raw_documents")
    plant_evidence: Mapped[PlantEvidence | None] = relationship(
        back_populates="raw_documents", foreign_keys=[plant_evidence_id]
    )
    insect_evidence: Mapped[InsectEvidence | None] = relationship(
        back_populates="raw_documents", foreign_keys=[insect_evidence_id]
    )


Index("ix_plant_taxonomy_path", PlantTaxon.kingdom, PlantTaxon.phylum, PlantTaxon.class_name)
Index(
    "ix_insect_taxonomy_path",
    InsectTaxon.kingdom,
    InsectTaxon.phylum,
    InsectTaxon.class_name,
)
