"""全局常量与路径。"""

from __future__ import annotations

import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))              # mod_dup_checker/ 包目录
APP_DIR = os.path.dirname(PACKAGE_DIR)                                # 脚本 / 安装根目录
WEB_DIR = os.path.join(PACKAGE_DIR, "web")                            # index.html / style.css / app.js

CACHE_FILE_NAME = "moddup_cache.json"
CACHE_JOURNAL_NAME = "moddup_cache.journal"
CACHE_VERSION = 1


def _cache_dir():
    """缓存目录：MODDUP_CACHE_DIR > 程序目录旁的 cache/ > 用户本地数据目录。"""
    override = os.environ.get("MODDUP_CACHE_DIR")
    if override:
        return os.path.abspath(override)
    beside = os.path.join(APP_DIR, "cache")
    if os.access(beside, os.W_OK) or os.access(APP_DIR, os.W_OK):
        return beside
    # 装在 site-packages 之类只读位置时退到用户目录，不往程序目录里写
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "mod_dup_checker")


CACHE_DIR = _cache_dir()
CACHE_FILE = os.path.join(CACHE_DIR, CACHE_FILE_NAME)
CACHE_JOURNAL = os.path.join(CACHE_DIR, CACHE_JOURNAL_NAME)

DEFAULT_PORT = 8765
DEFAULT_JOBS = max(1, min(8, os.cpu_count() or 4))
SAMPLE_SIZE = 64 * 1024          # 采样段大小
SAMPLE_TOTAL = 3 * SAMPLE_SIZE   # 小于等于它就整文件读一次
FULL_CHUNK = 4 * 1024 * 1024       # 全量哈希缓冲（块大一点，顺序读的间接层更少）
CACHE_FLUSH_INTERVAL = 2.0       # 秒
