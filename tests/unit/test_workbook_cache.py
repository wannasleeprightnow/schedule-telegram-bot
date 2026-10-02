import asyncio
import json
import time

import httpx
import pytest

from src.infrastructure.cache.workbook_cache import WorkbookCache


class FakeResponse:
    content = b"PK-test-xlsx-content"

    def raise_for_status(self):
        return None


class FakeClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url):
        type(self).calls += 1
        await asyncio.sleep(0.03)
        return FakeResponse()


@pytest.mark.asyncio
async def test_simultaneous_requests_share_one_download(tmp_path, monkeypatch):
    FakeClient.calls = 0
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    cache = WorkbookCache("https://example.invalid/schedule.xlsx", tmp_path, 180)
    results = await asyncio.gather(*(cache.get() for _ in range(5)))
    assert FakeClient.calls == 1
    assert all(result.sha256 == results[0].sha256 for result in results)
    assert json.loads((tmp_path / "metadata.json").read_text())["sha256"] == results[0].sha256


@pytest.mark.asyncio
async def test_cache_expires_and_redownloads(tmp_path, monkeypatch):
    FakeClient.calls = 0
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    cache = WorkbookCache("https://example.invalid/schedule.xlsx", tmp_path, 180)
    first = await cache.get()
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    metadata["downloaded_at"] = time.time() - 181
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    second = await cache.get()
    assert FakeClient.calls == 2
    assert not first.stale and not second.stale


@pytest.mark.asyncio
async def test_failure_reports_error_without_cached_file(tmp_path, monkeypatch):
    class FailedClient(FakeClient):
        async def get(self, url):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "AsyncClient", FailedClient)
    cache = WorkbookCache("https://example.invalid/schedule.xlsx", tmp_path, 180)
    with pytest.raises(RuntimeError):
        await cache.get()


@pytest.mark.asyncio
async def test_stale_cache_is_used_only_when_explicitly_enabled(tmp_path, monkeypatch):
    class FailedClient(FakeClient):
        async def get(self, url):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "AsyncClient", FailedClient)
    cache = WorkbookCache("https://example.invalid/schedule.xlsx", tmp_path, 180, allow_stale=True)
    cache.cache_dir.mkdir(parents=True, exist_ok=True)
    cache.file_path.write_bytes(b"PK-cached")
    (tmp_path / "metadata.json").write_text(json.dumps({"downloaded_at": time.time() - 200}))
    result = await cache.get()
    assert result.stale is True
