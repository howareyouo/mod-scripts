import os, shutil, fnmatch
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from copy_skeleton import copy_newer, copy_absent


def show_message(title, message):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()


def shorten_path(path: Path, only_name=False):
    mod_name = str(path).partition("\\natives")[0].rpartition("\\")[2]
    file_name = str(path).rpartition("\\ch\\")[2].rpartition("\\")[2].rpartition(".")[0]
    return f"{file_name}" if only_name else f"[{mod_name}] {file_name}"

def copy_skeleton(fullpath):
    target_file = fullpath.replace("_mercenaries", "_chainsaw").replace("cha8", "cha2")
    target = Path(target_file).with_name("cha800.fbxskel.5")
    return copy_absent(fullpath, target)

def copy_meshes(source, name):
    target = source.replace("_mercenaries", "_chainsaw").replace("cha8\cha801", "cha2\cha200")
    return copy_absent(source, target)

def copy_mdf(source, name):
    target = source.replace("_mercenaries", "_chainsaw").replace("cha8\cha801", "cha2\cha200")
    return copy_absent(source, target)

mesh_files = [
    "cha801_01.mesh.221108797",
]

mdf_files = [
    "cha801_01.mdf2.32",
]

MOD_DIR = "E:/RE4R Mods/InGame"

if __name__ == "__main__":
    skeletons = 0 
    chains = 0
    meshes = 0
    mdfs = 0
    for root, dirs, files in os.walk(MOD_DIR, topdown=False):
        if not "\\_mercenaries\\" in root:
            continue

        for name in files:
            fullpath = os.path.join(root, name)

            if fnmatch.fnmatch(name, "cha*.fbxskel.5"):
                skeletons += copy_skeleton(fullpath)

            elif name in mesh_files:
                meshes += copy_meshes(fullpath, name)

            elif name in mdf_files:
                mdfs += copy_mdf(fullpath, name)

    show_message("Done", f"{skeletons} skeleton copied\n{chains} chain copied\n{meshes} mesh copied\n{mdfs} mdf copied")
