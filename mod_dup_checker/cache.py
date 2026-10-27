"""全量哈希缓存：{abspath: {size, mtime_ns, blake2b}}，原子写，失败静默降级。"""

from __future__ import annotations

import json
import os
import threading
import time

from .config import CACHE_FLUSH_INTERVAL


class DigestCache:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = {}
        self._dirty = 0
        self._last_flush = 0.0
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        data = {}
        for key, val in raw.items():
            if (
                isinstance(val, dict)
                and isinstance(val.get("size"), int)
                and isinstance(val.get("mtime_ns"), int)
                and isinstance(val.get("blake2b"), str)
            ):
                data[key] = val
        self._data = data

    def get(self, abspath, size, mtime_ns):
        item = self._data.get(abspath)
        if item and item.get("size") == size and item.get("mtime_ns") == mtime_ns:
            return item["blake2b"]
        return None

    def put(self, abspath, size, mtime_ns, digest):
        with self._lock:
            self._data[abspath] = {"size": size, "mtime_ns": mtime_ns, "blake2b": digest}
            self._dirty += 1
        now = time.monotonic()
        if self._dirty >= 256 or now - self._last_flush >= CACHE_FLUSH_INTERVAL:
            self.flush()

    def flush(self, force=False):
        with self._lock:
            if not self._dirty and not force:
                return
            payload = None if (not self._dirty and os.path.exists(self.path)) else dict(self._data)
            self._dirty = 0
            self._last_flush = time.monotonic()
        if payload is None:
            return
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, self.path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
