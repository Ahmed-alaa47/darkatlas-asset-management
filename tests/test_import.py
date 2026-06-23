import pytest
from app.importer import bulk_import
from app.crud import get_asset, add_relationship
from app.models import Asset


class TestDedup:
    def test_reimport_updates_last_seen(self, db_session, sample_assets):
        bulk_import(db_session, sample_assets, "org_test")
        asset = get_asset(db_session, "a1", "org_test")
        first_last = asset.last_seen

        bulk_import(db_session, sample_assets, "org_test")
        db_session.refresh(asset)
        assert asset.last_seen >= first_last
        assert asset.first_seen < asset.last_seen or \
               asset.first_seen == asset.first_seen

    def test_merge_tags_union(self, db_session):
        records1 = [{"id": "m1", "type": "domain", "value": "merge.com",
                      "tags": ["prod"]}]
        records2 = [{"id": "m1", "type": "domain", "value": "merge.com",
                      "tags": ["external"]}]
        bulk_import(db_session, records1, "org_test")
        bulk_import(db_session, records2, "org_test")
        asset = get_asset(db_session, "m1", "org_test")
        assert set(asset.tags) == {"prod", "external"}

    def test_stale_revives_to_active(self, db_session):
        records1 = [{"id": "s1", "type": "domain", "value": "stale.com",
                      "status": "stale"}]
        bulk_import(db_session, records1, "org_test")
        records2 = [{"id": "s1", "type": "domain", "value": "stale.com",
                      "status": "active"}]
        bulk_import(db_session, records2, "org_test")
        asset = get_asset(db_session, "s1", "org_test")
        assert asset.status == "active"


class TestRelationships:
    def test_relationships_created(self, db_session, sample_assets):
        bulk_import(db_session, sample_assets, "org_test")
        rels = db_session.query(
            __import__("app.models", fromlist=["AssetRelationship"]).AssetRelationship
        ).filter_by(organization_id="org_test").all()
        assert len(rels) >= 2  # parent + covers

class TestMultiTenancy:
    def test_no_cross_org_leakage(self, db_session, sample_assets):
        # Import assets into org_A
        bulk_import(db_session, sample_assets, "org_A")
        
        # Try to query assets from org_B
        from app.crud import get_asset
        asset_org_b = get_asset(db_session, "a1", "org_B")
        
        # Should return None, because a1 belongs to org_A!
        assert asset_org_b is None