"""Firestore 데이터 접근 (jobs, assets). 스펙 7장 데이터 모델."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Protocol


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Store(Protocol):
    def create_asset(self, owner: str, kind: str, gcs_object: str, mime: str, **extra: Any) -> dict: ...
    def get_asset(self, asset_id: str) -> dict | None: ...
    def update_asset(self, asset_id: str, **fields: Any) -> None: ...
    def list_assets(self, owner: str, limit: int) -> list[dict]: ...
    def create_job(self, owner: str, **fields: Any) -> dict: ...
    def get_job(self, job_id: str) -> dict | None: ...
    def update_job(self, job_id: str, **fields: Any) -> None: ...
    def list_jobs(self, owner: str, limit: int) -> list[dict]: ...


class FirestoreStore:
    def __init__(self, project_id: str | None = None, client=None):
        from google.cloud import firestore

        self.db = client or firestore.Client(project=project_id or None)
        self._desc = firestore.Query.DESCENDING

    def _create(self, coll: str, prefix: str, data: dict) -> dict:
        doc_id = new_id(prefix)
        data = {"id": doc_id, "created_at": now(), **data}
        self.db.collection(coll).document(doc_id).set(data)
        return data

    def _get(self, coll: str, doc_id: str) -> dict | None:
        snap = self.db.collection(coll).document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def _list(self, coll: str, owner: str, limit: int) -> list[dict]:
        q = (
            self.db.collection(coll)
            .where("owner", "==", owner)
            .order_by("created_at", direction=self._desc)
            .limit(limit)
        )
        return [d.to_dict() for d in q.stream()]

    def create_asset(self, owner, kind, gcs_object, mime, **extra):
        return self._create("assets", "ast", {"owner": owner, "kind": kind, "gcs_object": gcs_object, "mime": mime, **extra})

    def get_asset(self, asset_id):
        return self._get("assets", asset_id)

    def update_asset(self, asset_id, **fields):
        self.db.collection("assets").document(asset_id).update(fields)

    def list_assets(self, owner, limit):
        return self._list("assets", owner, limit)

    def create_job(self, owner, **fields):
        return self._create("jobs", "job", {"owner": owner, "versions": [], **fields})

    def get_job(self, job_id):
        return self._get("jobs", job_id)

    def update_job(self, job_id, **fields):
        self.db.collection("jobs").document(job_id).update({**fields, "updated_at": now()})

    def list_jobs(self, owner, limit):
        return self._list("jobs", owner, limit)


class MemoryStore:
    """테스트·로컬 개발용 메모리 저장소."""

    def __init__(self):
        self.assets: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}

    def create_asset(self, owner, kind, gcs_object, mime, **extra):
        a = {"id": new_id("ast"), "created_at": now(), "owner": owner, "kind": kind, "gcs_object": gcs_object, "mime": mime, **extra}
        self.assets[a["id"]] = a
        return a

    def get_asset(self, asset_id):
        return self.assets.get(asset_id)

    def update_asset(self, asset_id, **fields):
        self.assets[asset_id].update(fields)

    def list_assets(self, owner, limit):
        items = [a for a in self.assets.values() if a["owner"] == owner]
        return sorted(items, key=lambda a: a["created_at"], reverse=True)[:limit]

    def create_job(self, owner, **fields):
        j = {"id": new_id("job"), "created_at": now(), "owner": owner, "versions": [], **fields}
        self.jobs[j["id"]] = j
        return j

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def update_job(self, job_id, **fields):
        self.jobs[job_id].update(fields, updated_at=now())

    def list_jobs(self, owner, limit):
        items = [j for j in self.jobs.values() if j["owner"] == owner]
        return sorted(items, key=lambda j: j["created_at"], reverse=True)[:limit]
