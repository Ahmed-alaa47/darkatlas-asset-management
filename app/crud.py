from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app import models, schemas


def get_asset(db: Session, asset_id: str, org_id: str) -> Optional[models.Asset]:
    return (
        db.query(models.Asset)
        .filter(models.Asset.id == asset_id,
                models.Asset.organization_id == org_id)
        .first()
    )


def upsert_asset(db: Session, asset_in: schemas.AssetIn,
                 org_id: str) -> tuple[models.Asset, bool]:
    """
    Upsert by (org, type, value). Returns (asset, created).
    Merge strategy:
      - status: if incoming is 'active' and existing is 'stale',
        revive to 'active'.
      - tags: union.
      - metadata: shallow merge (incoming wins on conflict).
      - last_seen: always update.
    """
    existing = (
        db.query(models.Asset)
        .filter(
            models.Asset.organization_id == org_id,
            models.Asset.type == asset_in.type,
            models.Asset.value == asset_in.value,
        )
        .first()
    )

    if existing:
        if asset_in.status == schemas.AssetStatus.active and \
                existing.status == schemas.AssetStatus.stale:
            existing.status = schemas.AssetStatus.active
        elif asset_in.status is not None:
            existing.status = asset_in.status

        existing.last_seen = datetime.utcnow()
        existing.tags = list(set((existing.tags or []) + (asset_in.tags or [])))
        meta = dict(existing.metadata_ or {})
        meta.update(asset_in.metadata or {})
        existing.metadata_ = meta
        return existing, False

    asset_id = asset_in.id or f"{org_id}-{asset_in.type}-{hash(asset_in.value)}"
    asset = models.Asset(
        id=asset_id,
        organization_id=org_id,
        type=asset_in.type,
        value=asset_in.value,
        status=asset_in.status,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        source=asset_in.source,
        tags=asset_in.tags,
        metadata_=asset_in.metadata,
    )
    db.add(asset)
    db.flush()
    return asset, True


def add_relationship(db: Session, org_id: str, source_id: str,
                     target_id: str, rel_type: str):
    existing = (
        db.query(models.AssetRelationship)
        .filter(
            models.AssetRelationship.organization_id == org_id,
            models.AssetRelationship.source_id == source_id,
            models.AssetRelationship.target_id == target_id,
            models.AssetRelationship.relationship_type == rel_type,
        )
        .first()
    )
    if existing:
        return existing
    rel = models.AssetRelationship(
        organization_id=org_id,
        source_id=source_id,
        target_id=target_id,
        relationship_type=rel_type,
    )
    db.add(rel)
    return rel


def filter_assets(db: Session, org_id: str,
                  flt: schemas.NLQueryFilter) -> list[models.Asset]:
    q = db.query(models.Asset).filter(
        models.Asset.organization_id == org_id)

    if flt.asset_type:
        q = q.filter(models.Asset.type == flt.asset_type)
    if flt.status:
        q = q.filter(models.Asset.status == flt.status)
    if flt.value_contains:
        q = q.filter(models.Asset.value.ilike(f"%{flt.value_contains}%"))
    for tag in flt.tags:
        # JSON containment (Postgres)
        q = q.filter(models.Asset.tags.contains([tag]))

    results = q.all()

    # metadata filters
    if flt.metadata_filters:
        filtered = []
        for a in results:
            meta = a.metadata_ or {}
            keep = True
            for k, v in flt.metadata_filters.items():
                if k == "expires_before":
                    val = meta.get("expires")
                    if val and val > v:
                        keep = False
                elif k == "expires_after":
                    val = meta.get("expires")
                    if val and val < v:
                        keep = False
                elif meta.get(k) != v:
                    keep = False
            if keep:
                filtered.append(a)
        results = filtered

    return results


def get_asset_graph(db: Session, asset_id: str, org_id: str,
                    depth: int = 1) -> dict:
    """Return an asset + its directly related assets."""
    asset = get_asset(db, asset_id, org_id)
    if not asset:
        return None
    related = []
    for rel in asset.outgoing:
        related.append({
            "asset_id": rel.target_id,
            "relationship": rel.relationship_type,
            "direction": "outgoing",
        })
    for rel in asset.incoming:
        related.append({
            "asset_id": rel.source_id,
            "relationship": rel.relationship_type,
            "direction": "incoming",
        })
    return {"asset": asset, "related": related}