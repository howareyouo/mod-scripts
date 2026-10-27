"""Windows 路径工具：长路径前缀、重解析点."""

from __future__ import annotations

import os
import stat as stat_mod

_REPARSE_ATTR = getattr(stat_mod, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def long_path(path):
    """Windows 长路径防御：超长时加 \\\\?\\ 前缀."""
    if os.name != "nt":
        return path
    if len(path) < 250:
        return path
    if path.startswith("\\\\?\\"):
        return path
    abspath = os.path.abspath(path)
    if abspath.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abspath[2:]
    return "\\\\?\\" + abspath


def display_path(path):
    """去掉 Windows 长路径前缀, 得到用户看得懂的路径."""
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def is_reparse(st):
    """符号链接 / junction / 其它重解析点：一律不跟进."""
    if os.name != "nt":
        return False
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE_ATTR)
