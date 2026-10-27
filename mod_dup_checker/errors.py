"""扫描过程的异常类型。"""

from __future__ import annotations


class Cancelled(Exception):
    """用户取消扫描。"""
