import os, shutil, fnmatch, math, datetime, re
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

CURRENT_PATH = Path(__file__)
CURRENT_DIR = CURRENT_PATH.parent
DOWNLOAD_DIR = "C:/Users/hunan/Downloads/"
MODS_DIR = "E:/FluffyModManager/Games/StellarBlade/Mods/"

def show_message(title, message):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()

def shorten_path(path):
    return s.rpartition('/')[0]
    
def rename_file(filepath, new_filename):
    # target_path.rename(backup_name)
    p = Path(filepath)
    new_file = p.with_name(new_filename + p.suffix)
    print(f"Replace {filepath} to {os.path.basename(new_file)}")
    p.rename(new_file)

def replace_dir(dir):
    cnt = 0
    for root, dirs, files in os.walk(dir, topdown=True):
        for f in files:
            filename, ext = os.path.splitext(f)
            if ext not in [".rar", ".zip", ".7z", ".webp", ".avif"]:
                continue
            
            # apply regex replacement
            new_filename = re.sub(r"-\d-\d-\d{10}", "", filename)
            
            # only rename if changed
            if new_filename != filename:
                filepath = os.path.join(root, f)
                rename_file(filepath, new_filename)
                cnt += 1
    return cnt


if __name__ == "__main__":
    cnt = 0
    cnt += replace_dir(DOWNLOAD_DIR)
    # cnt += replace_dir(MODS_DIR)
                
    show_message("Done", f"{cnt} mods replaced")

