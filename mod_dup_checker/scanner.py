"""扫描任务：三级校验流程、结果组装、取消、单任务注册表。"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import traceback
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .cache import DigestCache
from .config import CACHE_FILE, CACHE_JOURNAL, DEFAULT_JOBS, FULL_CHUNK
from .discovery import discover_mods, list_natives_files
from .errors import Cancelled
from .paths import long_path
from .progress import Progress
from .signatures import (
    SAMPLE_DIGEST_SIZE,
    combine_mod_sig,
    sample_file_digest,
    structure_sig,
)

FULL_DIGEST_SIZE = 32
MAX_WARNINGS = 500          # 脏目录下警告可能上千条，超出部分只计数不再保存

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Mod:
    """一个待比较的 mod。字段在流水线各阶段逐步填上，用属性避免字典键手滑。"""

    path: str
    name: str
    natives: str
    root_index: int
    rel_depth: int
    index: int = -1
    files: list = field(default_factory=list)
    bytes: int = 0
    struct: str = ""
    sig: str = ""
    partial: bool = False


class ScanJob:
    def __init__(self, job_id, roots, jobs=None):
        self.id = job_id
        self.roots = [r for r in roots if isinstance(r, str) and r.strip()]
        try:
            jobs = int(jobs) if jobs else DEFAULT_JOBS
        except (TypeError, ValueError):
            jobs = DEFAULT_JOBS
        self.jobs = max(1, min(jobs, 64))

        self.prog = Progress()
        self.lock = threading.Lock()
        self.cancel_evt = threading.Event()

        self.warnings = []
        self.partial_mods = []
        self.empty_mods = []
        self.groups = []
        self.stats = {
            "mods": 0, "unique": 0, "dup_mods": 0, "empty": 0,
            "reclaimable_bytes": 0, "elapsed_ms": 0, "files": 0, "bytes": 0,
            "cancelled": False,
            "phase_times_ms": {},
        }
        self.mods_total = 0
        self.natives_files_total = 0
        self.natives_bytes_total = 0

        self.error = None
        self.cancelled = False
        self.finished = False
        self.t0 = time.perf_counter()
        self.phase_times = {}
        # 缓存在扫描线程里才加载：8 MB 的 JSON 不该卡住 HTTP 请求线程
        self.cache = None
        self.cache_hits = 0
        self._physical = {}
        self._physical_lock = threading.Lock()

    # -- 公共 ------------------------------------------------------------
    def cancel(self):
        self.cancel_evt.set()

    def _warn(self, msg):
        with self.lock:
            if len(self.warnings) >= MAX_WARNINGS:
                return
            self.warnings.append(msg)
        log.warning("%s", msg)

    def _count_hit(self):
        with self.lock:
            self.cache_hits += 1

    def run(self):
        try:
            self._open_cache()
            self._run()
        except Cancelled:
            self.cancelled = True
            self._warn("扫描已取消：以下结论可能不完整（未经内容全量校验的组按「疑似重复」处理）。")
        except Exception as exc:  # noqa: BLE001 - 用户目录任何异常都不能崩
            self.error = "扫描失败：%s" % exc
            self._warn(self.error)
            log.debug("%s", traceback.format_exc())
        finally:
            self._close_cache()
            self._build_stats()
            self.prog.set_label("已取消" if self.cancelled else "完成")
            self.finished = True

    def _open_cache(self):
        self.cache = DigestCache(CACHE_FILE, CACHE_JOURNAL)
        self.cache.load()

    def _close_cache(self):
        if self.cache is None:
            return
        try:
            self.cache.flush(force=True, compact=True)
        except Exception:  # noqa: BLE001 - 缓存写不进去不影响结论
            pass

    # -- 主流程 ----------------------------------------------------------
    def _run(self):
        t = time.perf_counter()
        self.prog.start_phase("扫描结构", 0)

        raw_mods, warns = discover_mods(self.roots, self.cancel_evt)
        for w in warns:
            self._warn(w)
        mods = [
            Mod(path=d["path"], name=d["name"], natives=d["natives"],
                root_index=d["root_index"], rel_depth=d["rel_depth"])
            for d in raw_mods
        ]
        self.mods_total = len(mods)
        self.prog.set_mods(0, len(mods))

        if not mods:
            self._warn("未找到任何 mod：mod 根目录 = 自身含有 natives 子目录的目录。")
            self._sort_groups()
            return

        self.prog.start_phase("扫描结构", len(mods))
        self._list_natives(mods)

        for i, m in enumerate(mods):
            m.index = i

        self.natives_files_total = sum(len(m.files) for m in mods)
        self.natives_bytes_total = sum(m.bytes for m in mods)
        self.phase_times["structure"] = time.perf_counter() - t

        if self.cancel_evt.is_set():
            raise Cancelled()

        # 第 1 级分组
        buckets = defaultdict(list)
        for m in mods:
            if m.partial:
                continue
            if not m.files:
                with self.lock:
                    self.empty_mods.append(m.path)
                continue
            buckets[m.struct].append(m)
        candidates = [g for g in buckets.values() if len(g) > 1]
        if not candidates:
            self.groups = []
            return

        # 第 2 级
        t2 = time.perf_counter()
        sample_groups, cached_groups = self._sample_stage(candidates)
        self.phase_times["sample"] = time.perf_counter() - t2
        # 中间结论：取消时用得着；采样通过的只是「疑似重复」，靠缓存定论的已是全量级
        self.groups = [self._make_group(g, "structure") for g in sample_groups]
        self.groups += [self._make_group(g, "content") for g in cached_groups]
        self._sort_groups()

        if not sample_groups:
            return

        # 第 3 级
        t3 = time.perf_counter()
        content_groups = self._full_stage(sample_groups)
        self.phase_times["full"] = time.perf_counter() - t3
        self.groups = [self._make_group(g, "content") for g in content_groups]
        self.groups += [self._make_group(g, "content") for g in cached_groups]
        self._sort_groups()

    def _list_natives(self, mods):
        """第 0 步：并发枚举每个 mod 的 natives/，只读元数据。"""
        executor = ThreadPoolExecutor(max_workers=self.jobs, thread_name_prefix="modscan")
        try:
            futures = [executor.submit(list_natives_files, m.natives, self.cancel_evt) for m in mods]
            for i, (m, fut) in enumerate(zip(mods, futures)):
                files, problems = fut.result()
                m.files = files
                m.bytes = sum(t[1] for t in files)
                m.struct = structure_sig(files)
                if problems:
                    m.partial = True
                    for problem in problems:
                        self._warn("无法读取（%s）：%s" % (m.path, problem))
                    with self.lock:
                        self.partial_mods.append(m.path)
                self.prog.set_mods(i + 1, len(mods))
                self.prog.bump(1)
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    # -- 第 2 / 3 级：同一套流程，只换单文件摘要算法 ----------------------
    def _verify_stage(self, groups, task_fn, digest_size, phase, order_by_size=False):
        """对每组内的每个文件算摘要，再按「路径+大小+摘要」重新分桶。

        返回仍然有多个成员的组；读不出来的 mod 直接踢出本组。
        """
        tasks = []
        for gi, group in enumerate(groups):
            for m in group:
                for tup in m.files:
                    tasks.append((gi, m, tup))
        if order_by_size:
            tasks.sort(key=lambda t: -t[2][1])   # 大文件先开工，IO 更饱满
        self.prog.start_phase(phase, len(tasks))

        executor = ThreadPoolExecutor(max_workers=self.jobs, thread_name_prefix="verify")
        try:
            digests = list(executor.map(task_fn, tasks))
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        per_mod = defaultdict(list)
        failed = set()
        for (_gi, m, _tup), digest in zip(tasks, digests):
            if digest is None:
                failed.add(m.index)
            else:
                per_mod[m.index].append(digest)

        out = []
        for group in groups:
            buckets = defaultdict(list)
            for m in group:
                if m.index in failed or m.partial:
                    continue
                ds = per_mod.get(m.index, [])
                if len(ds) != len(m.files):
                    continue
                m.sig = combine_mod_sig(digest_size, m.files, ds)
                buckets[m.sig].append(m)
            out.extend(members for members in buckets.values() if len(members) > 1)
        return out

    def _sample_stage(self, candidates):
        """第 2 级。返回 (仍需采样的组, 已经能按缓存全量摘要定论的组)。"""
        todo = []
        resolved = []
        for group in candidates:
            sigs = [self._cached_sig(m) for m in group]
            if any(sig is None for sig in sigs):
                todo.append(group)
                continue
            buckets = defaultdict(list)
            for m, sig in zip(group, sigs):
                m.sig = sig
                buckets[sig].append(m)
            resolved.extend(members for members in buckets.values() if len(members) > 1)

        groups = self._verify_stage(todo, self._sample_task, SAMPLE_DIGEST_SIZE, "采样校验")
        return groups, resolved

    def _cached_sig(self, mod):
        """整只 mod 的全量摘要都能从缓存拼出来时返回签名，否则 None。"""
        digests = []
        for _rel, size, path, mtime_ns, _nlink in mod.files:
            digest = self.cache.get(path, size, mtime_ns)
            if digest is None:
                return None
            digests.append(digest)
        self._count_hit()
        return combine_mod_sig(FULL_DIGEST_SIZE, mod.files, digests)

    def _full_stage(self, sample_groups):
        return self._verify_stage(sample_groups, self._full_task, FULL_DIGEST_SIZE,
                                  "全量校验", order_by_size=True)

    def _fail_mod(self, mod, path, exc):
        self._warn("无法读取文件，该 mod 不参与重复判定：%s（%s）" % (path, exc.strerror or exc))
        mod.partial = True

    def _sample_task(self, task):
        if self.cancel_evt.is_set():
            raise Cancelled()
        _gi, mod, (rel, size, path, _mtime_ns, _nlink) = task
        try:
            digest, read = sample_file_digest(rel, size, path)
        except OSError as exc:
            self._fail_mod(mod, path, exc)
            return None
        self.prog.bump(1, read)
        return digest

    def _full_task(self, task):
        if self.cancel_evt.is_set():
            raise Cancelled()
        _gi, mod, (rel, size, path, mtime_ns, nlink) = task
        cached = self.cache.get(path, size, mtime_ns)
        if cached is not None:
            self._count_hit()
            self.prog.bump(1, 0)
            return cached

        key = os.path.realpath(path) if nlink > 1 else None   # 只对可能的硬链接做这层映射
        if key is not None:
            with self._physical_lock:
                known = self._physical.get(key)
            if known is not None:
                self._count_hit()
                self.cache.put(path, size, mtime_ns, known)
                self.prog.bump(1, 0)
                return known

        try:
            digest, read = self._hash_file(path)
        except OSError as exc:
            self._fail_mod(mod, path, exc)
            return None

        if key is not None:
            with self._physical_lock:
                self._physical[key] = digest
        self.cache.put(path, size, mtime_ns, digest)
        self.prog.bump(1, read)
        return digest

    def _hash_file(self, path):
        h = hashlib.blake2b(digest_size=FULL_DIGEST_SIZE)
        read = 0
        with open(long_path(path), "rb", buffering=0) as f:
            while True:
                if self.cancel_evt.is_set():
                    raise Cancelled()
                chunk = f.read(FULL_CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                read += len(chunk)
        return h.hexdigest(), read

    # -- 结果 ------------------------------------------------------------
    def _make_group(self, members, kind):
        # 成员顺序即「默认保留」优先级：先看是第几个扫描目录扫到的（先填的赢），
        # 再看相对该目录埋得多深（越上层越优先），最后才按路径字母序。
        members = sorted(members, key=lambda m: (m.root_index, m.rel_depth, m.path.lower()))
        member_bytes = members[0].bytes
        count = len(members)
        return {
            "id": 0,
            "kind": kind,
            "count": count,
            "member_bytes": member_bytes,
            "reclaimable_bytes": member_bytes * (count - 1),
            "structure_sig": members[0].struct,
            "members": [
                {
                    "path": m.path,
                    "files": len(m.files),
                    "bytes": m.bytes,
                    "mod_name": m.name,
                }
                for m in members
            ],
        }

    def _sort_groups(self):
        groups = sorted(
            self.groups,
            key=lambda g: (-g["reclaimable_bytes"], g["members"][0]["path"].lower()),
        )
        for i, g in enumerate(groups, 1):
            g["id"] = i
        with self.lock:
            self.groups = groups

    def _build_stats(self):
        with self.lock:
            groups = list(self.groups)
            empty = list(self.empty_mods)
            warnings = list(self.warnings)
            cache_hits = self.cache_hits
        dup = sum(g["count"] for g in groups)
        self.stats = {
            "mods": self.mods_total,
            "unique": max(0, self.mods_total - dup - len(empty)),
            "dup_mods": dup,
            "empty": len(empty),
            "reclaimable_bytes": sum(g["reclaimable_bytes"] for g in groups),
            "elapsed_ms": int((time.perf_counter() - self.t0) * 1000),
            "files": self.natives_files_total,
            "bytes": self.natives_bytes_total,
            "bytes_read": self.prog.snapshot()["bytes_read"],
            "cache_hits": cache_hits,
            "cancelled": self.cancelled,
            "phase_times_ms": {k: int(v * 1000) for k, v in self.phase_times.items()},
            "warnings": len(warnings),
        }

    def status(self):
        snap = self.prog.snapshot()
        with self.lock:
            warnings = self.warnings[-200:]
            cancelled = self.cancelled
        return {
            "job_id": self.id,
            "phase": snap["phase"],
            "scanned_mods": snap["scanned_mods"],
            "total_mods": snap["total_mods"],
            "files_done": snap["phase_done"],
            "files_total": snap["phase_total"],
            "bytes_read": snap["bytes_read"],
            "elapsed_ms": (self.stats.get("elapsed_ms", 0) if self.finished
                           else int((time.perf_counter() - self.t0) * 1000)),
            "warnings": warnings,
            "done": self.finished,
            "error": self.error,
            "cancelled": cancelled or self.cancel_evt.is_set(),
        }

    def result(self):
        with self.lock:
            groups = [dict(g) for g in self.groups]
            empty = list(self.empty_mods)
            warnings = list(self.warnings)
            partial = list(self.partial_mods)
        return {
            "groups": groups,
            "stats": dict(self.stats),
            "empty_mods": empty,
            "partial_mods": partial,
            "warnings": warnings,
            "cancelled": self.cancelled,
            "done": self.finished,
        }


class Registry:
    """同一时刻只允许一个扫描任务。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._job = None

    def start(self, roots, jobs):
        with self._lock:
            if self._job is not None and not self._job.finished:
                return None
            job = ScanJob(uuid.uuid4().hex[:12], roots, jobs)
            self._job = job
        thread = threading.Thread(target=job.run, name="scan-job", daemon=True)
        thread.start()
        return job

    def get(self, job_id=None):
        with self._lock:
            job = self._job
        if job is None:
            return None
        if job_id and job.id != job_id:
            return None
        return job


REGISTRY = Registry()
