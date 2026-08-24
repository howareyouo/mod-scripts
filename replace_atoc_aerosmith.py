import os, sys, shutil, hashlib, argparse
from collections import defaultdict
from tkinter import messagebox, filedialog
from pathlib import Path
import tkinter as tk

CURRENT_PATH = Path(__file__)
CURRENT_DIR = CURRENT_PATH.parent
TEXTURES_DIR = "E:/RE4 Mods/Mods Resources/_/"
HIDE_ATOC = TEXTURES_DIR + "hide_ATOC.tex.143221013"
SHOW_ATOC = TEXTURES_DIR + "show_ATOC.tex.143221013"
PUBS_SHOW = TEXTURES_DIR + "pubs_SHOW.tex.143221013"
SUFFIXES = (
    "_atos.tex",
    "_atoc.tex",
    "_atoc2.tex",
)
INGAME_DIR = r"E:\RE4 Mods\InGame\Ada Evil Nurse Style B"
SWITCH = True  # 是否进行替换, 为否时只打印替换信息
# 默认源文件列表, 可用于拖放或命令行未提供时
DEFAULT_SOURCE_FILES = [
    r"E:\RE4 Mods\InGame\Ada Evil Nurse Style B\Ada Evil Nurse Style B\natives\stm\_chainsaw\character\ch\cha2\cha200\00\cha200_00_panty_atoc.tex.143221013"
]

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

def replace_matching_files(directory=INGAME_DIR, hashes=None):
    if hashes is None:
        hashes = []
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
                    if SWITCH:
                        shutil.move(filepath, backup_path)
                        shutil.copy2(HIDE_ATOC, filepath)
                        print(f"replace {shorten_path(filename):<60} size: {file_size}")
                    else:
                        print(f"preview {shorten_path(filename):<60} size: {file_size}")
                except (OSError, PermissionError) as e:
                    print(f"Warning: Unable to create or move to backup folder {backup_dir}: {e}")

                matches.append(filename)
    return matches

def get_hashes_from_files(filepaths):
    """Calculate hashes from a list of file paths."""
    hashes = []
    for filepath in filepaths:
        if os.path.isfile(filepath):
            try:
                file_hash = get_file_hash(filepath)
                hashes.append(file_hash)
                print(f"Computed hash for {filepath}: {file_hash}")
            except Exception as e:
                print(f"Error computing hash for {filepath}: {e}")
        else:
            print(f"File not found: {filepath}")
    return hashes

def select_source_files():
    """Open a file dialog to select source files."""
    root = tk.Tk()
    root.withdraw()
    files = filedialog.askopenfilenames(
        title="Select source texture files",
        filetypes=[("Texture files", "*.tex.143221013"), ("All files", "*.*")]
    )
    root.destroy()
    return list(files)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replace ATOC/ATOS textures using hashes from source files.")
    parser.add_argument(
        "-s", "--sources",
        nargs="+",
        default=[],
        help="One or more source file paths to compute hashes from. Supports drag-and-drop."
    )
    parser.add_argument(
        "-d", "--directory",
        default=INGAME_DIR,
        help=f"Target directory to scan (default: {INGAME_DIR})"
    )
    parser.add_argument(
        "-g", "--gui",
        action="store_true",
        help="Open a file dialog to select source files (overrides -s and DEFAULT_SOURCE_FILES)."
    )
    args = parser.parse_args()

    # Determine source files: GUI dialog > command-line -s > drag-and-drop (sys.argv) > DEFAULT_SOURCE_FILES
    if args.gui:
        source_files = select_source_files()
    elif args.sources:
        source_files = args.sources
    else:
        # Attempt to read from sys.argv (drag-and-drop on Windows passes full paths)
        argv_files = [arg for arg in sys.argv[1:] if not arg.startswith('-') and os.path.isfile(arg)]
        if argv_files:
            source_files = argv_files
        elif DEFAULT_SOURCE_FILES:
            source_files = DEFAULT_SOURCE_FILES
            print("Using DEFAULT_SOURCE_FILES from script configuration.")
        else:
            parser.error("No source files provided. Use -s to specify source files, -g for file dialog, or drag-and-drop files onto the script.")

    hashes = get_hashes_from_files(source_files)

    if not hashes:
        print("No valid hashes computed. Exiting.")
        sys.exit(1)

    matches = replace_matching_files(args.directory, hashes)
    print(f"Done, {len(matches)} textures replaced")
