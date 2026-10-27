"""扫描任务：三级校验流程、结果组装、取消、单任务注册表。"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import time
import traceback
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .cache import DigestCache
from .config import CACHE_FILE, DEFAULT_JOBS, FULL_CHUNK
from .discovery import discover_mods, list_natives_files
from .errors import Cancelled
from .paths import long_path
from .progress import Progress
from .signatures import combine_mod_sig, sample_file_digest, structure_sig


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
        self.cache = DigestCache(CACHE_FILE)
        self._physical = {}
        self._physical_lock = threading.Lock()

    # -- 公共 ------------------------------------------------------------
    def cancel(self):
        self.cancel_evt.set()

    def _warn(self, msg):
        with self.lock:
            self.warnings.append(msg)
        print("[warning] %s" % msg, file=sys.stderr)

    def run(self):
        try:
            self._run()
        except Cancelled:
            self.cancelled = True
            self._warn("扫描已取消：以下结论可能不完整（未经内容全量校验的组按「疑似重复」处理）。")
        except Exception as exc:  # noqa: BLE001 - 用户目录任何异常都不能崩
            self.error = "扫描失败：%s" % exc
            self._warn(self.error)
            traceback.print_exc()
        finally:
            try:
                self.cache.flush(force=True)
            except Exception:
                pass
            self._build_stats()
            self.prog.set_label("已取消" if self.cancelled else "完成")
            self.finished = True

    # -- 主流程 ----------------------------------------------------------
    def _run(self):
        t = time.perf_counter()
        self.prog.start_phase("扫描结构", 0)

        mods, warns = discover_mods(self.roots, self.cancel_evt)
        for w in warns:
            self._warn(w)
        self.mods_total = len(mods)
        self.prog.set_mods(0, len(mods))

        if not mods:
            self._warn("未找到任何 mod：mod 根目录 = 自身含有 natives 子目录的目录。")
            self._sort_groups()
            return

        self.prog.start_phase("扫描结构", len(mods))
        executor = ThreadPoolExecutor(max_workers=self.jobs, thread_name_prefix="modscan")
        try:
            futures = [executor.submit(list_natives_files, m["natives"], self.cancel_evt) for m in mods]
            for i, (m, fut) in enumerate(zip(mods, futures)):
                files, problems = fut.result()
                m["files"] = files
                m["bytes"] = sum(sz for _r, sz, _p, _mt in files)
                m["struct"] = structure_sig(files)
                m["partial"] = bool(problems)
                for problem in problems:
                    self._warn("无法读取（%s）：%s" % (m["path"], problem))
                if problems:
                    with self.lock:
                        self.partial_mods.append(m["path"])
                self.prog.set_mods(i + 1, len(mods))
                self.prog.bump(1)
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        for m in mods:
            m["idx"] = id(m)

        self.natives_files_total = sum(len(m["files"]) for m in mods)
        self.natives_bytes_total = sum(m["bytes"] for m in mods)
        self.phase_times["structure"] = time.perf_counter() - t

        if self.cancel_evt.is_set():
            raise Cancelled()

        # 第 1 级分组
        buckets = defaultdict(list)
        for m in mods:
            if m["partial"]:
                continue
            if not m["files"]:
                with self.lock:
                    self.empty_mods.append(m["path"])
                continue
            buckets[m["struct"]].append(m)
        candidates = [g for g in buckets.values() if len(g) > 1]

        if not candidates:
            self.groups = []
            return

        # 第 2 级
        t2 = time.perf_counter()
        sample_groups = self._sample_stage(candidates)
        self.phase_times["sample"] = time.perf_counter() - t2
        # 中间结论：取消时用得着，但只是「疑似重复」
        self.groups = [self._make_group(g, "structure") for g in sample_groups]
        self._sort_groups()

        if not sample_groups:
            return

        # 第 3 级
        t3 = time.perf_counter()
        content_groups = self._full_stage(sample_groups)
        self.phase_times["full"] = time.perf_counter() - t3
        self.groups = [self._make_group(g, "content") for g in content_groups]
        self._sort_groups()

    # -- 第 2 级 ---------------------------------------------------------
    def _sample_stage(self, candidates):
        tasks = []
        for gi, group in enumerate(candidates):
            for m in group:
                for tup in m["files"]:
                    tasks.append((gi, m, tup))
        self.prog.start_phase("采样校验", len(tasks))

        digests = []
        executor = ThreadPoolExecutor(max_workers=self.jobs, thread_name_prefix="sample")
        try:
            for res in executor.map(self._sample_task, tasks):
                digests.append(res)
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        per_mod = defaultdict(list)
        failed = set()
        for (gi, m, tup), digest in zip(tasks, digests):
            if digest is None:
                failed.add(id(m))
            else:
                per_mod[id(m)].append(digest)

        out = []
        for gi, group in enumerate(candidates):
            buckets = defaultdict(list)
            for m in group:
                if id(m) in failed or m.get("partial"):
                    continue
                ds = per_mod.get(id(m), [])
                if len(ds) != len(m["files"]):
                    continue
                m["sample_sig"] = combine_mod_sig(16, m["files"], ds)
                buckets[m["sample_sig"]].append(m)
            for members in buckets.values():
                if len(members) > 1:
                    out.append(members)
        return out

    def _sample_task(self, task):
        if self.cancel_evt.is_set():
            raise Cancelled()
        _gi, m, (rel, size, path, _mt) = task
        try:
            digest, read = sample_file_digest(rel, size, path)
        except OSError as exc:
            self._warn("无法读取文件，该 mod 不参与重复判定：%s（%s）" % (path, exc.strerror or exc))
            m["partial"] = True
            return None
        self.prog.bump(1, read, path)
        return digest

    # -- 第 3 级 ---------------------------------------------------------
    def _full_stage(self, sample_groups):
        tasks = []
        for gi, group in enumerate(sample_groups):
            for m in group:
                for tup in m["files"]:
                    tasks.append((gi, m, tup))
        tasks.sort(key=lambda t: -t[2][1])  # 大文件先开工，IO 更饱满
        self.prog.start_phase("全量校验", len(tasks))

        digests = []
        executor = ThreadPoolExecutor(max_workers=self.jobs, thread_name_prefix="fullhash")
        try:
            for res in executor.map(self._full_task, tasks):
                digests.append(res)
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        per_mod = defaultdict(list)
        failed = set()
        for (gi, m, tup), digest in zip(tasks, digests):
            if digest is None:
                failed.add(id(m))
            else:
                per_mod[id(m)].append(digest)

        out = []
        for gi, group in enumerate(sample_groups):
            buckets = defaultdict(list)
            for m in group:
                if id(m) in failed or m.get("partial"):
                    continue
                ds = per_mod.get(id(m), [])
                if len(ds) != len(m["files"]):
                    continue
                buckets[combine_mod_sig(32, m["files"], ds)].append(m)
            for members in buckets.values():
                if len(members) > 1:
                    out.append(members)
        return out

    def _full_task(self, task):
        if self.cancel_evt.is_set():
            raise Cancelled()
        _gi, m, (rel, _size, path, mtime_ns) = task
        try:
            size = os.stat(long_path(path), follow_symlinks=False).st_size
        except OSError:
            size = _size

        cached = self.cache.get(path, size, mtime_ns)
        if cached is not None:
            self.prog.bump(1, 0, path)
            return cached

        key = os.path.realpath(path)
        with self._physical_lock:
            known = self._physical.get(key)
        if known is not None:
            self.prog.bump(1, 0, path)
            self.cache.put(path, size, mtime_ns, known)
            return known

        try:
            digest, read = self._hash_file(path, size)
        except OSError as exc:
            self._warn("无法读取文件，该 mod 不参与重复判定：%s（%s）" % (path, exc.strerror or exc))
            m["partial"] = True
            return None

        with self._physical_lock:
            self._physical[key] = digest
        self.cache.put(path, size, mtime_ns, digest)
        self.prog.bump(1, read, path)
        return digest

    def _hash_file(self, path, size):
        h = hashlib.blake2b(digest_size=32)
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
        members = sorted(members, key=lambda m: m["path"].lower())
        member_bytes = members[0]["bytes"]
        count = len(members)
        return {
            "id": 0,
            "kind": kind,
            "count": count,
            "member_bytes": member_bytes,
            "reclaimable_bytes": member_bytes * (count - 1),
            "structure_sig": members[0]["struct"],
            "members": [
                {
                    "path": m["path"],
                    "files": len(m["files"]),
                    "bytes": m["bytes"],
                    "mod_name": m["name"],
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
            "current_path": snap["current_path"],
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
