"""Cloud Run 진입점: uvicorn app.main:app"""

from __future__ import annotations

from .config import settings
from .server import build_server


def _build():
    if settings.disable_auth and not settings.bucket:
        # 로컬 개발: GCP 없이 메모리 저장소로 띄운다.
        from .store import MemoryStore

        class _NoStorage:
            def exists(self, _):
                return False

            def upload_url(self, obj, _ct):
                return f"http://localhost/fake-upload/{obj}"

            def download_url(self, obj):
                return f"http://localhost/fake-download/{obj}"

            def copy_from_url(self, *_):
                raise RuntimeError("로컬 모드에서는 URL 가져오기를 지원하지 않습니다")

        return build_server(settings, MemoryStore(), _NoStorage())

    from .storage import Storage
    from .store import FirestoreStore

    return build_server(settings, FirestoreStore(settings.project_id), Storage(settings))


mcp = _build()
app = mcp.http_app(path="/mcp")
