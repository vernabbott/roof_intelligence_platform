import json
import unittest
from unittest.mock import patch

from supabase_tenant_worker import SupabaseTenantWorker, SupabaseWorkerError


class _Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class SupabaseTenantWorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker = SupabaseTenantWorker("http://127.0.0.1:54321", "sb_secret_test-worker-key")

    def test_publishable_key_is_rejected(self):
        with self.assertRaisesRegex(SupabaseWorkerError, "service-role"):
            SupabaseTenantWorker("http://127.0.0.1:54321", "sb_publishable_not-a-worker")

    def test_claim_requires_tenant_on_returned_job(self):
        with patch.object(self.worker, "_request", return_value=[{
            "id": "job-id", "job_type": "individual_address", "input": {}
        }]):
            with self.assertRaisesRegex(SupabaseWorkerError, "tenant ownership"):
                self.worker.claim_job("worker-1")

    def test_claim_uses_tenant_from_database_row(self):
        with patch.object(self.worker, "_request", return_value=[{
            "id": "job-id",
            "tenant_id": "tenant-id",
            "job_type": "individual_address",
            "input": {"property_address": "101 Test Ave"},
        }]):
            claimed = self.worker.claim_job("worker-1")
        self.assertEqual(claimed.tenant_id, "tenant-id")
        self.assertEqual(claimed.payload["property_address"], "101 Test Ave")

    def test_storage_path_uses_report_tenant_and_folder(self):
        with patch.object(self.worker, "_request", return_value=[{
            "id": "report-id", "tenant_id": "tenant-id", "report_folder_id": "folder-id"
        }]):
            path = self.worker.storage_path_for_report("report-id", 2, "../report.pdf")
        self.assertEqual(
            path,
            "tenant-id/folders/folder-id/reports/report-id/revisions/2/report.pdf",
        )


if __name__ == "__main__":
    unittest.main()

