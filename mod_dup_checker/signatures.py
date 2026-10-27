"""三级签名：结构 (路径+大小)→ 采样 → 全量.

文件条目为 (相对路径小写, 大小, 绝对路径, mtime_ns, 硬链接数) 五元组.
"""

from __future__ import annotations

import hashlib

from .config import SAMPLE_SIZE, SAMPLE_TOTAL
from .paths import long_path

STRUCTURE_DIGEST_SIZE = 32
SAMPLE_DIGEST_SIZE = 16


def _feed_rel(h, rel, size):
    h.update(rel.encode("utf-8", "surrogatepass"))
    h.update(b"\x00")
    h.update(str(size).encode("ascii"))
    h.update(b"\x00")


def sample_file_digest(rel, size, path):
    """第 2 级单文件采样：首 64 KiB + 中间 64 KiB + 末尾 64 KiB.返回 (摘要字节, 实际读取字节数)."""
    h = hashlib.blake2b(digest_size=SAMPLE_DIGEST_SIZE)
    _feed_rel(h, rel, size)
    read = 0
    with open(long_path(path), "rb", buffering=0) as f:
        if size <= SAMPLE_TOTAL:
            data = f.read(SAMPLE_TOTAL)
            h.update(len(data).to_bytes(8, "little"))
            h.update(data)
            read += len(data)
        else:
            for off in (0, size // 2, size - SAMPLE_SIZE):
                f.seek(off)
                data = f.read(SAMPLE_SIZE)
                h.update(len(data).to_bytes(8, "little"))
                h.update(data)
                read += len(data)
    return h.digest(), read


def combine_mod_sig(digest_size, files, digests=None):
    """把「相对路径 + 大小 + 单文件摘要」按顺序合成整个 mod 的签名.

    ``digests`` 为 None 时只吃路径与大小, 即第 1 级的结构签名.
    单文件摘要可以是 bytes, 也可以是缓存里的十六进制字符串.
    """
    h = hashlib.blake2b(digest_size=digest_size)
    if digests is None:
        for rel, size, _p, _mt, _n in files:
            _feed_rel(h, rel, size)
        return h.hexdigest()
    for (rel, size, _p, _mt, _n), digest in zip(files, digests):
        _feed_rel(h, rel, size)
        h.update(digest.encode("ascii") if isinstance(digest, str) else digest)
    return h.hexdigest()


def structure_sig(files):
    """第 1 级：只看 (相对路径, 大小), 零内容读取."""
    return combine_mod_sig(STRUCTURE_DIGEST_SIZE, files)
