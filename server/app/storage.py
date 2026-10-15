"""Cloud Storage: 업로드/다운로드용 서명 URL."""

from __future__ import annotations

from datetime import timedelta

import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage

from .config import Settings


class Storage:
    def __init__(self, s: Settings, client: storage.Client | None = None):
        self.s = s
        self.client = client or storage.Client(project=s.project_id or None)
        self.bucket = self.client.bucket(s.bucket)

    def _signing_kwargs(self) -> dict:
        # Cloud Run 에는 개인 키 파일이 없으므로 IAM signBlob 으로 서명한다.
        # (런타임 서비스 계정에 roles/iam.serviceAccountTokenCreator 가 필요)
        creds, _ = google.auth.default()
        if not creds.valid:
            creds.refresh(Request())
        email = self.s.signer_email or getattr(creds, "service_account_email", None)
        return {"service_account_email": email, "access_token": creds.token}

    def upload_url(self, object_name: str, content_type: str) -> str:
        return self.bucket.blob(object_name).generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=self.s.signed_url_minutes),
            method="PUT",
            content_type=content_type,
            **self._signing_kwargs(),
        )

    def download_url(self, object_name: str) -> str:
        return self.bucket.blob(object_name).generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=self.s.signed_url_minutes),
            method="GET",
            **self._signing_kwargs(),
        )

    def exists(self, object_name: str) -> bool:
        return self.bucket.blob(object_name).exists()

    def copy_from_url(self, url: str, object_name: str, content_type: str | None) -> int:
        """외부 URL의 파일을 버킷으로 가져온다. 바이트 수를 돌려준다."""
        import httpx

        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            blob = self.bucket.blob(object_name)
            ctype = content_type or r.headers.get("content-type", "application/octet-stream")
            with blob.open("wb", content_type=ctype) as f:
                size = 0
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    size += len(chunk)
        return size
