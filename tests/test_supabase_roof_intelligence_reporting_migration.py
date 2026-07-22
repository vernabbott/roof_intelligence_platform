import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
MIGRATION = (
    PROJECT_DIR
    / "supabase"
    / "migrations"
    / "20260722000100_create_roof_intelligence_reporting.sql"
)
CUTOVER_MIGRATION = (
    PROJECT_DIR
    / "supabase"
    / "migrations"
    / "20260722000200_prepare_roof_intelligence_cutover.sql"
)


class RoofIntelligenceReportingMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_creates_revision_ready_reporting_contract(self):
        required_tables = (
            "roof_intelligence_properties",
            "roof_intelligence_jobs",
            "roof_intelligence_job_items",
            "roof_intelligence_reports",
            "roof_intelligence_report_revisions",
            "roof_intelligence_report_assets",
            "roof_intelligence_notifications",
            "roof_intelligence_county_health_checks",
        )
        for table in required_tables:
            self.assertIn(f"create table public.{table}", self.sql)

        for snapshot in (
            "source_snapshot jsonb",
            "analysis_snapshot jsonb",
            "calculated_snapshot jsonb",
            "render_snapshot jsonb",
        ):
            self.assertIn(snapshot, self.sql)

    def test_ready_revisions_are_immutable_and_not_human_approval(self):
        self.assertIn("validate_roof_report_revision_lineage", self.sql)
        self.assertIn("prevent_ready_roof_report_revision_changes", self.sql)
        self.assertIn("prevent_ready_roof_report_asset_changes", self.sql)
        self.assertIn("ready does not imply human review or approval", self.sql)
        self.assertNotIn("approval_status", self.sql)

    def test_private_storage_and_locked_down_rls_are_declared(self):
        self.assertIn("('roof-intelligence-reports', 'roof-intelligence-reports', false)", self.sql)
        self.assertIn("('roof-intelligence-images', 'roof-intelligence-images', false)", self.sql)
        self.assertIn("enable row level security", self.sql)
        self.assertNotIn("create policy", self.sql)

    def test_migration_does_not_import_legacy_test_data(self):
        self.assertNotIn("insert into public.roof_intelligence_reports", self.sql)
        self.assertNotIn("roof_ai_analysis_cache", self.sql)
        self.assertNotIn("roof_intelligence_jobs.sqlite3", self.sql)


class RoofIntelligenceCutoverMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = CUTOVER_MIGRATION.read_text(encoding="utf-8").lower()

    def test_adds_approved_override_and_retention_contracts(self):
        self.assertIn("create table public.roof_intelligence_property_overrides", self.sql)
        self.assertIn("field_name = 'roof_area_sqft'", self.sql)
        self.assertIn("interval '90 days'", self.sql)
        self.assertIn("edit_patch jsonb", self.sql)

    def test_adds_service_only_atomic_worker_claim(self):
        self.assertIn("for update skip locked", self.sql)
        self.assertIn("lease_expires_at", self.sql)
        self.assertIn("revoke all on function", self.sql)
        self.assertIn("to service_role", self.sql)

    def test_cutover_migration_does_not_add_client_policies(self):
        self.assertIn("enable row level security", self.sql)
        self.assertNotIn("create policy", self.sql)


if __name__ == "__main__":
    unittest.main()
