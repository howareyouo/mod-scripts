import os, sys, re, ctypes, threading, queue
from tkinter import messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
import tkinter as tk
import tkinter.font

CURRENT_PATH = Path(__file__)
CURRENT_DIR = CURRENT_PATH.parent

# 目标文件夹：执行时会对该文件夹下所有匹配扩展名的文件进行替换
TARGET_DIR = r"E:\RE4 Mods\Ada 1\Ada Nun Collection___"

# 要处理的文件扩展名（小写，含点）
EXTENSIONS = (
    ".ini",
)

# 正则表达式与对应替换字符串的映射表
# 每一项为 (regex_pattern, replacement)
REPLACEMENTS = (
    (r".*空中铁匠", ""),
    (r"description=.*\n", ""),
    (r"description=.*\n", ""),
    (r"screenshot=.*\n", ""),
    (r"category=.*\n", ""),
    (r"version=.*\n", ""),
    (r"name=.*\n", ""),
    (r"\n+", "\n"),
)

# 是否进行替换, 为否时只打印替换信息 (预览)
DRY_RUN = True

# 文件夹名称替换规则, 仅应用于目标目录下的直接子目录 (格式同 REPLACEMENTS)
FOLDER_REPLACEMENTS = REPLACEMENTS


def show_message(title, message):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()

def parse_list_field(text):
    """Parse a comma-separated text field into a tuple of non-empty items."""
    items = [item.strip() for item in text.replace("，", ",").split(",")]
    return tuple(item for item in items if item)

def parse_replacements(text):
    """Parse the rules textarea into (pattern, replacement) pairs.

    每行一条规则, 格式为 "pattern => replacement", 缺少 " => " 时替换文本视为空。
    """
    rules = []
    for line in text.splitlines():
        if not line.strip():
            continue
        # 先分割再去空白, 否则 "pattern => " (替换文本为空) 的行尾空格被去掉后无法分割
        # 分割出的 pattern 不做 strip, 保留用户故意写的行首/行尾空白 (如 " *xxx")
        if " => " in line:
            pattern, replacement = line.split(" => ", 1)
            replacement = replacement.strip()
        else:
            pattern, replacement = line.strip(), ""
        rules.append((pattern, replacement))
    return tuple(rules)

class QueueWriter:
    """把工作线程里 print 的输出转发到队列, 由 GUI 轮询显示到日志区。"""
    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, text):
        if text.strip():
            self.log_queue.put(text)

    def flush(self):
        pass

# 暗色主题配色
BG = "#1e1f22"          # 窗口/框架背景
FG = "#e0e0e0"          # 正文文字
ENTRY_BG = "#2a2c31"    # 输入框/日志背景
BTN_BG = "#33363c"      # 按钮背景
BTN_ACTIVE = "#44484f"  # 按钮按下/悬停背景
SELECT_BG = "#3b5b8a"   # 文本选中高亮

# 按控件类名 (winfo_class) 配置暗色样式, 未列出的控件保持默认
DARK_STYLES = {
    "Tk":          {"bg": BG},
    "Frame":       {"bg": BG},
    "Label":       {"bg": BG, "fg": FG},
    "Button":      {"bg": BTN_BG, "fg": FG, "activebackground": BTN_ACTIVE, "activeforeground": FG,
                    "relief": "flat", "bd": 0, "highlightthickness": 0},
    "Entry":       {"bg": ENTRY_BG, "fg": FG, "insertbackground": FG, "relief": "flat",
                    "highlightthickness": 1, "highlightbackground": BTN_BG, "highlightcolor": BTN_ACTIVE},
    "Text":        {"bg": ENTRY_BG, "fg": FG, "insertbackground": FG, "relief": "flat", "bd": 0,
                    "selectbackground": SELECT_BG, "selectforeground": FG},
    "Checkbutton": {"bg": BG, "fg": FG, "activebackground": BG, "activeforeground": FG, "selectcolor": ENTRY_BG},
    "Radiobutton": {"bg": BG, "fg": FG, "activebackground": BG, "activeforeground": FG, "selectcolor": ENTRY_BG},
    "Scrollbar":   {"bg": BTN_BG, "troughcolor": BG, "activebackground": BTN_ACTIVE, "bd": 0},
}

