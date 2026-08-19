import os, shutil, math, datetime, hashlib
from collections import defaultdict
from tkinter import messagebox
from pathlib import Path
from site import PREFIXES
import tkinter as tk

CURRENT_PATH = Path(__file__)
CURRENT_DIR = CURRENT_PATH.parent
TEXTURES_DIR = r"E:\RE4 Mods\Mods Resources\_\\"
HIDE_ATOC = TEXTURES_DIR + "hide_ATOC.tex.143221013"
SHOW_ATOC = TEXTURES_DIR + "show_ATOC.tex.143221013"
PUBS_SHOW = TEXTURES_DIR + "pubs_SHOW.tex.143221013"

def show_message(title, message):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()

def shorten_path(path):
    s = path.replace(INGAME_DIR, "")
    s = s.replace(r"natives\stm\_chainsaw\character\ch\cha2\cha200", "..")
    return s.rpartition('.')[0]

def get_file_hash(filepath, algorithm='sha256'):
    hash_obj = hashlib.new(algorithm)
    
    with open(filepath, 'rb') as f:
        # 分块读取，避免大文件占用过多内存
        chunk_size = 8192
        while chunk := f.read(chunk_size):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()

def format_filesize(filepath):
    size_bytes = os.path.getsize(filepath)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

def find_duplicate_files(directory='.'):
    """
    查找指定目录中的重复文件
    Args:
        directory: 要搜索的目录路径，默认为当前目录
    Returns:
        字典，键为文件哈希值，值为具有相同哈希值的文件路径列表
    """
    # 第一步：按文件大小分组（快速筛选）
    size_groups = defaultdict(list)
    
    print("正在扫描文件...")
    for root, dirs, files in os.walk(directory):
        # 跳过隐藏目录和常见不需要搜索的目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for filename in files:
            # 跳过隐藏文件
            if filename.startswith('.'): 
                continue
                
            filepath = os.path.join(root, filename)
            
            # 确保是文件而不是符号链接等
            if not os.path.isfile(filepath):
                continue
            
            try:
                file_size = os.path.getsize(filepath)
                # 只关注大小大于0的文件，且至少有两个文件才有意义
                if file_size > 0:
                    size_groups[file_size].append(filepath)
            except (OSError, PermissionError) as e:
                print(f"警告: 无法访问文件 {filepath}: {e}")
    
    # 第二步：对大小相同的文件计算哈希值
    print("正在比较文件内容...")
    hash_groups = defaultdict(list)
    files_checked = 0
    
    for file_size, filepaths in size_groups.items():
        # 只有当有多个文件具有相同大小时才需要进一步比较
        if len(filepaths) < 2:
            continue
        
        for filepath in filepaths:
            try:
                file_hash = get_file_hash(filepath)
                hash_groups[file_hash].append(filepath)
                files_checked += 1
            except (OSError, PermissionError) as e:
                print(f"警告: 无法读取文件 {filepath}: {e}")
    
    # 第三步：过滤出真正的重复文件（至少2个文件有相同哈希）
    duplicates = {
        hash_val: paths 
        for hash_val, paths in hash_groups.items() 
        if len(paths) >= 2
    }
    return duplicates, files_checked

def replace_matching_files(directory, hashes):
    matches = []
    for root, dirs, files in os.walk(directory, topdown=True):
        for name in files:
            filename, ext = os.path.splitext(name)
            if ext != ".143221013" or not filename.lower().endswith(SUFFIXES):
                continue
            filepath = os.path.join(root, name)
            if get_file_hash(filepath) in hashes:
                file_size = format_filesize(filepath)
                try:
                    backup_dir = os.path.join(root, "_backup")
                    os.makedirs(backup_dir, exist_ok=True)
                    backup_name = os.path.basename(filepath)
                    backup_path = os.path.join(backup_dir, backup_name)
                    shutil.move(filepath, backup_path)
                except (OSError, PermissionError) as e:
                    print(f"警告: 无法创建或移动到备份文件夹 {backup_dir}: {e}")

                matches.append(filename)
                print(f"replace {shorten_path(filename):<60} size: {file_size}")
                shutil.copy2(HIDE_ATOC, filepath)
    return matches

# 0b1a9bf24a65991f69ffdcf5a2132c0be40f0b392f505d93dbbee01c46a6166c

SUFFIXES = (
    "_atos.tex",
    "_atoc.tex",
    "_atoc2.tex",
)
HASHES = [
    "42fe606c2614d8ba592343786e1f70fcee07284116718ce0bb1a82041eb3b3c4",
    "e0051d8618fb55516d754875729eb4c2e1aef4f8a6ac8bdadfb259163104a938",
]

INGAME_DIR = r"E:\RE4 Mods\Ada 1"
SWITCH = True # 是否进行替换, 为否时只打印替换信息

if __name__ == "__main__":
    matches = replace_matching_files(INGAME_DIR, HASHES)
    print(f"Done, {len(matches)} textures replaced")
