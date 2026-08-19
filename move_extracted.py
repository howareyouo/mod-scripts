from tkinter import messagebox
from pathlib import Path
from copy_skeleton import copy_absent, copy_newer
import tkinter as tk
import os, shutil


def show_message(title="Alert", message="This is an alert!"):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()


def move_extract_folders(root):
    deleted_count = 0
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Skip the root directory itself if it's empty
        if dirpath.endswith("__UNKNOWN") and len(dirnames) == 0:
            natives = Path(dirpath).parent / "natives"
            if natives.exists():
                print(dirpath)
                path_to_move = natives.parent.parent / "natives"
                shutil.move(str(natives), str(path_to_move))
                shutil.rmtree(natives.parent) 
                pakfile = natives.parent.with_suffix(".pak")
                pakfile.unlink(missing_ok=True)
                deleted_count += 1

        if dirpath.endswith("awldbd"):
            for file in filenames:
                if file == "awldbd_blabit.mesh.221108797":
                    source = Path(dirpath) / file
                    target = Path(dirpath).parent.parent / "ch/cha2/cha200/00/cha200_00.mesh.221108797"
                    copy_absent(source, target)
                elif file == "awldbd_blabit.mdf2.32":
                    source = Path(dirpath) / file
                    target = Path(dirpath).parent.parent / "ch/cha2/cha200/00/cha200_00.mdf2.32"
                    copy_absent(source, target)
        
        if dirpath.endswith("awldfc"):
            for file in filenames:
                if file == "awldfc_blabit.mesh.221108797":
                    source = Path(dirpath) / file
                    target = Path(dirpath).parent.parent / "ch/cha2/cha200/10/cha200_10.mesh.221108797"
                    copy_absent(source, target)
                elif file == "awldfc_blabit.mdf2.32":
                    source = Path(dirpath) / file
                    target = Path(dirpath).parent.parent / "ch/cha2/cha200/10/cha200_10.mdf2.32"
                    copy_absent(source, target)

    return deleted_count


extract_dir = "E:\RE4R Mods\InGame\Little Danger"


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))

    moved_count = move_extract_folders(extract_dir)

    show_message("Done", f"{moved_count} natives folders moved up.")
