"""全局常量与路径。"""

from __future__ import annotations

import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 脚本所在目录
WEB_DIR = os.path.join(APP_DIR, "mod_dup_checker", "web")              # index.html / style.css / app.js
CACHE_DIR = os.path.join(APP_DIR, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "moddup_cache.json")

DEFAULT_PORT = 8765
DEFAULT_JOBS = max(1, min(8, os.cpu_count() or 4))
SAMPLE_SIZE = 64 * 1024          # 采样段大小
SAMPLE_TOTAL = 3 * SAMPLE_SIZE   # 小于等于它就整文件读一次
FULL_CHUNK = 1024 * 1024         # 全量哈希缓冲
CACHE_FLUSH_INTERVAL = 2.0       # 秒
