"""환경 변수 기반 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(value: str | None) -> list[str]:
    return [v.strip().lower() for v in (value or "").split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    project_id: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    bucket: str = field(default_factory=lambda: os.environ.get("REELS_BUCKET", ""))
    # Cloud Run 서비스의 공개 주소. OAuth 콜백 주소를 만드는 데 쓴다.
    base_url: str = field(default_factory=lambda: os.environ.get("BASE_URL", "http://localhost:8080"))
    google_client_id: str = field(default_factory=lambda: os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""))
    google_client_secret: str = field(default_factory=lambda: os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""))
    jwt_signing_key: str = field(default_factory=lambda: os.environ.get("JWT_SIGNING_KEY", ""))
    allowed_emails: list[str] = field(default_factory=lambda: _csv(os.environ.get("ALLOWED_EMAILS")))
    # 서명 URL을 만들 때 쓸 서비스 계정 (Cloud Run 런타임 서비스 계정)
    signer_email: str = field(default_factory=lambda: os.environ.get("SIGNER_SERVICE_ACCOUNT", ""))
    signed_url_minutes: int = field(default_factory=lambda: int(os.environ.get("SIGNED_URL_MINUTES", "60")))
    # 로컬 개발용: 인증을 끈다. 배포 환경에서는 절대 켜지 않는다.
    disable_auth: bool = field(default_factory=lambda: os.environ.get("DISABLE_AUTH") == "1")

    @property
    def auth_enabled(self) -> bool:
        return not self.disable_auth


settings = Settings()
