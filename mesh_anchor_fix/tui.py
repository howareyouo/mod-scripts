# -*- coding: utf-8 -*-
r"""
tui.py — mesh_anchor_fix 的交互式终端 UI 组件

提供路径输入 (拖放自动确认)、文件列表选择、文字高亮等功能.
"""

import os
import sys

# 启用 Windows 终端的 ANSI 颜色支持
if os.name == 'nt':
    os.system('')

# 文字高亮颜色 (ANSI)
CYAN = '\033[96m'
END = '\033[0m'


def hl(s):
    """给文字添加颜色突出显示"""
    return f"{CYAN}{s}{END}"


def clean_path(s):
    """去掉拖拽/右键复制路径时带的引号和空白"""
    return s.strip().strip('"').strip("'").strip()


def monotonic_ms():
    """返回单调递增的毫秒数(用于拖入自动确认超时)."""
    try:
        import time
        return int(time.monotonic() * 1000)
    except Exception:
        return 0


def ask_path(prompt):
    """逐字符读取,拖入/粘贴文件路径后自动回车确认(无需手动按回车)."""
    try:
        import msvcrt
    except ImportError:
        # 非 Windows 回退到普通 input
        while True:
            p = clean_path(input(prompt))
            if not p:
                print("  路径不能为空,请重新输入")
            elif not os.path.isfile(p):
                print(f"  文件不存在: {p}")
            else:
                return p

    buf = ''
    last_char_time = 0
    AUTOACCEPT_MS = 400  # 拖入/粘贴后停顿 400ms 无新字符则自动确认

    print(prompt, end='', flush=True)
    while True:
        try:
            ch = msvcrt.getwch()
        except Exception:
            # 降级:用 input 走一遍
            print()
            p = clean_path(input("   > "))
            if not p:
                print("  路径不能为空,请重新输入")
                print(prompt, end='', flush=True)
                continue
            if not os.path.isfile(p):
                print(f"  文件不存在: {p}")
                print(prompt, end='', flush=True)
                continue
            return p

        now = monotonic_ms()
        if now - last_char_time > AUTOACCEPT_MS and buf and os.path.isfile(clean_path(buf)):
            # 停顿期间路径已完整,自动确认
            print()
            return clean_path(buf)
        last_char_time = now

        if ch == "\r":  # 回车手动确认
            print()
            p = clean_path(buf)
            if not p:
                print("  路径不能为空,请重新输入")
                print(prompt, end='', flush=True)
                buf = ''
                last_char_time = 0
                continue
            if not os.path.isfile(p):
                print(f"  文件不存在: {p}")
                print(prompt, end='', flush=True)
                buf = ''
                last_char_time = 0
                continue
            return p
        elif ch in ("\x1b", "\x03"):  # Esc / Ctrl+C
            print()
            buf = ''
            last_char_time = 0
            print(prompt, end='', flush=True)
            continue
        elif ch in ("\x08", "\x7f"):  # 退格
            buf = buf[:-1]
            print("\b \b", end='', flush=True)
        else:
            buf += ch
            print(ch, end='', flush=True)


def list_meshes(meshes_dir):
    """列出目录下的所有 mesh 文件 (按文件名排序)"""
    if not os.path.isdir(meshes_dir):
        return []
    files = []
    for name in sorted(os.listdir(meshes_dir)):
        p = os.path.join(meshes_dir, name)
        if os.path.isfile(p) and name.endswith('.221108797'):
            files.append(p)
    return files


def select_body_mesh(meshes_dir):
    """选择目标身体 mesh：上下方向键高亮选择 / 输入数字 / 拖放路径.
    无可用列表或终端不支持方向键时, 回退为普通输入."""
    files = list_meshes(meshes_dir)
    if not files:
        return ask_path(f"② 输入 「{hl('目标角色的身体 mesh')}」 路径并回车\n   (可输入编号或把文件拖进本窗口): ")

    try:
        import msvcrt
    except ImportError:
        msvcrt = None

    if msvcrt is None:
        for i, p in enumerate(files, 1):
            print(f"   {i}. {os.path.basename(p)}")
        return ask_path(f"② 输入 「{hl('目标角色的身体 mesh')}」 路径并回车\n   (可输入编号或把文件拖进本窗口): ")

    sel = 0
    buf = ''
    last_char_time = 0
    print(f"② 选择「{hl('目标角色的身体 mesh')}」(↑/↓ 或数字选择,回车确认;也可直接拖放文件路径):")

    def render():
        for i, p in enumerate(files):
            label = f"{os.path.basename(p)}"
            if i == sel:
                print(f"  \x1b[32m❯ {label}\x1b[0m")
            else:
                print(f"    {label}")
        print("  [↑/↓ 选择, 数字键直接选中, 回车确认, Esc 取消]")

    render()
    while True:
        try:
            ch = msvcrt.getwch()
        except Exception:
            return ask_path(f"② 输入 「{hl('目标角色的身体 mesh')}」 路径并回车\n   (可输入编号或把文件拖进本窗口): ")

        now = monotonic_ms()
        if now - last_char_time > 400 and buf and os.path.isfile(clean_path(buf)):
            print()
            return clean_path(buf)
        last_char_time = now

        if ch in ("\x00", "\xe0"):  # 功能键前缀
            key = msvcrt.getwch()
            if key == "H":  # ↑
                sel = (sel - 1) % len(files)
            elif key == "P":  # ↓
                sel = (sel + 1) % len(files)
            else:
                continue
            print(f"\x1b[{len(files) + 1}A\x1b[J", end="")
            render()
        elif ch == "\r":
            if buf.strip():
                p = clean_path(buf)
                if os.path.isfile(p):
                    print()
                    return p
                print(f"  文件不存在: {p}")
                buf = ''
                continue
            print()
            return files[sel]
        elif ch.isdigit() and 1 <= int(ch) <= len(files):
            print()
            return files[int(ch) - 1]
        elif ch in ("\x1b", "\x03"):  # Esc / Ctrl+C
            return ask_path(f"② 输入「{hl('目标角色的身体 mesh')}」路径并回车\n   (可输入编号或把文件拖进本窗口): ")
        elif ch in ("\x08", "\x7f"):  # 退格
            buf = buf[:-1]
            continue
        else:
            buf += ch
            last_char_time = now
            continue
