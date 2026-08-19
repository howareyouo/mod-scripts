import tkinter as tk
import os, re
from tkinter import messagebox


def show_message(title="Alert", message="This is an alert!"):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()


image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

def rename_screenshot(directory, filenames):
    imgfile = None
    newfile = None
    for filename in filenames:
        name, ext = os.path.splitext(filename.lower())
        if ext in image_extensions:
            if name == "screenshot":
                return
            if not imgfile:
                imgfile = os.path.join(directory, filename)
                newfile = os.path.join(directory, "screenshot" + ext)

    if imgfile:
        os.rename(imgfile, newfile)
        print("rename screenshot", imgfile)
        return imgfile
        

def replace_modeinfo(filepath: str) -> int:
    if not os.path.isfile(filepath):
        return 0

    with open(filepath, 'r+') as file:
        content = file.read()
        content = re.sub(r'screenshot\s*=\s*.*\n?', '', content)
        content = re.sub(r'category=!', 'category=', content)
        content = re.sub(r'category=Ashley(\Z|\n)', '', content)
        content = re.sub(r'category=Ada(\Z|\n)', '', content)
        content = re.sub(r'category=Hair\b', 'category=Hairs', content)
        content = re.sub(r'name\s*=\s*.*\n?', '', content)
        content = re.sub(r'(\s*\n)+\Z', '', content)        
        
        # Rewrite efficiently
        file.seek(0)
        file.write(content)
        file.truncate()  # Remove any leftover content if new content is shorter
    return 1


# WORKING_DIR = "E:\\RE4 Mods\\InGame"
WORKING_DIR = os.getcwd()

print("Working dir:", WORKING_DIR)
if __name__ == "__main__":
    del_cnt = 0
    ren_cnt = 0
    for dirpath, dirnames, filenames in os.walk(WORKING_DIR, topdown=False):
        if dirpath == WORKING_DIR:
            continue

        depth = dirpath.count(os.sep) - WORKING_DIR.count(os.sep)
        if depth <= 3:
            if replace_modeinfo(os.path.join(dirpath, "modinfo.ini")):
                if rename_screenshot(dirpath, filenames):
                    ren_cnt += 1

        # Check if the directory is empty
        if os.listdir(dirpath):
            start_index = dirpath.lower().find("natives")
            if start_index != -1:
                subbefore = dirpath[0:start_index]
                substring = dirpath[start_index:]
                # rename to lowercase
                if substring != substring.lower():
                    os.rename(dirpath, subbefore + substring.lower())
        else:
            os.rmdir(dirpath)
            del_cnt += 1
            print(f"Deleted: {dirpath}")

    show_message("Done", f"{del_cnt} empty folders deleted\n{ren_cnt} screenshots renamed")
