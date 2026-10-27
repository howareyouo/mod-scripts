"""mod 重复检测工具 —— 启动入口。

只比较每个 mod 的 ``natives/`` 子树：相对路径集合 + 每个文件大小 + 每个文件内容。
``modinfo.ini`` / 截图 / mod 根目录下的其它东西一律不进比较集合。

前端资源在 ``mod_dup_checker/web/``，后端功能模块在 ``mod_dup_checker/`` 包里，
本文件只负责解析参数并分发。

用法::

    python mod_dup_checker.py
    python mod_dup_checker.py --no-browser
    python mod_dup_checker.py --cli "E:/Dedup/Ada Side Slit Cheongsam" "E:/Dedup/Ada Side Slit Cheongsam_"
"""

from __future__ import annotations

import argparse
import sys

from mod_dup_checker.cli import run_cli, setup_console
from mod_dup_checker.config import DEFAULT_JOBS, DEFAULT_PORT
from mod_dup_checker.webui import serve


def main(argv=None):
    setup_console()

    parser = argparse.ArgumentParser(
        description="mod 重复检测：只比较 natives/ 下的文件，按路径+大小+内容判定重复。",
    )
    parser.add_argument("--cli", nargs="+", metavar="路径",
                        help="无界面模式：扫描给定目录并直接打印分组结果")
    parser.add_argument("--no-browser", action="store_true", help="只启动服务，不自动打开浏览器")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口（默认 %d）" % DEFAULT_PORT)
    parser.add_argument("--jobs", type=int, default=None, help="IO 线程数（默认 %d）" % DEFAULT_JOBS)
    args = parser.parse_args(argv)

    if args.cli:
        return run_cli(args.cli, args.jobs)
    return serve(args)


if __name__ == "__main__":
    sys.exit(main())
