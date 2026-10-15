"""Google OAuth 로그인과 허용 사용자 검사."""

from __future__ import annotations

from cryptography.fernet import Fernet
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.auth.jwt_issuer import derive_jwt_key
from key_value.aio.stores.firestore import FirestoreStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from .config import Settings

LOCAL_USER = "local-dev"


class NotAllowed(PermissionError):
    pass


def build_auth(s: Settings) -> GoogleProvider | None:
    if not s.auth_enabled:
        return None
    missing = [
        name
        for name, value in [
            ("GOOGLE_OAUTH_CLIENT_ID", s.google_client_id),
            ("GOOGLE_OAUTH_CLIENT_SECRET", s.google_client_secret),
            ("JWT_SIGNING_KEY", s.jwt_signing_key),
            ("ALLOWED_EMAILS", ",".join(s.allowed_emails)),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"인증 설정이 비어 있습니다: {', '.join(missing)}")

    # claude.ai 가 등록한 OAuth 클라이언트 정보는 Firestore에 암호화해 보관한다.
    # Cloud Run 인스턴스가 바뀌어도 다시 로그인할 필요가 없도록 하기 위함.
    storage_key = derive_jwt_key(
        high_entropy_material=s.jwt_signing_key, salt="reels-studio-client-storage"
    )
    client_storage = FernetEncryptionWrapper(
        key_value=FirestoreStore(project=s.project_id or None, default_collection="oauth_clients"),
        fernet=Fernet(key=storage_key),
        raise_on_decryption_error=False,
    )
    return GoogleProvider(
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        base_url=s.base_url,
        required_scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
        jwt_signing_key=s.jwt_signing_key,
        client_storage=client_storage,
    )


def current_user(s: Settings) -> str:
    """요청한 사용자의 이메일. 허용 목록에 없으면 NotAllowed."""
    if not s.auth_enabled:
        return LOCAL_USER
    token = get_access_token()
    email = (token.claims.get("email") or "").lower() if token else ""
    if not email or email not in s.allowed_emails:
        raise NotAllowed("이 계정은 Reels Studio 사용이 허용되지 않았습니다.")
    return email
