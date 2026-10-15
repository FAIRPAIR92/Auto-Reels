import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app.config import Settings
from app.server import build_server
from app.store import MemoryStore


class FakeStorage:
    def __init__(self):
        self.objects: set[str] = set()

    def exists(self, obj):
        return obj in self.objects

    def upload_url(self, obj, ct):
        return f"https://storage.example/{obj}?put"

    def download_url(self, obj):
        return f"https://storage.example/{obj}?get"

    def copy_from_url(self, url, obj, ct):
        self.objects.add(obj)
        return 1234


@pytest.fixture
def env():
    s = Settings(disable_auth=True, base_url="https://reels.example")
    store, storage = MemoryStore(), FakeStorage()
    return build_server(s, store, storage), store, storage


async def call(mcp, name, **args):
    async with Client(mcp) as c:
        return (await c.call_tool(name, args)).data


async def test_lists_all_spec_tools(env):
    mcp, *_ = env
    async with Client(mcp) as c:
        names = {t.name for t in await c.list_tools()}
    assert names == {
        "reels_upload_source", "reels_list_assets", "reels_plan", "reels_render",
        "reels_status", "reels_revise", "reels_export", "reels_templates",
    }


async def test_upload_without_url_returns_upload_page(env):
    mcp, store, storage = env
    out = await call(mcp, "reels_upload_source", kind="source", filename="clip.mp4")
    assert out["status"] == "pending"
    assert out["upload_page"].startswith("https://reels.example/upload?u=")

    listed = await call(mcp, "reels_list_assets")
    assert listed["assets"][0]["uploaded"] is False

    storage.objects.add(store.get_asset(out["asset_id"])["gcs_object"])
    listed = await call(mcp, "reels_list_assets")
    assert listed["assets"][0]["uploaded"] is True


async def test_upload_from_url_is_ready(env):
    mcp, *_ = env
    out = await call(mcp, "reels_upload_source", kind="reference", filename="ref.mov", source_url="https://x/ref.mov")
    assert out == {"asset_id": out["asset_id"], "status": "ready", "size_bytes": 1234}


async def test_rejects_non_media(env):
    mcp, *_ = env
    with pytest.raises(ToolError, match="영상"):
        await call(mcp, "reels_upload_source", kind="source", filename="notes.txt")


async def test_plan_requires_uploaded_files(env):
    mcp, *_ = env
    ref = await call(mcp, "reels_upload_source", kind="reference", filename="ref.mp4")
    with pytest.raises(ToolError, match="업로드되지 않은"):
        await call(mcp, "reels_plan", reference_asset_id=ref["asset_id"], source_asset_ids=[])


async def test_plan_limits_images(env):
    mcp, *_ = env
    ref = await call(mcp, "reels_upload_source", kind="reference", filename="r.mp4", source_url="https://x/r")
    imgs = [
        (await call(mcp, "reels_upload_source", kind="source", filename=f"{i}.jpg", source_url="https://x/i"))["asset_id"]
        for i in range(6)
    ]
    with pytest.raises(ToolError, match="5장"):
        await call(mcp, "reels_plan", reference_asset_id=ref["asset_id"], source_asset_ids=imgs)


async def test_export_returns_signed_urls(env):
    mcp, store, _ = env
    job = store.create_job("local-dev", status="done")
    store.update_job(job["id"], versions=[{"v": 1, "final_object": "jobs/x/final/v1.mp4", "cover_object": "jobs/x/cover.jpg", "duration": 28.5}])
    out = await call(mcp, "reels_export", job_id=job["id"])
    assert out["video_url"].endswith("v1.mp4?get")
    assert out["cover_url"].endswith("cover.jpg?get")


async def test_other_users_job_is_hidden(env):
    mcp, store, _ = env
    job = store.create_job("someone@else.com", status="done")
    with pytest.raises(ToolError, match="찾을 수 없습니다"):
        await call(mcp, "reels_status", job_id=job["id"])
