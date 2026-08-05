from pathlib import Path
import unittest


MIGRATION = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "20260805145432_add_multi_tenant_foundation.sql"


class SupabaseMultiTenantMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_creates_tenant_membership_roles_settings_and_report_folders(self):
        for declaration in (
            "create table public.tenant (",
            "create table public.tenant_membership (",
            "create table public.tenant_settings (",
            "create table public.tenant_feature_flag (",
            "create table public.report_folder (",
        ):
            self.assertIn(declaration, self.sql)
        self.assertIn("'owner', 'admin', 'sales', 'estimator', 'viewer'", self.sql)

    def test_large_reference_datasets_are_not_tenant_duplicated(self):
        self.assertNotIn("alter table public.building_footprints add column tenant_id", self.sql)
        self.assertNotIn("alter table public.canonical_building_footprints add column tenant_id", self.sql)
        self.assertNotIn("alter table public.roof_intelligence_properties add column tenant_id", self.sql)

    def test_business_and_report_records_have_required_tenant_ownership(self):
        for table in (
            "contact", "organization", "organization_contact", "proposal",
            "proposal_contact", "roof_intelligence_jobs", "roof_intelligence_reports",
            "roof_intelligence_report_revisions", "roof_intelligence_report_assets",
        ):
            self.assertIn(f"alter table public.{table} add column tenant_id", self.sql)
            self.assertIn(f"alter table public.{table} alter column tenant_id set not null", self.sql)

    def test_rls_and_storage_paths_are_tenant_scoped(self):
        self.assertIn("private.user_has_tenant_access(tenant_id)", self.sql)
        self.assertIn("private.user_has_tenant_role", self.sql)
        self.assertIn("create policy tenant_storage_read", self.sql)
        self.assertIn("membership.tenant_id::text = (storage.foldername(name))[1]", self.sql)
        self.assertIn("validate_tenant_storage_path", self.sql)
        self.assertIn("'/folders/'", self.sql)

    def test_worker_derives_tenant_from_trusted_parent_records(self):
        self.assertIn("create or replace function private.set_job_tenant()", self.sql)
        self.assertIn("create or replace function private.set_report_tenant_and_folder()", self.sql)
        self.assertIn("create or replace function private.set_tenant_from_parent()", self.sql)
        self.assertIn("validate_edit_request_actor", self.sql)


if __name__ == "__main__":
    unittest.main()

