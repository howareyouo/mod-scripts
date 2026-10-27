"""mod 识别与 natives/ 文件枚举."""

from __future__ import annotations

import os
import stat as stat_mod
from dataclasses import dataclass, field

from .paths import display_path, is_reparse, long_path


class Cancelled(Exception):
    """用户取消扫描."""


@dataclass(slots=True)
class Mod:
    """一个待比较的 mod.字段在流水线各阶段逐步填上, 用属性避免字典键手滑."""

    path: str
    name: str
    natives: str
    root_index: int
    rel_depth: int
    index: int = -1
    files: list = field(default_factory=list)
    bytes: int = 0
    struct: str = ""
    partial: bool = False


def _path_depth(path):
    """路径层级 (不计盘符), 用来判断 mod 埋得有多深."""
    _, rest = os.path.splitdrive(os.path.normpath(display_path(path)))
    return len([x for x in rest.split(os.sep) if x])


def walk(top, cancel_evt=None, on_problem=None, descend=None):
    """深度优先遍历目录树, 逐个产出 (目录绝对路径, 相对前缀, 子目录名, 文件条目).

    - 重解析点 (符号链接 / junction)既不递归也不出现在结果里
    - ``descend(name)`` 返回 False 的子目录仍会出现在子目录名里, 但不递归
    - 目录读不出来时调用 ``on_problem(路径, 异常)`` 并跳过

    ``文件条目`` 为 [(名字, stat 结果, 绝对路径)].
    """
    stack = [(top, "")]
    while stack:
        cur, rel = stack.pop()
        if cancel_evt is not None and cancel_evt.is_set():
            raise Cancelled()
        try:
            with os.scandir(long_path(cur)) as it:
                entries = list(it)
        except OSError as exc:
            if on_problem is not None:
                on_problem(display_path(cur), exc)
            continue

        dirnames = []
        files = []
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                if on_problem is not None:
                    on_problem(display_path(entry.path), exc)
                continue
            if stat_mod.S_ISLNK(st.st_mode) or is_reparse(st):
                continue
            if stat_mod.S_ISDIR(st.st_mode):
                dirnames.append(entry.name)
                if descend is None or descend(entry.name):
                    stack.append((entry.path, rel + entry.name.lower() + "/"))
            elif stat_mod.S_ISREG(st.st_mode):
                files.append((entry.name, st, entry.path))
            # 其它类型 (设备、管道)忽略
        yield cur, rel, dirnames, files


def discover_mods(roots, cancel_evt=None):
    """返回 (mods, warnings), mods 是 :class:`Mod` 列表.mod 根目录 = 自身含有 natives 子目录 (大小写不敏感).

    每个 mod 附带 root_index (第几个输入目录扫到的)和 rel_depth (相对该目录的层级), 
    供扫描器决定同组重复里默认保留谁.
    """
    mods = []
    seen = set()
    warnings = []

    for root_index, raw in enumerate(roots):
        if cancel_evt is not None and cancel_evt.is_set():
            raise Cancelled()
        root = (raw or "").strip().strip('"').strip("'")
        if not root:
            continue
        root = os.path.expanduser(root)
        if not os.path.exists(root):
            warnings.append("目录不存在, 已跳过：%s" % root)
            continue
        if not os.path.isdir(root):
            warnings.append("不是目录, 已跳过：%s" % root)
            continue

        found = 0
        already = 0
        root_depth = _path_depth(root)

        def on_problem(path, exc):
            warnings.append("无法访问, 已跳过：%s (%s)" % (path, exc.strerror or exc))

        def descend(name):
            return name.lower() != "natives"   # 不往 natives 里钻, 里面的东西不是 mod

        try:
            for cur, rel, dirnames, _files in walk(long_path(root), cancel_evt, on_problem, descend):
                natives_name = None
                for dn in dirnames:
                    if dn.lower() == "natives":
                        natives_name = dn
                        break
                if natives_name is None:
                    continue

                mod_dir = os.path.normpath(display_path(cur))
                real = os.path.realpath(mod_dir)
                if real in seen:
                    already += 1
                    continue
                seen.add(real)
                mods.append(Mod(
                    path=mod_dir,
                    name=os.path.basename(mod_dir) or mod_dir,
                    natives=os.path.join(mod_dir, natives_name),
                    root_index=root_index,
                    rel_depth=max(0, _path_depth(mod_dir) - root_depth),
                ))
                found += 1
        except OSError as exc:
            warnings.append("遍历目录失败, 已跳过：%s (%s)" % (root, exc.strerror or exc))

        if found == 0:
            if already:
                warnings.append("该目录下的 %d 个 mod 已包含在之前的输入目录中, 已去重：%s" % (already, root))
            else:
                warnings.append("该目录下没有找到 mod (mod 根目录 = 自身含有 natives 子目录)：%s" % root)

    mods.sort(key=lambda m: m.path.lower())
    return mods, warnings


def list_natives_files(natives_dir, cancel_evt=None):
    """枚举 natives/ 下的普通文件, 只读元数据.

    返回 (files, problems)：files 为 [(相对路径小写, 大小, 绝对路径, mtime_ns, 硬链接数)], 
    按相对路径排序.
    """
    files = []
    problems = []

    def on_problem(path, exc):
        problems.append("%s (%s)" % (path, exc.strerror or exc.__class__.__name__))

    for _cur, rel, _dirs, entries in walk(natives_dir, cancel_evt, on_problem):
        for name, st, path in entries:
            files.append((rel + name.lower(), st.st_size, display_path(path),
                          st.st_mtime_ns, st.st_nlink))

    files.sort(key=lambda t: t[0])
    return files, problems
