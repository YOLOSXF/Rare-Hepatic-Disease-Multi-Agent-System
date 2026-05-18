"""
LLM调用缓存

职责：
1. 缓存LLM知识抽取结果，避免重复调用
2. 基于输入文本哈希作为缓存键
3. 支持JSON持久化存储
4. 提供TTL过期机制
5. 提供异步接口兼容Gleaning循环

使用示例：
    from core.kg.kg_cache import KGCache
    cache = KGCache(ttl_seconds=86400)
    result = cache.get("some text hash")
    if result is None:
        result = await llm_extract(text)
        cache.put("some text hash", result)
"""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


class KGCache:
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        ttl_seconds: Optional[int] = 86400,
    ):
        if cache_dir is None:
            project_root = Path(__file__).parent.parent.parent
            cache_dir = str(project_root / "data" / "kg_cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0

    @staticmethod
    def compute_key(text: str, model_name: str = "") -> str:
        raw = f"{model_name}::{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        if self.ttl_seconds is None:
            return False
        created_at = entry.get("_created_at", 0)
        return (time.time() - created_at) > self.ttl_seconds

    def _wrap_with_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **data,
            "_created_at": time.time(),
        }

    def _unwrap_metadata(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self._is_expired(entry):
            return None
        return {k: v for k, v in entry.items() if not k.startswith("_")}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            result = self._unwrap_metadata(entry)
            if result is not None:
                self._hits += 1
                logger.debug(f"Cache hit (memory): {key}")
                return result
            else:
                del self._memory_cache[key]
                logger.debug(f"Cache expired (memory): {key}")

        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                result = self._unwrap_metadata(entry)
                if result is not None:
                    self._memory_cache[key] = entry
                    self._hits += 1
                    logger.debug(f"Cache hit (disk): {key}")
                    return result
                else:
                    cache_file.unlink()
                    logger.debug(f"Cache expired (disk): {key}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Cache read error for {key}: {e}")

        self._misses += 1
        return None

    async def aget(self, key: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self.get, key)

    def put(self, key: str, data: Dict[str, Any]) -> None:
        entry = self._wrap_with_metadata(data)
        self._memory_cache[key] = entry
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            logger.debug(f"Cache write: {key}")
        except IOError as e:
            logger.error(f"Cache write error for {key}: {e}")

    async def aput(self, key: str, data: Dict[str, Any]) -> None:
        await asyncio.to_thread(self.put, key, data)

    def has(self, key: str) -> bool:
        result = self.get(key)
        return result is not None

    def invalidate(self, key: str) -> bool:
        removed = False
        if key in self._memory_cache:
            del self._memory_cache[key]
            removed = True
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            cache_file.unlink()
            removed = True
        return removed

    def clear(self) -> int:
        count = len(self._memory_cache)
        self._memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        logger.info(f"Cache cleared: {count} entries removed")
        return count

    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        disk_count = len(list(self.cache_dir.glob("*.json")))
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "memory_entries": len(self._memory_cache),
            "disk_entries": disk_count,
            "ttl_seconds": self.ttl_seconds,
        }

    def batch_get(self, keys: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        return {key: self.get(key) for key in keys}

    async def abatch_get(self, keys: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        tasks = [self.aget(key) for key in keys]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = {}
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                logger.error(f"Async cache get failed for {key}: {result}")
                output[key] = None
            else:
                output[key] = result
        return output

    def batch_put(self, items: Dict[str, Dict[str, Any]]) -> None:
        for key, data in items.items():
            self.put(key, data)

    async def abatch_put(self, items: Dict[str, Dict[str, Any]]) -> None:
        tasks = [self.aput(key, data) for key, data in items.items()]
        await asyncio.gather(*tasks, return_exceptions=True)
