import tkinter as tk
import os, csv
from tkinter import messagebox

current_dir = os.path.dirname(os.path.abspath(__file__))
tex_ext = ".143221013"

def show_message(title="Alert", message="This is an alert!"):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()

def extract_all_textures(filepath, current_dir):
    split = current_dir.lower().split("stm\\")
    dir_base = os.path.join(split[0],  "stm")
    mod_base = os.path.join(split[1].replace("\\", "/"))
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Name'] == "Texture File Path":
                val = row["Value"].lower().replace("\\", "/")
                if val.startswith(mod_base):
                    yield os.path.basename(val) + tex_ext
    return []

def remove_unused_textures(texture_set, texture_files):
    diff = [x for x in texture_files if x not in texture_set]
    if len(diff) > 0:
        unused_dir = os.path.join(current_dir, "unused")
        os.makedirs(unused_dir, exist_ok=True)
        for tex in diff:
            os.rename(
                os.path.join(current_dir, tex),
                os.path.join(unused_dir, tex)
            )
    return diff

if __name__ == "__main__":

    texture_set = set()
    texture_files = []

    files = os.listdir(current_dir)
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext == ".csv":
            csvfile = os.path.join(current_dir, f)
            texture_set.update(extract_all_textures(csvfile, current_dir))

        elif ext == tex_ext:
            texture_files.append(f.lower())

    removed = remove_unused_textures(texture_set, texture_files)
    show_message("Done", str(len(removed)) + " unussed textures removed")
