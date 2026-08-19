#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SHA256 文件哈希生成工具
=====================

功能:
- 计算指定目录下文件的 SHA256 哈希值
- 支持按文件扩展名过滤
- 批量处理文件并输出结果

使用方法:
1. 直接运行脚本:python sha256gen.py
2. 修改 exts 变量来指定要处理的文件类型
3. 结果会直接输出到控制台

作者:MiMoCode
创建日期:2026-07-31
"""

import os
import hashlib

def calculate_hash(file_path, algorithm='sha256', chunk_size=8192):
    """
    计算单个文件的哈希值
    
    参数:
        file_path (str): 文件路径
        algorithm (str): 哈希算法, 默认为 'sha256'
        chunk_size (int): 读取文件的块大小, 默认为 8192 字节
        
    返回:
        str: 文件的哈希值(十六进制字符串)
        
    异常:
        如果文件读取失败会抛出异常
    """
    hash_func = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        # 分块读取文件以处理大文件
        while chunk := f.read(chunk_size):
            hash_func.update(chunk)
    return hash_func.hexdigest()

def hash_all_files(directory='.', extensions=None):
    """
    批量计算目录下所有文件的哈希值
    
    参数:
        directory (str): 要扫描的目录路径, 默认为当前目录
        extensions (list): 文件扩展名列表, 例如 ['.txt', '.py'], None 表示不过滤
        
    返回:
        list: 包含 (文件路径, 哈希值) 元组的列表, 错误时哈希值为错误信息
        
    说明:
        - 使用递归方式遍历目录
        - 支持文件扩展名过滤
        - 捕获并记录文件处理过程中的异常
    """
    results = []
    
    if extensions:
        extensions = set(ext.lower() for ext in extensions)

    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)

            # 扩展名过滤
            if extensions:
                _, ext = os.path.splitext(file)
                if ext.lower() not in extensions:
                    continue

            try:
                file_hash = calculate_hash(file_path)
                results.append((file_path, file_hash))
            except Exception as e:
                results.append((file_path, f'ERROR: {e}'))

    return results

if __name__ == '__main__':
    """
    主程序入口
    """
    # 配置要处理的文件类型
    # ['.143221013'] - 只处理扩展名为 .143221013 的文件
    # None - 处理所有文件类型
    exts = ['.143221013']   # 修改这里来改变文件过滤规则

    # 执行哈希计算
    results = hash_all_files('.', extensions=exts)

    # 输出结果
    print("=" * 80)
    print("文件哈希值计算结果")
    print("=" * 80)
    for path, h in results:
        print(f"{path}  {h}")
    print("=" * 80)
    print(f"共处理 {len(results)} 个文件")
    print("=" * 80)

    # 等待用户按键退出
    input("\n执行完成, 按回车键退出...")
