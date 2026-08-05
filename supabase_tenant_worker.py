"""Tenant-safe Supabase adapter for the protected PilotPoint worker.

The service role is permitted only in this worker process. Tenant identity is
always loaded from a claimed job or report row and is never accepted as a CLI
argument, form field, or storage-path prefix supplied by a user.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SupabaseWorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaimedTenantJob:
    job_id: str
    tenant_id: str
    job_type: str
    payload: dict
    raw: dict


class SupabaseTenantWorker:
    def __init__(self, project_url: str, service_role_key: str):
        if not project_url or not service_role_key:
            raise SupabaseWorkerError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
        if service_role_key.startswith("sb_publishable_"):
            raise SupabaseWorkerError("The protected worker requires a service-role secret, not a publishable key.")
        self.project_url = project_url.rstrip("/")
        self.service_role_key = service_role_key

    @classmethod
    def from_environment(cls) -> "SupabaseTenantWorker":
        return cls(
            os.environ.get("SUPABASE_URL", "").strip(),
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        )

    def _request(self, path: str, *, method: str = "GET", params=None, payload=None, headers=None):
        query = f"?{urlencode(params, doseq=True)}" if params else ""
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(headers or {}),
        }
        request = Request(
            f"{self.project_url}/{path.lstrip('/')}{query}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                message = json.loads(exc.read().decode("utf-8")).get("message", "")
            except Exception:
                message = ""
            raise SupabaseWorkerError(message or f"Supabase worker request failed ({exc.code}).") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise SupabaseWorkerError("PilotPoint could not connect to Supabase.") from exc
        return json.loads(raw.decode("utf-8")) if raw else []

    def claim_job(self, worker_name: str, lease_seconds: int = 300) -> ClaimedTenantJob | None:
        clean_worker = " ".join(str(worker_name or "").split())
        if not clean_worker:
            raise SupabaseWorkerError("worker_name is required.")
        rows = self._request(
            "rest/v1/rpc/claim_roof_intelligence_job",
            method="POST",
            payload={"worker_name": clean_worker, "lease_seconds": int(lease_seconds)},
        )
        if not rows:
            return None
        row = rows[0]
        tenant_id = str(row.get("tenant_id") or "")
        if not tenant_id:
            raise SupabaseWorkerError("Claimed job has no trusted tenant ownership.")
        return ClaimedTenantJob(
            job_id=str(row["id"]),
            tenant_id=tenant_id,
            job_type=str(row["job_type"]),
            payload=dict(row.get("input") or {}),
            raw=dict(row),
        )

    def storage_path_for_report(
        self,
        report_id: str,
        revision_number: int,
        filename: str,
    ) -> str:
        """Build a path from the trusted report row, never from caller tenant input."""
        clean_filename = PurePosixPath(str(filename or "")).name
        if not clean_filename or clean_filename in {".", ".."}:
            raise SupabaseWorkerError("A storage filename is required.")
        rows = self._request(
            "rest/v1/roof_intelligence_reports",
            params={
                "select": "id,tenant_id,report_folder_id",
                "id": f"eq.{report_id}",
                "limit": "1",
            },
        )
        if not rows:
            raise SupabaseWorkerError("The report was not found.")
        report = rows[0]
        tenant_id = str(report.get("tenant_id") or "")
        folder_id = str(report.get("report_folder_id") or "")
        if not tenant_id or not folder_id:
            raise SupabaseWorkerError("The report has no tenant-owned folder.")
        return (
            f"{tenant_id}/folders/{folder_id}/reports/{report['id']}/"
            f"revisions/{int(revision_number)}/{clean_filename}"
        )

    def upload_report_asset(
        self,
        bucket: str,
        storage_path: str,
        content: bytes,
        mime_type: str,
    ) -> None:
        if bucket not in {"roof-intelligence-reports", "roof-intelligence-images"}:
            raise SupabaseWorkerError("Unsupported Roof Intelligence storage bucket.")
        request = Request(
            f"{self.project_url}/storage/v1/object/{bucket}/{storage_path}",
            data=content,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Content-Type": mime_type,
                "x-upsert": "false",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=120):
                return
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise SupabaseWorkerError("The tenant-namespaced report asset upload failed.") from exc


__all__ = ["ClaimedTenantJob", "SupabaseTenantWorker", "SupabaseWorkerError"]