def apply_dark_theme(widget):
    """递归地给 widget 及其子控件应用暗色样式 (日志界面在运行时才创建, 需要再次调用)。"""
    opts = DARK_STYLES.get(widget.winfo_class())
    if opts:
        try:
            widget.configure(**opts)
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        apply_dark_theme(child)

def launch_gui():
    """Open a GUI window to collect settings, then run the replacement with live log output.

    Returns True if the job was started, None if the user closed the window without starting.
    """
    log_queue = queue.Queue()
    ui = {}
    started = [False]

    # DPI 感知: 避免 Windows 缩放导致字体模糊 (须在创建窗口前设置)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = tk.Tk()
    root.withdraw()  # 先隐藏窗口, 避免在计算居中位置时闪现
    root.title("文本替换工具")
    root.resizable(False, False)

    # 统一字体: Tk 的 Text 控件默认使用等宽字体, 与其他控件的系统默认字体不一致
    default_font = tk.font.nametofont("TkDefaultFont")
    text_font = tk.font.Font(font=default_font)
    root.option_add("*Text.font", text_font)

    frm = tk.Frame(root, padx=10, pady=10)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(0, weight=1)

    tk.Label(frm, text="目标文件夹 (TARGET_DIR):").grid(row=0, column=0, sticky="w")
    dir_var = tk.StringVar(value=TARGET_DIR)

    def browse_dir():
        chosen = filedialog.askdirectory(parent=root, initialdir=dir_var.get() or os.getcwd())
        if chosen:
            dir_var.set(os.path.normpath(chosen))

    tk.Button(frm, text="浏览...", command=browse_dir).grid(row=0, column=1, padx=(5, 0), sticky="e")
    tk.Entry(frm, textvariable=dir_var, width=70).grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 8))

    tk.Label(frm, text="文件扩展名 EXTENSIONS (逗号分隔, 含点, 如 .ini):").grid(row=2, column=0, sticky="w")
    ext_var = tk.StringVar(value=", ".join(EXTENSIONS))
    tk.Entry(frm, textvariable=ext_var, width=70).grid(row=3, column=0, columnspan=2, sticky="we", pady=(0, 8))

    tk.Label(frm, text="替换规则 REPLACEMENTS, 每行一条: 正则 => 替换文本 (省略 \" => \" 则删除匹配):").grid(row=4, column=0, sticky="w")
    rules_text = tk.Text(frm, width=70, height=10)
    rules_text.grid(row=5, column=0, columnspan=2, sticky="we", pady=(0, 8))
    for pattern, replacement in REPLACEMENTS:
        rules_text.insert("end", f"{pattern} => {replacement}\n")

    tk.Label(frm, text="文件夹名称替换规则 (仅目标目录的直接子目录, 每行一条: 正则 => 替换文本):").grid(row=6, column=0, sticky="w")
    folder_rules_text = tk.Text(frm, width=70, height=5)
    folder_rules_text.grid(row=7, column=0, columnspan=2, sticky="we", pady=(0, 8))
    for pattern, replacement in FOLDER_REPLACEMENTS:
        folder_rules_text.insert("end", f"{pattern} => {replacement}\n")

    dry_run_var = tk.BooleanVar(value=DRY_RUN)
    tk.Checkbutton(
        frm, text="仅预览 (不勾选则执行替换并写入文件)", variable=dry_run_var
    ).grid(row=8, column=0, sticky="w")

    def worker(directory, extensions, rules, folder_rules, dry_run):
        old = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = QueueWriter(log_queue)
        try:
            if folder_rules:
                rename_subdirs(directory, folder_rules, dry_run)
                print()
            run_replacements(directory, extensions, rules, dry_run)
        except Exception as e:
            print(f"发生错误: {e}")
        finally:
            sys.stdout, sys.stderr = old
            log_queue.put(None)  # 结束标记

    def poll_log():
        try:
            while True:
                item = log_queue.get_nowait()
                if item is None:
                    ui["status_var"].set("完成, 可以关闭窗口。")
                    root.protocol("WM_DELETE_WINDOW", root.destroy)
                    ui["close_btn"].config(state="normal")
                    return
                log_text = ui["log_text"]
                log_text.insert("end", item if item.endswith("\n") else item + "\n")
                log_text.see("end")
        except queue.Empty:
            pass
        root.after(100, poll_log)

    def on_close_while_running():
        messagebox.showinfo("提示", "正在运行, 请等待完成。", parent=root)

    def on_start():
        directory = dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
            messagebox.showerror("错误", f"目标文件夹无效:\n{directory}", parent=root)
            return
        extensions = parse_list_field(ext_var.get())
        if not extensions:
            messagebox.showerror("错误", "请至少填写一个文件扩展名。", parent=root)
            return
        rules = parse_replacements(rules_text.get("1.0", "end"))
        if not rules:
            messagebox.showerror("错误", "请至少填写一条替换规则。", parent=root)
            return
        # 文件夹名称替换为可选功能, 留空则不改名
        folder_rules = parse_replacements(folder_rules_text.get("1.0", "end"))
        dry_run = dry_run_var.get()
        started[0] = True

        # 切换到日志界面
        root.title("文本替换工具 - 运行中")
        root.resizable(True, True)
        frm.pack_forget()
        log_frame = tk.Frame(root, padx=10, pady=10)
        log_frame.pack(fill="both", expand=True)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        ui["log_text"] = ScrolledText(log_frame, width=90, height=25)
        ui["log_text"].grid(row=0, column=0, columnspan=2, sticky="nsew")
        ui["status_var"] = tk.StringVar(value="正在运行...")
        tk.Label(log_frame, textvariable=ui["status_var"], anchor="w").grid(row=1, column=0, sticky="w", pady=(5, 0))
        ui["close_btn"] = tk.Button(log_frame, text="关闭", command=root.destroy, state="disabled", width=12)
        ui["close_btn"].grid(row=1, column=1, sticky="e", pady=(5, 0))
        apply_dark_theme(log_frame)
        root.protocol("WM_DELETE_WINDOW", on_close_while_running)

        threading.Thread(target=worker, args=(directory, extensions, rules, folder_rules, dry_run), daemon=True).start()
        root.after(100, poll_log)

    tk.Button(frm, text="开始", command=on_start, width=12).grid(row=9, column=0, columnspan=2, pady=(10, 0))

    apply_dark_theme(root)

    # 窗口居中: 先刷新几何信息, 再按屏幕尺寸计算偏移
    root.update_idletasks()
    win_w = root.winfo_width()
    win_h = root.winfo_height()
    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()
    pos_x = max((scr_w - win_w) // 2, 0)
    pos_y = max((scr_h - win_h) // 2, 0)
    root.geometry(f"+{pos_x}+{pos_y}")
    root.deiconify()  # 计算好位置后再显示窗口

    root.lift()
    root.focus_force()
    root.mainloop()
    return True if started[0] else None

def rename_subdirs(target_dir, rules, dry_run):
    """对 target_dir 下的直接子目录名应用正则替换并重命名 (不递归)。"""
    compiled = [(re.compile(p), r) for p, r in rules]
    renamed = total_hits = 0
    try:
        entries = sorted(os.listdir(target_dir))
    except OSError as e:
        print(f"错误: 无法读取目录 {target_dir}: {e}")
        return

    for name in entries:
        path = os.path.join(target_dir, name)
        if not os.path.isdir(path):
            continue

        new_name = name
        count = 0
        for regex, replacement in compiled:
            new_name, n = regex.subn(replacement, new_name)
            count += n
        if count == 0 or new_name == name:
            continue

        new_path = os.path.join(target_dir, new_name)
        if os.path.exists(new_path):
            print(f"跳过 (目标已存在): {name} -> {new_name}")
            continue

        total_hits += count
        mode = "preview" if dry_run else "rename"
        print(f"{mode} [{count:>3} 处] {name} -> {new_name}")
        if not dry_run:
            try:
                os.rename(path, new_path)
            except OSError as e:
                print(f"错误: 重命名失败 {name}: {e}")
                continue
        renamed += 1

    mode = "预览（未改名）" if dry_run else "已改名"
    print(f"文件夹: 扫描直接子目录, {mode} {renamed} 个, 共 {total_hits} 处替换")

def find_excluded_files(target_dir, extensions):
    """找出需要排除的主 mod ini, 返回文件路径集合。

    1. 文件名 (不含扩展名) 与所在文件夹同名的 ini (mod 名默认使用文件夹名称)
    2. 其他 ini 中 addonfor= 引用的同名 ini (值可逗号分隔多个)
    """
    excluded = set()
    stems = {}  # 文件名 (不含扩展名, 小写) -> 文件路径列表
    addon_names = set()
    addon_re = re.compile(r"addonfor\s*=\s*(.+)", re.IGNORECASE)

    for root, _dirs, files in os.walk(target_dir):
        folder = os.path.basename(os.path.normpath(root))
        for name in files:
            stem, ext = os.path.splitext(name)
            if ext.lower() not in extensions:
                continue
            path = os.path.join(root, name)
            if stem == folder:
                excluded.add(path)
            stems.setdefault(stem.lower(), []).append(path)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for m in addon_re.finditer(content):
                for item in m.group(1).split(","):
                    item = item.strip()
                    if item.lower().endswith(".ini"):
                        item = item[:-4]
                    if item:
                        addon_names.add(item.lower())

    for addon_name in addon_names:
        excluded.update(stems.get(addon_name, []))
    return excluded

def run_replacements(target_dir=TARGET_DIR, extensions=EXTENSIONS, rules=REPLACEMENTS, dry_run=DRY_RUN):
    """遍历 target_dir, 对匹配扩展名的文件依次应用所有正则替换。

    主 mod ini (与文件夹同名, 或被 addonfor= 引用) 不做替换。
    """
    if not os.path.isdir(target_dir):
        print(f"错误：目标文件夹不存在: {target_dir}")
        return

    excluded = find_excluded_files(target_dir, extensions)
    if excluded:
        print(f"排除主 mod ini {len(excluded)} 个:")
        for path in sorted(excluded):
            print(f"  跳过: {path}")

    compiled = [(re.compile(p), r) for p, r in rules]
    processed = changed = total_hits = 0

    for root, _dirs, files in os.walk(target_dir):
        for name in files:
            _, ext = os.path.splitext(name)
            if ext.lower() not in extensions:
                continue

            file_path = os.path.join(root, name)
            if file_path in excluded:
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original = f.read()
            except (UnicodeDecodeError, OSError) as e:
                print(f"跳过（无法读取）: {file_path} ({e})")
                continue

            text = original
            count = 0
            for regex, replacement in compiled:
                text, n = regex.subn(replacement, text)
                count += n
            processed += 1

            if count == 0:
                continue

            changed += 1
            total_hits += count
            mode = "preview" if dry_run else "replace"
            print(f"{mode} [{count:>3} 处] {file_path}")

            if dry_run:
                continue

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)

    mode = "预览（未写入）" if dry_run else "已替换"
    print(f"\n完成: 扫描 {processed} 个文件, {mode} {changed} 个文件, 共 {total_hits} 处替换")

if __name__ == "__main__":
    # 双击直接运行: 打开 GUI 窗口收集配置, 并在窗口日志区运行显示结果
    launch_gui()
