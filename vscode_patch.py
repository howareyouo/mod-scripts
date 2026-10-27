import re
import os
import json
import msvcrt
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

def remove_locale_paks(base_dir):
    """Delete all .pak files under <base_dir>/110a328ea5/locales except en-US.pak."""
    locales_dir = Path(base_dir) / "locales"
    if not locales_dir.is_dir():
        print(f"Locales dir not found, skipping: {locales_dir}")
        return
    for pak in locales_dir.glob("*.pak"):
        if pak.name == "en-US.pak":
            continue
        pak.unlink()
        print(f"Removed locale pak: {pak.name}")
    print("Locale paks cleaned.")

def apply_patches(base_dir):
    if disable_checksums(base_dir):
        return
    basename = f"{base_dir}/resources/app/out/vs/workbench/workbench.desktop.main"
    batfile = f"{base_dir}/resources/app/extensions/bat/language-configuration.json"
    css_patterns = [
        (r"Segoe WPC", "'Museo Sans 500'"),
        (r".issue-reporter-body .\w+:lang.*?\}", ""),
        (r".(windows|mac|linux)+:lang.*?\}", ""),
        (".titlebar-center{order:1;width:60%;", ".titlebar-center{order:1;width:25%;"),
    ]
    js_patterns = [(r"Segoe WPC", "Museo Sans 500"),
                   (r":host-context\(.\w+:lang.*\}\n", "")]
    print("Patching...")
    modify_file(basename + ".css", css_patterns)
    print("CSS: OK")
    modify_file(basename + ".js", js_patterns)
    print("JS: OK")
    modify_file(batfile, [(r'"lineComment":"@REM"', '"lineComment":"::"')])
    print("BAT: OK")
    remove_locale_paks(base_dir)

def get_editor_choice():
    editors = [
        ("VSCode", "D:/VSCode/", 10),
        ("Trae", "D:/Trae", None),
    ]

    def render(idx):
        for i, (name, path, _) in enumerate(editors):
            if i == idx:
                print(f"\x1b[96m > {name} \t({path})\x1b[0m")
            else:
                print(f"   {name} \t({path})")

    os.system('')  # enable ANSI escape sequences on Windows console
    idx = 0
    print("Select editor to patch (Up/Down + Enter):")
    render(idx)
    while True:
        key = msvcrt.getwch()
        if key in ('\x00', '\xe0'):
            key = msvcrt.getwch()
            if key == 'H':
                idx = (idx - 1) % len(editors)
            elif key == 'P':
                idx = (idx + 1) % len(editors)
            else:
                continue
        elif key == '\r':
            break
        elif key == '\x03':
            raise KeyboardInterrupt
        else:
            continue
        print(f"\x1b[{len(editors)}A\x1b[J", end="")
        render(idx)

    name, path, length = editors[idx]
    return name, path if length is None else path + find_dir_by_length(path, length)

if __name__ == '__main__':
    name, path = get_editor_choice()
    print(f"Selected: {name} ({path})")
    apply_patches(path)
    input("Press Enter to exit...")
