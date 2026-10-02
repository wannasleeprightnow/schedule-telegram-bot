import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedWorkbook:
    path: Path
    stale: bool
    sha256: str


class WorkbookCache:
    def __init__(self, source_url: str, cache_dir: Path, ttl: int = 180, allow_stale: bool = True):
        self.source_url = source_url
        self.cache_dir = cache_dir
        self.file_path = cache_dir / "schedule.xlsx"
        self.metadata_path = cache_dir / "metadata.json"
        self.ttl = ttl
        self.allow_stale = allow_stale
        self._lock = asyncio.Lock()

    async def get(self) -> CachedWorkbook:
        async with self._lock:
            if self._is_fresh():
                digest = self._read_metadata().get("sha256") or await asyncio.to_thread(_file_hash, self.file_path)
                logger.info("Используется XLSX-кэш, возраст менее %s секунд", self.ttl)
                return CachedWorkbook(self.file_path, False, digest)
            logger.info("TTL XLSX-кэша истёк или кэш отсутствует")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            last_error: Exception | None = None
            for attempt in range(2):
                try:
                    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
                        response = await client.get(self.source_url)
                        response.raise_for_status()
                    if not response.content.startswith(b"PK"):
                        raise ValueError("Источник вернул файл, который не похож на XLSX")
                    temp_path = self.file_path.with_suffix(".tmp")
                    await asyncio.to_thread(temp_path.write_bytes, response.content)
                    os.replace(temp_path, self.file_path)
                    digest = hashlib.sha256(response.content).hexdigest()
                    self.metadata_path.write_text(json.dumps({"downloaded_at": time.time(), "sha256": digest}, ensure_ascii=False), encoding="utf-8")
                    logger.info("XLSX загружен (%d байт)", len(response.content))
                    return CachedWorkbook(self.file_path, False, digest)
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    last_error = exc
                    logger.warning("Ошибка загрузки XLSX, попытка %d/2: %s", attempt + 1, exc)
                    if attempt == 0:
                        await asyncio.sleep(0.35)
            if self.file_path.exists() and self.allow_stale:
                logger.warning("Используется устаревшая версия XLSX после ошибки загрузки")
                metadata = self._read_metadata()
                digest = metadata.get("sha256") or await asyncio.to_thread(_file_hash, self.file_path)
                return CachedWorkbook(self.file_path, True, digest)
            raise RuntimeError("Не удалось получить актуальное расписание из Google Sheets") from last_error

    def _is_fresh(self) -> bool:
        if not self.file_path.exists():
            return False
        metadata = self._read_metadata()
        downloaded_at = metadata.get("downloaded_at")
        return isinstance(downloaded_at, (int, float)) and time.time() - downloaded_at < self.ttl

    def _read_metadata(self) -> dict:
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
