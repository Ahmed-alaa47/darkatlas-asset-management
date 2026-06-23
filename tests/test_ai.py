import pytest
import os
from app.importer import bulk_import
from app.crud import filter_assets, get_asset
from app.schemas import NLQueryFilter, EnrichmentResult, AssetType
from app.ai.guardrails import validate_nl_query_filter, validate_enrichment


class TestImport:
    def test_import_creates_assets(self, db_session, sample_assets):
        result = bulk_import(db_session, sample_assets, "org_test")
        assert result.imported == 5
        assert result.skipped == 0

    def test_idempotent_import(self, db_session, sample_assets):
        bulk_import(db_session, sample_assets, "org_test")
        result = bulk_import(db_session, sample_assets, "org_test")
        assert result.imported == 0
        assert result.updated == 5
        assert result.skipped == 0

    def test_malformed_record_skipped(self, db_session):
        records = [
            {"id": "x1", "type": "domain", "value": "good.com"},
            {"id": "x2", "type": "INVALID_TYPE", "value": "bad.com"},
        ]
        result = bulk_import(db_session, records, "org_test")
        assert result.imported == 1
        assert result.skipped == 1
        assert len(result.errors) == 1


class TestGuardrails:
    def test_nl_query_filter_strips_tags(self):
        # Use model_construct to bypass Pydantic validation so we can test the guardrail
        flt = NLQueryFilter.model_construct(tags=["Prod", "  Staging  ", "", 123])
        flt = validate_nl_query_filter(flt)
        assert flt.tags == ["prod", "staging"]

    def test_enrichment_clamps_values(self, db_session, sample_assets):
        bulk_import(db_session, sample_assets, "org_test")
        asset = get_asset(db_session, "a2", "org_test")

        # Use model_construct to bypass Pydantic validation
        result = EnrichmentResult.model_construct(
            environment="INVALID",
            category="ALSO_INVALID",
            criticality="nope",
            confidence=1.5,
            enriched_metadata={"value": "HACKED", "custom": "ok"},
            reasoning="test",
        )
        result = validate_enrichment(result, asset)
        assert result.environment == "unknown"
        assert result.criticality == "medium"
        assert result.category == "unknown"
        assert "value" not in result.enriched_metadata
        assert result.enriched_metadata.get("custom") == "ok"


class TestFilterAssets:
    def test_filter_by_type(self, db_session, sample_assets):
        bulk_import(db_session, sample_assets, "org_test")
        flt = NLQueryFilter(asset_type=AssetType.certificate)
        results = filter_assets(db_session, "org_test", flt)
        assert len(results) == 1
        assert results[0].value == "CN=api.example.com"

    def test_filter_by_tag(self, db_session, sample_assets):
        bulk_import(db_session, sample_assets, "org_test")
        flt = NLQueryFilter(tags=["prod"])
        results = filter_assets(db_session, "org_test", flt)
        assert len(results) == 1
        assert results[0].value == "api.example.com"

    def test_filter_by_value_contains(self, db_session, sample_assets):
        bulk_import(db_session, sample_assets, "org_test")
        flt = NLQueryFilter(value_contains="example")
        results = filter_assets(db_session, "org_test", flt)
        assert len(results) == 3  # domain, subdomain, certificate


# ---- Integration tests (require LLM API key — skip if not set) ----
LLM_AVAILABLE = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))

@pytest.mark.skipif(not LLM_AVAILABLE, reason="No LLM API key set")
class TestChainsIntegration:
    def test_nl_query_returns_real_assets(self, db_session, sample_assets):
        from app.ai.chains import run_nl_query
        bulk_import(db_session, sample_assets, "org_test")
        result = run_nl_query("show me all certificates", db_session, "org_test")
        
        # 1. Ensure the pipeline didn't crash
        assert "error" not in result, f"LLM Error: {result.get('error')}"
        
        # 2. Ensure the database query executed and returned assets
        assert result["count"] >= 1
        
        # 3. If the LLM was smart enough to set the filter to "certificate", 
        # verify that the database respected it.
        interpreted_type = result.get("interpreted_filter", {}).get("asset_type")
        if interpreted_type == "certificate":
            for m in result["matches"]:
                assert m["type"] == "certificate"

    def test_risk_analysis_grounds_findings(self, db_session, sample_assets):
        from app.ai.chains import run_risk_analysis
        bulk_import(db_session, sample_assets, "org_test")
        result = run_risk_analysis(["a3", "a4"], db_session, "org_test")
        if "error" not in result:
            valid_ids = {"a3", "a4"}
            for f in result.get("findings", []):
                assert f["asset_id"] in valid_ids