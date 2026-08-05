from pathlib import Path
import unittest


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260805162011_normalize_proposal_tracking.sql"
)


class ProposalTrackingNormalizationMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_tracking_is_a_one_to_one_extension_of_proposal(self):
        self.assertIn("create table public.proposal_tracking (", self.sql)
        self.assertIn("proposal_id uuid primary key", self.sql)
        self.assertIn(
            "foreign key (tenant_id, proposal_id)",
            self.sql,
        )
        self.assertIn(
            "references public.proposal(tenant_id, id) on delete cascade",
            self.sql,
        )

    def test_tracking_data_is_copied_before_redundant_columns_are_removed(self):
        copy_position = self.sql.index("insert into public.proposal_tracking")
        drop_position = self.sql.index("drop column lead_source")
        self.assertLess(copy_position, drop_position)
        for column in (
            "lead_source", "submitted_by", "estimated_by",
            "estimate_completed_date", "proposal_sent_date", "follow_up_date",
            "response_notes", "status", "source_name", "source_row_number",
        ):
            self.assertIn(f"drop column {column}", self.sql)
        for retained_column in (
            "customer_name", "project_street_address", "project_city",
            "project_state", "project_zip_code", "proposal_folder_name",
        ):
            self.assertNotIn(f"drop column {retained_column}", self.sql)

    def test_tracking_has_tenant_rls_privileges_and_queue_indexes(self):
        self.assertIn(
            "alter table public.proposal_tracking enable row level security",
            self.sql,
        )
        self.assertIn("private.user_has_tenant_access(tenant_id)", self.sql)
        self.assertIn("proposal_tracking_tenant_status_sent_idx", self.sql)
        self.assertIn("proposal_tracking_tenant_follow_up_queue_idx", self.sql)
        self.assertIn(
            "grant select, insert, update, delete on public.proposal_tracking to authenticated",
            self.sql,
        )


if __name__ == "__main__":
    unittest.main()
