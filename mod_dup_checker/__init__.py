"""mod 重复检测工具的功能模块包。

- ``config``      路径与常量
- ``paths``       Windows 长路径 / 重解析点
- ``discovery``   mod 识别与 natives/ 文件枚举
- ``signatures``  三级签名（结构 → 采样 → 全量）
- ``cache``       全量哈希缓存
- ``progress``    进度快照
- ``scanner``     扫描任务、结果组装、单任务注册表
- ``webui``       HTTP 服务与前端资源托管
- ``cli``         无界面模式
"""

from __future__ import annotations

__all__ = ["config", "paths", "discovery", "signatures", "cache", "progress", "scanner", "webui", "cli"]
