"""命令行（无界面）模式：带实时进度行地打印分组结果。"""

from __future__ import annotations

import sys
import threading

from .scanner import ScanJob


def setup_console():
    """控制台编码兜底：能显示中文就保持原样，不能就切 UTF-8，绝不因为编码崩掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", None) or "ascii")
            "中文".encode(enc)
            continue
        except Exception:
            pass
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


def fmt_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.2f %s" % (n, unit))
        n /= 1024.0
    return "%.2f TiB" % n


def run_cli(paths, jobs):
    job = ScanJob("cli", paths, jobs)
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            snap = job.prog.snapshot()
            total = snap["phase_total"]
            done = snap["phase_done"]
            pct = ("%5.1f%%" % (done * 100.0 / total)) if total else "  --- "
            line = "[%s] %s  mod %d/%d  文件 %d/%d  已读 %s" % (
                snap["phase"], pct, snap["scanned_mods"], snap["total_mods"],
                done, total, fmt_bytes(snap["bytes_read"]),
            )
            sys.stdout.write("\r" + line)
            sys.stdout.flush()
            stop.wait(0.3)
        # \x1b[K 抹掉整行剩余内容，不用猜上一行有多长
        sys.stdout.write("\r\x1b[K")
        sys.stdout.flush()

    thread = threading.Thread(target=monitor, name="cli-progress", daemon=True)
    thread.start()
    job.run()
    stop.set()
    thread.join(1.5)

    res = job.result()
    stats = res["stats"]
    times = stats.get("phase_times_ms", {})
    print("=" * 72)
    print("扫描完成：%d 个 mod，natives 文件 %d 个，总计 %s"
          % (stats["mods"], stats["files"], fmt_bytes(stats["bytes"])))
    print("阶段耗时：结构 %sms / 采样 %sms / 全量 %sms / 总计 %dms"
          % (times.get("structure", 0), times.get("sample", 0),
             times.get("full", 0), stats["elapsed_ms"]))
    print("实际读取：%s（采样 + 全量；另有 %d 个文件命中缓存不计入）"
          % (fmt_bytes(stats.get("bytes_read", 0)), stats.get("cache_hits", 0)))
    print("重复结果：%d 组，%d 个 mod，可回收 %s"
          % (len(res["groups"]), stats["dup_mods"], fmt_bytes(stats["reclaimable_bytes"])))
    if res["cancelled"]:
        print("注意：扫描被取消，结论不完整。")
    print("=" * 72)

    for g in res["groups"]:
        print("")
        print("[组 %d] %d 个成员 | 单个 %s | 可回收 %s | 结构签名 %s%s"
              % (g["id"], g["count"], fmt_bytes(g["member_bytes"]),
                 fmt_bytes(g["reclaimable_bytes"]), g["structure_sig"][:8],
                 "  (疑似)" if g["kind"] == "structure" else ""))
        for i, m in enumerate(g["members"]):
            print("    %s  %s  (%d 个文件, %s)"
                  % ("保留" if i == 0 else "候选", m["path"], m["files"], fmt_bytes(m["bytes"])))

    if res["empty_mods"]:
        print("")
        print("空 mod（natives/ 下没有任何文件）：%d 个" % len(res["empty_mods"]))
        for p in res["empty_mods"]:
            print("    %s" % p)

    if res["partial_mods"]:
        print("")
        print("有读取问题的 mod（不参与重复判定）：%d 个" % len(res["partial_mods"]))
        for p in res["partial_mods"]:
            print("    %s" % p)

    if res["warnings"]:
        print("")
        print("提示 / 警告：%d 条" % len(res["warnings"]))
        for w in res["warnings"]:
            print("    %s" % w)

    if res["stats"].get("cancelled"):
        return 130
    return 0
