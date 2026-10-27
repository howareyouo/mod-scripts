"""mod 识别与 natives/ 文件枚举。"""

from __future__ import annotations

import os
import stat as stat_mod

from .errors import Cancelled
from .paths import display_path, is_reparse, long_path


def discover_mods(roots, cancel_evt=None):
    """返回 (mods, warnings)。mod 根目录 = 自身含有 natives 子目录（大小写不敏感）。"""
    mods = []
    seen = set()
    warnings = []

    for raw in roots:
        if cancel_evt is not None and cancel_evt.is_set():
            raise Cancelled()
        root = (raw or "").strip().strip('"').strip("'")
        if not root:
            continue
        root = os.path.expanduser(root)
        if not os.path.exists(root):
            warnings.append("目录不存在，已跳过：%s" % root)
            continue
        if not os.path.isdir(root):
            warnings.append("不是目录，已跳过：%s" % root)
            continue

        found = 0
        already = 0
        try:
            walker = os.walk(long_path(root), followlinks=False)
            for cur, dirnames, _files in walker:
                if cancel_evt is not None and cancel_evt.is_set():
                    raise Cancelled()

                keep = []
                natives_name = None
                for dn in dirnames:
                    full = os.path.join(cur, dn)
                    try:
                        st = os.stat(full, follow_symlinks=False)
                    except OSError:
                        warnings.append("无法访问子目录，已跳过：%s" % display_path(full))
                        continue
                    if is_reparse(st):
                        continue
                    if dn.lower() == "natives":
                        natives_name = dn
                        continue
                    keep.append(dn)
                dirnames[:] = keep

                if natives_name is None:
                    continue

                mod_dir = os.path.normpath(display_path(cur))
                real = os.path.realpath(mod_dir)
                if real in seen:
                    already += 1
                    continue
                seen.add(real)
                mods.append({
                    "path": mod_dir,
                    "name": os.path.basename(mod_dir) or mod_dir,
                    "natives": os.path.join(mod_dir, natives_name),
                })
                found += 1
        except OSError as exc:
            warnings.append("遍历目录失败，已跳过：%s（%s）" % (root, exc.strerror or exc))

        if found == 0:
            if already:
                warnings.append("该目录下的 %d 个 mod 已包含在之前的输入目录中，已去重：%s" % (already, root))
            else:
                warnings.append("该目录下没有找到 mod（mod 根目录 = 自身含有 natives 子目录）：%s" % root)

    mods.sort(key=lambda m: m["path"].lower())
    return mods, warnings


def list_natives_files(natives_dir, cancel_evt=None):
    """枚举 natives/ 下的普通文件，只读元数据。

    返回 (files, problems)：files 为 [(相对路径小写, 大小, 绝对路径, mtime_ns)]，按相对路径排序。
    """
    files = []
    problems = []
    stack = [(natives_dir, "")]
    while stack:
        if cancel_evt is not None and cancel_evt.is_set():
            raise Cancelled()
        cur, rel = stack.pop()
        try:
            with os.scandir(long_path(cur)) as it:
                entries = list(it)
        except OSError as exc:
            problems.append("%s（%s）" % (display_path(cur), exc.strerror or exc.__class__.__name__))
            continue

        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                problems.append("%s（%s）" % (display_path(entry.path), exc.strerror or exc.__class__.__name__))
                continue
            if stat_mod.S_ISLNK(st.st_mode) or is_reparse(st):
                continue
            if stat_mod.S_ISDIR(st.st_mode):
                stack.append((entry.path, rel + entry.name.lower() + "/"))
            elif stat_mod.S_ISREG(st.st_mode):
                files.append((rel + entry.name.lower(), st.st_size, display_path(entry.path), st.st_mtime_ns))
            # 其它类型（设备、管道）忽略

    files.sort(key=lambda t: t[0])
    return files, problems
