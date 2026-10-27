"""全量哈希缓存：快照 JSON + 追加日志，读盘只在扫描线程里发生。

写入路径只做内存字典操作 + 日志追加，绝不重写整个快照；日志长到一定程度才压实
（重写快照并清空日志）。加载时先读快照再重放日志，等于启动即压实。
失败一律静默降级：缓存坏了只是下次重算，不能让扫描挂掉。
"""

from __future__ import annotations

import json
import os
import threading
import time

from .config import CACHE_FLUSH_INTERVAL, CACHE_VERSION

# 日志里攒够这么多行就落盘一次
JOURNAL_BATCH = 256
# 日志追加行数超过「快照条目数」的这么多倍就压实一次，避免日志无限长
COMPACT_RATIO = 2
COMPACT_MIN_LINES = 4096
# 压实前先剔除已经不存在的老条目；条目数超过这个量才做全量探测
PRUNE_THRESHOLD = 5000


def _valid_entry(val):
    return (
        isinstance(val, dict)
        and isinstance(val.get("size"), int)
        and isinstance(val.get("mtime_ns"), int)
        and isinstance(val.get("blake2b"), str)
    )


class DigestCache:
    def __init__(self, path, journal_path=None):
        self.path = path
        self.journal_path = journal_path or (path + ".journal")
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()   # 同一时刻只有一个线程写盘
        self._data = {}
        self._pending = []                    # 待追加的日志行
        self._appended = 0                    # 上次压实以来追加的行数
        self._last_flush = 0.0
        self._loaded = False

    # -- 读 --------------------------------------------------------------
    def load(self):
        """读快照 + 重放日志。只在扫描线程里调一次。"""
        data = self._load_snapshot()
        appended = self._replay_journal(data)
        with self._lock:
            self._data = data
            self._appended = appended
            self._loaded = True

    def _load_snapshot(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return {}
        # 兼容两种格式：{"v":1,"items":{...}} 与更早的扁平 {路径: {...}}
        items = raw.get("items") if isinstance(raw, dict) else None
        if not isinstance(items, dict):
            items = raw if isinstance(raw, dict) else {}
        return {k: v for k, v in items.items() if _valid_entry(v)}

    def _replay_journal(self, data):
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return 0
        replayed = 0
        for line in lines:
            try:
                key, size, mtime_ns, digest = json.loads(line)
            except Exception:
                continue                          # 崩溃时可能留下半行
            if isinstance(key, str) and isinstance(digest, str):
                data[key] = {"size": size, "mtime_ns": mtime_ns, "blake2b": digest}
                replayed += 1
        return replayed

    def get(self, abspath, size, mtime_ns):
        with self._lock:
            item = self._data.get(abspath)
            if item is not None and item.get("size") == size and item.get("mtime_ns") == mtime_ns:
                return item["blake2b"]
            return None

    # -- 写 --------------------------------------------------------------
    def put(self, abspath, size, mtime_ns, digest):
        now = time.monotonic()
        with self._lock:
            if not self._loaded:                  # 没走 load() 的调用方（测试等）直接可用
                self._loaded = True
            self._data[abspath] = {"size": size, "mtime_ns": mtime_ns, "blake2b": digest}
            self._pending.append([abspath, size, mtime_ns, digest])
            due = len(self._pending) >= JOURNAL_BATCH or now - self._last_flush >= CACHE_FLUSH_INTERVAL
        if due:
            self.flush()

    def flush(self, force=False, compact=False):
        """把待写日志落盘；需要时压实成快照。多个线程同时调用是安全的。"""
        with self._flush_lock:
            with self._lock:
                lines, self._pending = self._pending, []
                entries = len(self._data)
                pending_total = self._appended + len(lines)   # 上次压实以来累计追加的行
                if not lines and not force and not compact:
                    return
                need_compact = (
                    compact
                    or pending_total > COMPACT_MIN_LINES
                    or pending_total >= max(entries, 1) * COMPACT_RATIO
                )
                snapshot = None
                if need_compact:
                    snapshot = self._prune(dict(self._data)) if entries > PRUNE_THRESHOLD else dict(self._data)
                self._last_flush = time.monotonic()

            if lines:
                try:
                    os.makedirs(os.path.dirname(self.path), exist_ok=True)
                    with open(self.journal_path, "a", encoding="utf-8") as f:
                        f.writelines(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n"
                                     for line in lines)
                except Exception:                 # 写不进去就留在内存里下次再说
                    with self._lock:
                        self._pending[:0] = lines
                    return
                with self._lock:
                    self._appended += len(lines)
            if snapshot is not None:
                self._write_snapshot(snapshot)
                # 快照已包含全部日志内容，可以清空日志
                try:
                    if os.path.exists(self.journal_path):
                        os.remove(self.journal_path)
                except Exception:
                    pass
                with self._lock:
                    self._appended = 0

    def _prune(self, data):
        """剔除文件已经不在的条目，顺手把缓存控制在合理规模。"""
        alive = {}
        for key, val in data.items():
            try:
                if os.path.exists(key):
                    alive[key] = val
            except Exception:
                alive[key] = val
        return alive

    def _write_snapshot(self, data):
        tmp = "%s.%d.tmp" % (self.path, os.getpid())
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"v": CACHE_VERSION, "items": data}, f,
                          ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, self.path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
