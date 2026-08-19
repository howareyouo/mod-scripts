import os, shutil, math, datetime
from site import PREFIXES
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

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
    
def replace_tex(source, target):
    print("replacing: " + shorten_path(target))
    if SWITCH == False:
        return 0
    # 替换文件
    dest = shutil.copy2(source, target)
    return 1 if dest else 0

def shorten_path(path):
    s = path.replace(INGAME_DIR, "")
    s = s.replace(r"natives\stm\_chainsaw\character\ch\cha2\cha200", "..")
    return s.rpartition('.')[0]

PREFIXES = (
    "Remov_",
    "cha101_00_pub",
)

INGAME_DIR = r"E:\RE4 Mods\InGame\Ada Midnight Verdict"
SWITCH = True # 是否进行替换, 为否时只打印替换信息

if __name__ == "__main__":
    texs = 0
    for root, dirs, files in os.walk(INGAME_DIR, topdown=True):
        for name in files:
            file_name, ext = os.path.splitext(name)
            if ext != ".143221013" or not file_name.startswith(PREFIXES):
                continue
            file_path = os.path.join(root, name)
            file_size = math.ceil(os.path.getsize(file_path) / 1024)
            mtime = os.path.getmtime(file_path)
            mtime = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{shorten_path(file_path):<60} size: {file_size} kb \tmtime: {mtime}")

            if file_name.startswith(PREFIXES[0]):
                if file_size == 65 and mtime == "2023-04-27 13:13:41":
                    texs += replace_tex(SHOW_ATOC, file_path)
                elif (file_size == 257 and mtime == "2023-04-07 21:17:30") or (file_size == 5462 and mtime == "2023-11-11 04:13:42"):
                    texs += replace_tex(HIDE_ATOC, file_path)
            
            elif file_name.startswith(PREFIXES[1]):
                if (file_size == 257 and mtime == "2023-04-07 21:17:30") or (file_size == 5462 and mtime == "2023-11-11 04:13:42"):
                    texs += replace_tex(HIDE_ATOC, file_path)
                elif file_size == 257 and mtime == "2023-06-18 15:21:37":
                    texs += replace_tex(PUBS_SHOW, file_path)

    show_message("Done", f"{texs} textures replaced")

