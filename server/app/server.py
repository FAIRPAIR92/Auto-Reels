"""Reels Studio MCP 서버: 도구 정의 (스펙 4장).

M1 범위: 연결 · 인증 · 소스 업로드 · 상태/목록 조회 · 완성본 URL 발급.
분석/생성/합성 도구는 자리만 잡아 두고, 각 마일스톤에서 채운다.
"""

from __future__ import annotations

import mimetypes
from typing import Annotated, Literal
from urllib.parse import quote

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from .auth import NotAllowed, build_auth, current_user
from .config import Settings
from .store import Store

INSTRUCTIONS = """\
Reels Studio는 인스타그램 릴스용 세로 영상을 만드는 편집 서버입니다.
순서: reels_upload_source 로 참고 영상과 내 소스를 올림 → reels_plan 으로 분석과 예상 비용 확인
→ 사용자가 '진행'이라고 하면 reels_render → reels_status 로 진행 확인 → reels_export 로 완성본 URL 받기.
reels_render 는 비용이 드는 작업이므로 사용자가 견적을 보고 승인하기 전에는 절대 호출하지 마세요.
"""

ALLOWED_MIME_PREFIXES = ("video/", "image/", "audio/")
MAX_SOURCE_IMAGES = 5

NOT_YET = {
    "reels_plan": "M2 (참고 영상 분석 · 비용 견적)",
    "reels_render": "M3 (장면 생성 · 합성)",
    "reels_revise": "M4 (부분 수정)",
    "reels_templates": "M5 (편집 템플릿)",
}


def _not_yet(tool: str) -> dict:
    return {
        "status": "not_implemented",
        "message": f"이 기능은 아직 준비 중입니다. 구현 단계: {NOT_YET[tool]}",
    }


def _public_asset(a: dict, uploaded: bool | None = None) -> dict:
    out = {k: a.get(k) for k in ("id", "kind", "filename", "mime", "size_bytes", "status")}
    out["created_at"] = a["created_at"].isoformat() if a.get("created_at") else None
    if uploaded is not None:
        out["uploaded"] = uploaded
    return out


