"""把文件 / 目录送进回收站 (可还原), 本工具不做永久删除."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400

# SHFileOperation 内部走 MAX_PATH 缓冲区, 更长的路径一律拒绝而不是冒险
MAX_RECYCLE_PATH = 260
# pFrom 是单个缓冲区, 一次提交的路径总长不能太大, 超了 Windows 会直接拒绝
MAX_BATCH_CHARS = 30000

_ERRORS = {
    0x20: "文件正被其它程序占用.",
    0x71: "源和目标是同一个文件.",
    0x75: "操作被取消.",
    0x77: "拒绝访问.",
    0x78: "路径太深.",
    0x7C: "路径无效 (可能过长或含非法字符).",
}


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def _shell32():
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
    shell32.SHFileOperationW.restype = ctypes.c_int
    return shell32


def _delete(paths):
    """把一批路径 (都是绝对路径)交给一次 SHFileOperation.成功返回 None, 否则返回错误消息."""
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = "\0".join(paths) + "\0\0"  # 必须是双空结尾的路径列表
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI

    code = _shell32().SHFileOperationW(ctypes.byref(op))
    if code != 0:
        return _ERRORS.get(code, "回收站操作失败 (错误码 0x%X)." % code)
    if op.fAnyOperationsAborted:
        return "回收站操作被取消."
    if any(os.path.exists(p) for p in paths):
        return "接口报告成功, 但路径仍然存在；可能有程序占用, 请手动处理."
    return None


def _chunks(ready):
    """按缓冲区长度切分, 避免一次提交的路径列表超出 SHFileOperation 的承受范围."""
    chunk = []
    size = 0
    for raw, path in ready:
        if chunk and size + len(path) + 1 > MAX_BATCH_CHARS:
            yield chunk
            chunk = []
            size = 0
        chunk.append((raw, path))
        size += len(path) + 1
    if chunk:
        yield chunk


def recycle_many(paths):
    """把多个路径批量移到回收站.

    返回 (deleted, failed)：deleted 为成功移走的原始路径, failed 为 [(原始路径, 错误消息)].
    正常情况下整批只走一次 shell 调用；某一批报错才逐条重试, 把错误归到具体路径上.
    """
    if os.name != "nt":
        return [], [(p, "回收站删除仅在 Windows 上可用.") for p in paths]

    ready, failed = [], []
    for raw in paths:
        path = os.path.abspath(raw)
        if not os.path.exists(path):
            failed.append((raw, "路径不存在."))
        elif len(path) >= MAX_RECYCLE_PATH:
            failed.append((raw, "路径超过 %d 个字符, 回收站接口不支持, 请手动删除." % MAX_RECYCLE_PATH))
        else:
            ready.append((raw, path))

    deleted = []
    for chunk in _chunks(ready):
        if len(chunk) > 1 and _delete([path for _raw, path in chunk]) is None:
            deleted.extend(raw for raw, _path in chunk)
            continue
        for raw, path in chunk:
            if not os.path.exists(path):      # 同批的另一次调用已经删掉了
                deleted.append(raw)
                continue
            msg = _delete([path])
            if msg is None:
                deleted.append(raw)
            else:
                failed.append((raw, msg))
    return deleted, failed


def recycle(path):
    """把单个路径移到回收站.成功返回 None, 失败抛 OSError (消息可直接展示)."""
    _deleted, failed = recycle_many([path])
    if failed:
        raise OSError(failed[0][1])
