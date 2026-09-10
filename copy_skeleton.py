import os, shutil, fnmatch, hashlib
import tkinter as tk
from tkinter import messagebox
from pathlib import Path


CURRENT_PATH = Path(__file__)
CURRENT_DIR = CURRENT_PATH.parent
RE4_RESOURCES = "C:/Users/hunan/Desktop/RE4 Resources/"
CHA800_10_MESH = RE4_RESOURCES + "10/cha800_10.mesh.221108797"
CHA800_10_MDF = RE4_RESOURCES + "10/cha800_10.mdf2.32"
CHA800_14_FACEBLEND_MDF = RE4_RESOURCES + "14/cha800_14_faceblend.mdf2.32"
CHA800_14_FACEBLEND_ALBD = RE4_RESOURCES + "14/cha800_14_faceblend_albd.tex.143221013"
SKEL_SHA256= "7666a35141deadc3513de1c54aa5013623bb5dcb57dcd2595c00d71839af915d"

def show_message(title, message):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()

def get_file_hash(filepath, algorithm='sha256'):
    hash_obj = hashlib.new(algorithm)
    
    with open(filepath, 'rb') as f:
        # 分块读取，避免大文件占用过多内存
        chunk_size = 8192
        while chunk := f.read(chunk_size):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()


def shorten_path(path: Path, only_name=False):
    mod_name = str(path).partition("\\natives")[0].rpartition("\\")[2]
    file_name = str(path).rpartition("\\ch\\")[2].rpartition("\\")[2].rpartition(".")[0]
    return f"{file_name}" if only_name else f"[{mod_name}] {file_name}"


def copy_newer(source, target):
    source_path = Path(source)
    target_path = Path(target)

    dest = None
    if target_path.exists():
        source_mtime = source_path.stat().st_mtime
        target_mtime = target_path.stat().st_mtime
        if source_mtime > target_mtime:
            dest = shutil.copy2(source_path, target_path)
            print(f"Copying {shorten_path(source_path)} (newer) to {shorten_path(target_path, True)}")
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        dest = shutil.copy2(source_path, target_path)
        print(f"Copying {shorten_path(source_path)} to {shorten_path(target_path, True)}")

    return 1 if dest else 0


def copy_absent(source, target):
    if os.path.exists(target):
        return 0
    
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(source, target)
    print(f"Copying {shorten_path(source)} to {shorten_path(target, True)}")
    return 1


def copy_skeleton(fullpath):
    path = Path(fullpath)
    copied = 0
    if path.parent.name in ["cha1", "cha2"]:
        if get_file_hash(fullpath) == SKEL_SHA256:
            target = path.parent.with_name("cha0") / "cha000.skeleton.5"
            copied += copy_absent(path, target)
        
        if path.parent.name == "cha2":
            target_file = str(path).replace("_chainsaw", "_mercenaries").replace("cha2", "cha8")
            target = Path(target_file).with_name("cha800.fbxskel.5")
            copied += copy_absent(path, target)
            
    return copied


def copy_meshes(source, name):
    target = source.replace("_chainsaw", "_mercenaries").replace("cha2", "cha8")
    copied = 0
    if name == "cha200_10.mesh.221108797":
        copied += copy_absent(source, target)
        # target = target.replace("cha800\\10", "cha800\\11").replace("cha800_10", "cha800_11")
        copied += copy_absent(source, target)
    else:
        copied += copy_newer(source, target)

    return copied

def copy_mdf(source, name):
    target = source.replace("_chainsaw", "_mercenaries").replace("cha2", "cha8")
    copied = 0
    
    if name == "cha200_10.mdf2.32":
        copied += copy_absent(source, target)
        # target = target.replace("cha800\\10", "cha800\\11").replace("cha800_10", "cha800_11")
        # copied += copy_absent(source, target)
        # target = target.replace("cha800\\11", "cha800\\14").replace("cha800_11", "cha800_14_faceblend")
        target = target.replace("cha800\\10", "cha800\\14").replace("cha800_10", "cha800_14_faceblend")
        # copied += copy_absent(CHA800_14_FACEBLEND_MDF, target)
        target = target.replace(".mdf2.32", "_albd.tex.143221013")
        # copy_absent(CHA800_14_FACEBLEND_ALBD, target)
    else:
        copied += copy_newer(source, target)

    return copied

def copy_pfb(source):
    target = source.replace("ch2a1z0", "ch0a0z0").replace("cha100", "cha000")
    return copy_newer(source, target)

def copy_chain(source, filename):
    source_path = Path(source).parent.parent.parent / filename.replace("mesh.221108797", "chain.53")
    if not source_path.exists():
        return 0

    copied = 0
    source = str(source_path)
    target = source.replace("_chainsaw", "_mercenaries").replace("cha2", "cha8")
    copied += copy_newer(source, target)

    if target.endswith("cha800_20.chain.53"):
        copied += copy_absent(target, target.replace("cha800_20.chain.53", "cha801_20_figure.chain.53"))
        copied += copy_absent(target, target.replace("cha800_20.chain.53", "cha803_20_figure.chain.53"))

    return copied


mesh_files = [
    "cha200_00.mesh.221108797",
    "cha200_20.mesh.221108797",
    "cha200_10.mesh.221108797",
]

mdf_files = [
    "cha200_00.mdf2.32",
    "cha200_20.mdf2.32",
    "cha200_10.mdf2.32",
]

# INGAME_DIR = "E:/RE4R Mods/InGame_face"
INGAME_DIR = os.getcwd()
print("Working dir:", INGAME_DIR)

if __name__ == "__main__":
    skeletons = 0 
    chains = 0
    meshes = 0
    mdfs = 0
    pfbs = 0
    for root, dirs, files in os.walk(INGAME_DIR, topdown=False):
        if not "\\_chainsaw\\" in root:
            continue

        for name in files:
            fullpath = os.path.join(root, name)

            if fnmatch.fnmatch(name, "cha100_10*.pfb.17"):
                pfbs += copy_pfb(fullpath)

            elif fnmatch.fnmatch(name, "cha*.fbxskel.5"):  
                skeletons += copy_skeleton(fullpath)

            elif name in mesh_files:
                meshes += copy_meshes(fullpath, name)
                chains += copy_chain(fullpath, name)

            elif name in mdf_files:
                mdfs += copy_mdf(fullpath, name)

    show_message("Done", f"{skeletons} skeleton copied\n{chains} chain copied\n{meshes} mesh copied\n{mdfs} mdf copied\n{pfbs} pfd copied")
