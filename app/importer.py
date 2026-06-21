from sqlalchemy.orm import Session
from app import crud, schemas
from app.models import Asset


REL_MAP = {
    "parent": "subdomain_of",
    "covers": "covers",
    "resolves_to": "resolves_to",
    "runs_on": "runs_on",
}


def bulk_import(db: Session, records: list[dict],
                org_id: str) -> schemas.ImportResult:
    imported = updated = skipped = 0
    errors = []

    # First pass: upsert all assets (collect id mappings)
    id_map = {}  

    for i, rec in enumerate(records):
        try:
            asset_in = schemas.AssetIn(**rec)
            asset, created = crud.upsert_asset(db, asset_in, org_id)
            if asset_in.id:
                id_map[asset_in.id] = asset.id
            if created:
                imported += 1
            else:
                updated += 1
        except Exception as e:
            skipped += 1
            errors.append({"index": i, "record": rec, "error": str(e)})

    # Second pass: relationships
    for rec in records:
        try:
            asset_in = schemas.AssetIn(**rec)
            source_db_id = id_map.get(asset_in.id) or asset_in.id
            if not source_db_id:
                continue
            for field, rel_type in REL_MAP.items():
                target_ref = getattr(asset_in, field, None)
                if not target_ref:
                    continue
                targets = target_ref if isinstance(target_ref, list) else [target_ref]
                for t in targets:
                    target_db_id = id_map.get(t) or t
                    # confirm target exists in this org
                    target = db.query(Asset).filter(
                        Asset.id == target_db_id,
                        Asset.organization_id == org_id,
                    ).first()
                    if target:
                        crud.add_relationship(
                            db, org_id, source_db_id, target_db_id, rel_type)
        except Exception:
            pass  # relationship errors are non-fatal

    db.commit()
    return schemas.ImportResult(
        imported=imported, updated=updated,
        skipped=skipped, errors=errors,
    )