def build_server(s: Settings, store: Store, storage) -> FastMCP:
    mcp = FastMCP("Reels Studio", instructions=INSTRUCTIONS, auth=build_auth(s))

    def user() -> str:
        try:
            return current_user(s)
        except NotAllowed as e:
            raise ToolError(str(e)) from e

    def owned_asset(asset_id: str, owner: str) -> dict:
        a = store.get_asset(asset_id)
        if not a or a["owner"] != owner:
            raise ToolError(f"소스를 찾을 수 없습니다: {asset_id}")
        return a

    def owned_job(job_id: str, owner: str) -> dict:
        j = store.get_job(job_id)
        if not j or j["owner"] != owner:
            raise ToolError(f"작업을 찾을 수 없습니다: {job_id}")
        return j

    def refresh_upload(a: dict) -> bool:
        """업로드 대기 중인 소스가 실제로 올라왔는지 확인하고 상태를 갱신한다."""
        if a.get("status") == "ready":
            return True
        if storage.exists(a["gcs_object"]):
            store.update_asset(a["id"], status="ready")
            a["status"] = "ready"
            return True
        return False

    @mcp.tool
    def reels_upload_source(
        kind: Annotated[Literal["reference", "source"], Field(description="reference=따라 할 참고 영상, source=내 클립·사진")],
        filename: Annotated[str, Field(description="파일 이름 (확장자 포함)")],
        source_url: Annotated[str | None, Field(description="파일이 이미 인터넷에 있으면 그 주소. 서버가 직접 가져온다")] = None,
        content_type: Annotated[str | None, Field(description="MIME 형식. 비우면 파일 이름으로 추정")] = None,
    ) -> dict:
        """참고 영상이나 내 소스를 등록한다. URL이 있으면 서버가 바로 가져오고,
        없으면 사용자가 파일을 올릴 수 있는 업로드 페이지 주소를 돌려준다."""
        owner = user()
        ctype = content_type or mimetypes.guess_type(filename)[0] or ""
        if not ctype.startswith(ALLOWED_MIME_PREFIXES):
            raise ToolError("영상 · 이미지 · 오디오 파일만 올릴 수 있습니다.")
        asset = store.create_asset(owner, kind, gcs_object="", mime=ctype, filename=filename, status="pending")
        obj = f"assets/{asset['id']}/{filename}"
        store.update_asset(asset["id"], gcs_object=obj)

        if source_url:
            try:
                size = storage.copy_from_url(source_url, obj, ctype)
            except Exception as e:  # noqa: BLE001 - 사용자에게 원인을 그대로 전달
                store.update_asset(asset["id"], status="failed")
                raise ToolError(f"URL에서 파일을 가져오지 못했습니다: {e}") from e
            store.update_asset(asset["id"], status="ready", size_bytes=size)
            return {"asset_id": asset["id"], "status": "ready", "size_bytes": size}

        put_url = storage.upload_url(obj, ctype)
        page = f"{s.base_url.rstrip('/')}/upload?u={quote(put_url, safe='')}&ct={quote(ctype, safe='')}&n={quote(filename, safe='')}"
        return {
            "asset_id": asset["id"],
            "status": "pending",
            "upload_page": page,
            "expires_in_minutes": s.signed_url_minutes,
            "next": "사용자에게 upload_page 링크를 열어 파일을 올리라고 안내한 뒤, reels_list_assets 로 uploaded=true 인지 확인하세요.",
        }

    @mcp.tool
    def reels_list_assets(
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict:
        """최근에 올린 소스와 작업 목록."""
        owner = user()
        assets = [_public_asset(a, refresh_upload(a)) for a in store.list_assets(owner, limit)]
        jobs = [
            {"job_id": j["id"], "status": j.get("status"), "versions": len(j.get("versions", [])),
             "created_at": j["created_at"].isoformat()}
            for j in store.list_jobs(owner, limit)
        ]
        return {"assets": assets, "jobs": jobs}

    @mcp.tool
    def reels_plan(
        reference_asset_id: str,
        source_asset_ids: list[str],
        max_seconds: Annotated[int, Field(ge=3, le=90)] = 30,
        aspect: Literal["9:16"] = "9:16",
        instructions: str = "",
    ) -> dict:
        """참고 영상을 분석해 편집 계획과 예상 비용을 만든다. 생성은 하지 않는다."""
        owner = user()
        ref = owned_asset(reference_asset_id, owner)
        srcs = [owned_asset(a, owner) for a in source_asset_ids]
        images = [a for a in srcs if a["mime"].startswith("image/")]
        if len(images) > MAX_SOURCE_IMAGES:
            raise ToolError(f"참고 이미지는 한 번에 {MAX_SOURCE_IMAGES}장까지입니다.")
        not_ready = [a["id"] for a in [ref, *srcs] if not refresh_upload(a)]
        if not_ready:
            raise ToolError(f"아직 업로드되지 않은 파일이 있습니다: {', '.join(not_ready)}")
        return _not_yet("reels_plan")

    @mcp.tool
    def reels_render(job_id: str, approval_token: str) -> dict:
        """승인된 계획대로 장면을 생성하고 완성본을 만든다 (과금). 사용자 승인 후에만 호출."""
        owned_job(job_id, user())
        return _not_yet("reels_render")

    @mcp.tool
    def reels_status(job_id: str) -> dict:
        """작업 진행 상태와 자동 검사 결과."""
        j = owned_job(job_id, user())
        return {
            "job_id": j["id"],
            "status": j.get("status"),
            "progress": j.get("progress"),
            "estimate": j.get("estimate"),
            "versions": [
                {k: v.get(k) for k in ("v", "duration", "size_bytes", "checks")} for v in j.get("versions", [])
            ],
            "error": j.get("error"),
        }

    @mcp.tool
    def reels_revise(job_id: str, change: str) -> dict:
        """'바꿀 점 한 줄'로 수정 계획과 견적을 만든다."""
        owned_job(job_id, user())
        return _not_yet("reels_revise")

    @mcp.tool
    def reels_export(job_id: str, version: int | None = None) -> dict:
        """완성본(과 커버)의 다운로드 URL을 발급한다. uplika media_from_url 에 그대로 넘길 수 있다."""
        j = owned_job(job_id, user())
        versions = j.get("versions", [])
        if not versions:
            raise ToolError("아직 완성본이 없습니다.")
        v = versions[-1] if version is None else next((x for x in versions if x["v"] == version), None)
        if not v:
            raise ToolError(f"버전 {version} 이 없습니다.")
        out = {"job_id": j["id"], "version": v["v"], "video_url": storage.download_url(v["final_object"]),
               "duration": v.get("duration"), "size_bytes": v.get("size_bytes"),
               "expires_in_minutes": s.signed_url_minutes}
        if v.get("cover_object"):
            out["cover_url"] = storage.download_url(v["cover_object"])
        return out

    @mcp.tool
    def reels_templates(action: Literal["list", "save", "apply"], template_id: str | None = None) -> dict:
        """자주 쓰는 편집 스타일을 저장하고 다시 쓴다."""
        user()
        return _not_yet("reels_templates")

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request):
        return JSONResponse({"ok": True})

    @mcp.custom_route("/upload", methods=["GET"])
    async def upload_page(_: Request):
        return HTMLResponse(UPLOAD_PAGE)

    return mcp


# 서명된 PUT 주소로 브라우저에서 바로 올리는 한 장짜리 페이지.
# 주소 자체가 권한이므로 서버는 파일을 거치지 않는다.
UPLOAD_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reels Studio 업로드</title>
<style>
body{font-family:system-ui,sans-serif;max-width:480px;margin:40px auto;padding:0 16px;color:#222}
button{padding:10px 16px;font-size:16px}#msg{margin-top:16px}progress{width:100%}
</style></head><body>
<h2>파일 올리기</h2>
<p id="name"></p>
<input type="file" id="f"><br><br>
<button id="go">올리기</button>
<progress id="p" value="0" max="100" hidden></progress>
<div id="msg"></div>
<script>
const q=new URLSearchParams(location.search);const url=q.get('u'),ct=q.get('ct'),n=q.get('n');
document.getElementById('name').textContent='등록한 파일: '+(n||'');
document.getElementById('go').onclick=()=>{
  const file=document.getElementById('f').files[0];const msg=document.getElementById('msg');
  if(!file){msg.textContent='파일을 먼저 고르세요.';return;}
  const x=new XMLHttpRequest();const p=document.getElementById('p');p.hidden=false;
  x.upload.onprogress=e=>{if(e.lengthComputable)p.value=e.loaded/e.total*100;};
  x.onload=()=>{msg.textContent=x.status<300?'올라갔어요. 클로드 대화로 돌아가 "올렸어"라고 말해 주세요.':'실패했어요 ('+x.status+'). 링크가 만료됐을 수 있어요.';};
  x.onerror=()=>{msg.textContent='네트워크 오류로 실패했어요.';};
  x.open('PUT',url);x.setRequestHeader('Content-Type',ct);x.send(file);
};
</script></body></html>
"""
