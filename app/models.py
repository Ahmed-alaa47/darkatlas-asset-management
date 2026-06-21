import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, JSON, Enum, ForeignKey,
    Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True)
    organization_id = Column(String, nullable=False, index=True)
    type = Column(
        Enum("domain", "subdomain", "ip_address", "service",
             "certificate", "technology", name="asset_type"),
        nullable=False,
    )
    value = Column(String, nullable=False)
    status = Column(
        Enum("active", "stale", "archived", name="asset_status"),
        nullable=False, default="active",
    )
    first_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    source = Column(String, nullable=False, default="import")
    tags = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)

    outgoing = relationship(
        "AssetRelationship", foreign_keys="AssetRelationship.source_id",
        back_populates="source_asset", cascade="all, delete-orphan",
    )
    incoming = relationship(
        "AssetRelationship", foreign_keys="AssetRelationship.target_id",
        back_populates="target_asset", cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "type", "value",
                         name="uq_org_type_value"),
        Index("ix_assets_org_type", "organization_id", "type"),
        Index("ix_assets_org_status", "organization_id", "status"),
    )


class AssetRelationship(Base):
    __tablename__ = "asset_relationships"

    id = Column(String, primary_key=True,
                default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, nullable=False, index=True)
    source_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"),
                       nullable=False)
    target_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"),
                       nullable=False)
    relationship_type = Column(String, nullable=False)

    source_asset = relationship(
        "Asset", foreign_keys=[source_id], back_populates="outgoing")
    target_asset = relationship(
        "Asset", foreign_keys=[target_id], back_populates="incoming")

    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relationship_type",
                         name="uq_relationship"),
    )