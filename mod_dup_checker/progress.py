"""扫描进度快照（线程安全）。"""

from __future__ import annotations

import threading
import time


class Progress:
    def __init__(self):
        self._lock = threading.Lock()
        self.phase = "准备中"
        self.phase_done = 0
        self.phase_total = 0
        self.scanned_mods = 0
        self.total_mods = 0
        self.bytes_read = 0
        self.current_path = ""
        self._last_path_ts = 0.0

    def start_phase(self, phase, total):
        with self._lock:
            self.phase = phase
            self.phase_done = 0
            self.phase_total = total

    def set_mods(self, done, total):
        with self._lock:
            self.scanned_mods = done
            self.total_mods = total

    def set_label(self, phase):
        """只换阶段名，保留上一阶段的计数（收尾时进度条不会突然归零）。"""
        with self._lock:
            self.phase = phase

    def bump(self, files=1, read_bytes=0, path=None):
        with self._lock:
            self.phase_done += files
            self.bytes_read += read_bytes
            if path is not None:
                now = time.monotonic()
                if now - self._last_path_ts >= 0.1:  # 当前路径字段节流 ≥100ms
                    self.current_path = path
                    self._last_path_ts = now

    def snapshot(self):
        with self._lock:
            return {
                "phase": self.phase,
                "phase_done": self.phase_done,
                "phase_total": self.phase_total,
                "scanned_mods": self.scanned_mods,
                "total_mods": self.total_mods,
                "bytes_read": self.bytes_read,
                "current_path": self.current_path,
            }
