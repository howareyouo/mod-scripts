"""三级签名：结构（路径+大小）→ 采样 → 全量。"""

from __future__ import annotations

import hashlib

from .config import SAMPLE_SIZE, SAMPLE_TOTAL
from .paths import long_path


def _feed_rel(h, rel, size):
    h.update(rel.encode("utf-8", "surrogatepass"))
    h.update(b"\x00")
    h.update(str(size).encode("ascii"))
    h.update(b"\x00")


def structure_sig(files):
    """第 1 级：只看 (相对路径, 大小)，零内容读取。"""
    h = hashlib.sha256()
    for rel, size, _p, _mt in files:
        _feed_rel(h, rel, size)
    return h.hexdigest()


def sample_file_digest(rel, size, path):
    """第 2 级单文件采样：首 64 KiB + 中间 64 KiB + 末尾 64 KiB。返回 (十六进制摘要, 实际读取字节数)。"""
    h = hashlib.blake2b(digest_size=16)
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
    return h.hexdigest(), read


def combine_mod_sig(digest_size, files, digests):
    """把「相对路径 + 大小 + 单文件摘要」按顺序合成整个 mod 的签名。"""
    h = hashlib.blake2b(digest_size=digest_size)
    for (rel, size, _p, _mt), digest in zip(files, digests):
        _feed_rel(h, rel, size)
        h.update(digest.encode("ascii") if isinstance(digest, str) else digest)
    return h.hexdigest()
