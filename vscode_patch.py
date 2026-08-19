import re
import os
import json
from pathlib import Path

def find_dir_by_length(folder, length):
    return next((d for d in os.listdir(folder) if len(d) == length), None)

def modify_file(file_path, patterns):
    compiled = [(re.compile(p), r) for p, r in patterns]
    def _replace(match):
        text = match.group()
        for pattern, replacement in compiled:
            if pattern.search(text):
                return replacement
        return text

    combined = '|'.join(f'(?:{p})' for p, _ in patterns)
    with open(file_path, 'r+', encoding='utf-8') as f:
        content = re.sub(combined, _replace, f.read())
        f.seek(0)
        f.write(content)
        f.truncate()

def disable_checksums(build_dir):
    """Clear checksums. Returns True if already cleared, False otherwise."""
    target = Path(f"{build_dir}/resources/app/product.json")
    with open(target, 'r+', encoding='utf-8') as f:
        config = json.load(f)
        if not config.get('checksums'):
            print("Already patched, skipping.")
            return True
        config['checksums'] = {}
        f.seek(0)
        json.dump(config, f, indent='\t')
        f.truncate()
        print("Checksums removed.")
        return False

def apply_patches(base_dir):
    if disable_checksums(base_dir):
        return
    basename = f"{base_dir}/resources/app/out/vs/workbench/workbench.desktop.main"
    batfile = f"{base_dir}/resources/app/extensions/bat/language-configuration.json"
    css_patterns = [(r"Segoe WPC", "'Museo Sans 500'"),
                    (r".issue-reporter-body .\w+:lang.*?\}", ""),
                    (r".(windows|mac|linux)+:lang.*?\}", "")]
    js_patterns = [(r"Segoe WPC", "Museo Sans 500"),
                   (r":host-context\(.\w+:lang.*\}\n", "")]
    print("Patching...")
    modify_file(basename + ".css", css_patterns)
    print("CSS: OK")
    modify_file(basename + ".js", js_patterns)
    print("JS: OK")
    modify_file(batfile, [(r'"lineComment":"@REM"', '"lineComment":"::"')])
    print("BAT: OK")

def get_editor_choice():
    editors = [
        ("VSCode", "D:/VSCode/", 10),
        ("Trae", "D:/Trae", None),
    ]
    n = len(editors)
    print("Select editor to patch:")
    for i, (name, path, _) in enumerate(editors, start=1):
        print(f"  {i}. {name} \t({path})")

    while True:
        c = input(f"Option (1-{n}): ").strip()
        if c.isdigit():
            idx = int(c)
            if 1 <= idx <= n:
                name, path, length = editors[idx - 1]
                return name, path if length is None else path + find_dir_by_length(path, length)
        print(f"Invalid option: {c}, please try again.")

if __name__ == '__main__':
    name, path = get_editor_choice()
    print(f"Selected: {name} ({path})")
    apply_patches(path)
    input("Press Enter to exit...")
