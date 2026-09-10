import os, sys, ctypes, shutil, hashlib, threading, queue, json
from collections import defaultdict
from tkinter import messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
import tkinter as tk
import tkinter.font

CURRENT_PATH = Path(__file__)
CURRENT_DIR = CURRENT_PATH.parent
TEXTURES_DIR = "E:/RE4 Mods/Mods Resources/_/"
HIDE_ATOC = TEXTURES_DIR + "hide_ATOC.tex.143221013"
SHOW_ATOC = TEXTURES_DIR + "show_ATOC.tex.143221013"
PUBS_SHOW = TEXTURES_DIR + "pubs_SHOW.tex.143221013"
PREFIXES = (
    "Remov_",
)
SUFFIXES = (
    "_atos.tex",
    "_atoc.tex",
    "_atoc2.tex",
)
INGAME_DIR = r"E:\RE4 Mods\InGame\Ada Harley Quinn"

# GUI 窗口中默认填入的源文件列表
DEFAULT_SOURCE_FILES = [
    r"E:\RE4 Mods\InGame\Ada Harley Quinn\Ada Harley Quinn\natives\stm\_chainsaw\character\ch\cha2\cha200\00\Remov_Boots.tex.143221013"
]

# 是否进行替换, 为否时只打印替换信息
SWITCH = False

def show_message(title, message):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo(title, message)
    root.destroy()

def shorten_path(path):
    s = path.replace(INGAME_DIR, "")
    s = s.replace(r"natives\stm\_chainsaw\character\ch\cha2\cha200", "..")
    return s.rpartition('.')[0]

def get_file_hash(filepath, algorithm='sha256'):
    hash_obj = hashlib.new(algorithm)
    
    with open(filepath, 'rb') as f:
        # 分块读取，避免大文件占用过多内存
        chunk_size = 8192
        while chunk := f.read(chunk_size):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()

def format_filesize(filepath):
    size_bytes = os.path.getsize(filepath)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

def parse_list_field(text):
    """Parse a comma-separated text field into a tuple of non-empty items."""
    items = [item.strip() for item in text.replace("，", ",").split(",")]
    return tuple(item for item in items if item)

def clean_path_line(line):
    """去掉复制路径时可能带上的首尾空白和双引号。"""
    return line.strip().strip('"').strip()

# 用户上次输入/选择的持久化文件 (与脚本同目录)
CONFIG_FILE = CURRENT_DIR / "replace_atoc_config.json"

def load_config():
    """读取上次的 GUI 设置, 缺失或损坏时回退到脚本顶部的默认值。"""
    defaults = {
        "directory": INGAME_DIR,
        "sources": list(DEFAULT_SOURCE_FILES),
        "prefixes": ", ".join(PREFIXES),
        "suffixes": ", ".join(SUFFIXES),
        "switch": SWITCH,
        "source": HIDE_ATOC,
    }
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        for key in defaults:
            if key in saved:
                defaults[key] = saved[key]
    except (OSError, ValueError):
        pass
    if isinstance(defaults["sources"], list):
        defaults["sources"] = [clean_path_line(s) for s in defaults["sources"] if clean_path_line(s)]
    if defaults["source"] not in (HIDE_ATOC, SHOW_ATOC, PUBS_SHOW):
        defaults["source"] = HIDE_ATOC
    return defaults

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

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
    running = [True]

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
    root.title("ATOC 替换工具")
    root.resizable(False, False)

    # 统一字体: Tk 的 Text 控件默认使用等宽字体, 与其他控件的系统默认字体不一致
    default_font = tk.font.nametofont("TkDefaultFont")
    text_font = tk.font.Font(font=default_font)
    root.option_add("*Text.font", text_font)
    # 日志区使用等宽字体, 保证路径/大小等列对齐
    mono_font = tk.font.Font(family="Consolas", size=10)

    frm = tk.Frame(root, padx=10, pady=10)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(0, weight=1)

    cfg = load_config()

    tk.Label(frm, text="游戏目录 (INGAME_DIR):").grid(row=0, column=0, sticky="w")
    dir_var = tk.StringVar(value=cfg["directory"])

    def browse_dir():
        chosen = filedialog.askdirectory(parent=root, initialdir=dir_var.get() or os.getcwd())
        if chosen:
            dir_var.set(os.path.normpath(chosen))

    dir_row = tk.Frame(frm)
    dir_row.grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 8))
    dir_entry = tk.Entry(dir_row, textvariable=dir_var, width=70)
    browse_btn = tk.Button(dir_row, text="浏览...", command=browse_dir)
    # 以两者中较高者的请求高度作为整行高度, 输入框/按钮都纵向填满, 高度完全一致
    root.update_idletasks()
    dir_row.configure(height=max(dir_entry.winfo_reqheight(), browse_btn.winfo_reqheight()))
    dir_entry.pack(side="left", fill="y")
    browse_btn.pack(side="left", padx=(5, 0), fill="both", expand=True)

    tk.Label(frm, text="源文件 (DEFAULT_SOURCE_FILES), 每行一个:").grid(row=2, column=0, sticky="w")
    files_text = tk.Text(frm, width=70, height=6)
    files_text.grid(row=3, column=0, sticky="we", pady=(0, 8))
    for filepath in cfg["sources"]:
        files_text.insert("end", filepath + "\n")

    def add_files():
        for filepath in filedialog.askopenfilenames(
            parent=root,
            title="Select source texture files",
            filetypes=[("Texture files", "*.tex.143221013"), ("All files", "*.*")],
        ):
            files_text.insert("end", filepath + "\n")

    tk.Button(frm, text="添加文件...", command=add_files).grid(row=3, column=1, sticky="n", padx=(5, 0))

    tk.Label(frm, text="前缀 PREFIXES (逗号分隔, 留空则不过滤):").grid(row=4, column=0, sticky="w")
    prefix_var = tk.StringVar(value=cfg["prefixes"])
    tk.Entry(frm, textvariable=prefix_var, width=70).grid(row=5, column=0, columnspan=2, sticky="we", pady=(0, 8), ipady=3)

    tk.Label(frm, text="后缀 SUFFIXES (逗号分隔, 留空则不过滤):").grid(row=6, column=0, sticky="w")
    suffix_var = tk.StringVar(value=cfg["suffixes"])
    tk.Entry(frm, textvariable=suffix_var, width=70).grid(row=7, column=0, columnspan=2, sticky="we", pady=(0, 8), ipady=3)

    switch_var = tk.BooleanVar(value=cfg["switch"])

    def toggle_source():
        if switch_var.get():
            source_frame.grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 0))
        else:
            source_frame.grid_forget()

    tk.Checkbutton(frm, text="执行替换 (不勾选则仅预览)", variable=switch_var, command=toggle_source).grid(row=8, column=0, sticky="w")

    source_var = tk.StringVar(value=cfg["source"])
    source_frame = tk.Frame(frm)
    source_label = tk.Label(source_frame, text="替换源:")
    source_label.pack(side="left")
    rb_hide = tk.Radiobutton(source_frame, text="HIDE_ATOC", variable=source_var, value=HIDE_ATOC)
    rb_show = tk.Radiobutton(source_frame, text="SHOW_ATOC", variable=source_var, value=SHOW_ATOC)
    rb_pubs = tk.Radiobutton(source_frame, text="PUBS_SHOW", variable=source_var, value=PUBS_SHOW)
    rb_hide.pack(side="left", padx=(10, 0))
    rb_show.pack(side="left", padx=(10, 0))
    rb_pubs.pack(side="left", padx=(10, 0))

    if switch_var.get():
        toggle_source()

    def save_current():
        """把当前界面上的输入/选择写入配置文件。"""
        save_config({
            "directory": dir_var.get().strip(),
            "sources": [clean_path_line(line) for line in files_text.get("1.0", "end").splitlines() if clean_path_line(line)],
            "prefixes": prefix_var.get(),
            "suffixes": suffix_var.get(),
            "switch": switch_var.get(),
            "source": source_var.get(),
        })

    def on_close():
        save_current()
        root.destroy()

    def worker(sources, directory, source):
        old = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = QueueWriter(log_queue)
        try:
            print("正在计算源文件哈希...")
            hashes = get_hashes_from_files(sources)
            if not hashes:
                print("未计算出任何有效哈希, 退出。")
                return
            print(f"开始扫描目录: {directory}")
            matches = replace_matching_files(directory, hashes, source)
            print(f"完成, 共替换 {len(matches)} 个贴图")
        except Exception as e:
            print(f"发生错误: {e}")
        finally:
            sys.stdout, sys.stderr = old
            log_queue.put(None)  # 结束标记

    def back_to_main():
        """销毁日志界面, 返回主设置界面 (不退出程序)。"""
        ui["log_frame"].destroy()
        root.title("ATOC 替换工具")
        root.resizable(False, False)
        frm.pack(fill="both", expand=True)
        root.protocol("WM_DELETE_WINDOW", on_close)

    def poll_log():
        try:
            while True:
                item = log_queue.get_nowait()
                if item is None:
                    running[0] = False
                    ui["status_var"].set("完成, 点击关闭返回主界面。")
                    root.protocol("WM_DELETE_WINDOW", back_to_main)
                    ui["close_btn"].config(state="normal", command=back_to_main)
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
        global INGAME_DIR, PREFIXES, SUFFIXES, SWITCH
        directory = dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
            messagebox.showerror("错误", f"游戏目录无效:\n{directory}", parent=root)
            return
        sources = [clean_path_line(line) for line in files_text.get("1.0", "end").splitlines() if clean_path_line(line)]
        if not sources:
            messagebox.showerror("错误", "请至少填写一个源文件。", parent=root)
            return
        missing = [s for s in sources if not os.path.isfile(s)]
        if missing and not messagebox.askyesno(
            "确认", "以下源文件不存在:\n" + "\n".join(missing) + "\n\n是否仍然继续?", parent=root
        ):
            return

        INGAME_DIR = directory
        PREFIXES = parse_list_field(prefix_var.get())
        SUFFIXES = parse_list_field(suffix_var.get())
        SWITCH = switch_var.get()
        SOURCE = source_var.get()
        started[0] = True
        save_current()

        # 切换到日志界面
        root.title("ATOC 替换工具 - 运行中")
        root.resizable(True, True)
        frm.pack_forget()
        log_frame = tk.Frame(root, padx=10, pady=10)
        log_frame.pack(fill="both", expand=True)
        ui["log_frame"] = log_frame
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        ui["log_text"] = ScrolledText(log_frame, width=90, height=25, font=mono_font)
        ui["log_text"].grid(row=0, column=0, columnspan=2, sticky="nsew")
        ui["status_var"] = tk.StringVar(value="正在运行...")
        tk.Label(log_frame, textvariable=ui["status_var"], anchor="w").grid(row=1, column=0, sticky="w", pady=(5, 0))
        ui["close_btn"] = tk.Button(log_frame, text="关闭", command=back_to_main, state="disabled", width=12)
        ui["close_btn"].grid(row=1, column=1, sticky="e", pady=(5, 0))
        apply_dark_theme(log_frame)
        root.protocol("WM_DELETE_WINDOW", on_close_while_running)

        threading.Thread(target=worker, args=(sources, directory, SOURCE), daemon=True).start()
        root.after(100, poll_log)

    def on_delete_backups():
        """删除当前目录下所有 _backup 备份文件夹。"""
        directory = dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
            messagebox.showerror("错误", f"游戏目录无效:\n{directory}", parent=root)
            return
        backup_dirs = []
        file_count = 0
        for root_dir, dirs, files in os.walk(directory, topdown=True):
            if "_backup" in dirs:
                backup_dir = os.path.join(root_dir, "_backup")
                file_count += sum(len(fs) for _, _, fs in os.walk(backup_dir))
                backup_dirs.append(backup_dir)
            # 不进入 _backup 内部继续遍历
            dirs[:] = [d for d in dirs if d != "_backup"]
        if not backup_dirs:
            messagebox.showinfo("提示", "未找到任何 _backup 文件夹。", parent=root)
            return
        if not messagebox.askyesno(
            "确认",
            f"将删除 {len(backup_dirs)} 个 _backup 文件夹, 共 {file_count} 个文件。\n此操作不可恢复, 是否继续?",
            parent=root,
        ):
            return
        deleted = failed = 0
        for backup_dir in backup_dirs:
            try:
                shutil.rmtree(backup_dir)
                deleted += 1
            except (OSError, PermissionError) as e:
                failed += 1
                print(f"删除失败: {backup_dir}: {e}")
        if failed:
            messagebox.showwarning("完成", f"成功删除 {deleted} 个 _backup 文件夹, {failed} 个删除失败。", parent=root)
        else:
            messagebox.showinfo("完成", f"已删除 {deleted} 个 _backup 文件夹。", parent=root)

    btns = tk.Frame(frm)
    btns.grid(row=10, column=0, columnspan=2, sticky="we", pady=(10, 0))
    btns.columnconfigure(1, weight=1)  # 中间留空, 把右侧按钮推到最后
    tk.Button(btns, text="开始", command=on_start, width=12).grid(row=0, column=0, sticky="w")
    del_btn = tk.Button(btns, text="删除备份", command=on_delete_backups, width=12, fg="#ff6961")
    del_btn.grid(row=0, column=2, sticky="e")

    apply_dark_theme(root)
    # 暗色主题会覆盖按钮前景色, 最后再单独把删除备份设回柔和的红色
    del_btn.config(fg="#ff6961", activeforeground="#ef8080")

    # 窗口居中: 先刷新几何信息, 再按屏幕尺寸计算偏移
    # 窗口未映射时, winfo_width/height 会被第一次 update_idletasks 锁定成旧值,
    # 因此用请求尺寸 winfo_req* 计算居中 (resizable=False, 实际尺寸即请求尺寸)
    root.update_idletasks()
    win_w = root.winfo_reqwidth()
    win_h = root.winfo_reqheight()
    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()
    pos_x = max((scr_w - win_w) // 2, 0)
    pos_y = max((scr_h - win_h) // 2, 0)
    root.geometry(f"+{pos_x}+{pos_y}")
    root.deiconify()  # 计算好位置后再显示窗口

    root.lift()
    root.focus_force()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return True if started[0] else None

def replace_matching_files(directory=INGAME_DIR, hashes=None, source=HIDE_ATOC):
    if hashes is None:
        hashes = []
    matches = []
    for root, dirs, files in os.walk(directory, topdown=True):
        # 跳过备份目录, 避免把上次备份的文件再次替换掉
        dirs[:] = [d for d in dirs if d != "_backup"]
        for name in files:
            filename, ext = os.path.splitext(name)
            if ext != ".143221013":
                continue
            # 前缀和后缀任意一个匹配即可通过 (留空的项不参与过滤)
            suffix_ok = SUFFIXES and filename.lower().endswith(SUFFIXES)
            prefix_ok = PREFIXES and filename.startswith(PREFIXES)
            if not (suffix_ok or prefix_ok):
                continue
            filepath = os.path.join(root, name)
            if get_file_hash(filepath) in hashes:
                file_size = format_filesize(filepath)
                try:
                    backup_dir = os.path.join(root, "_backup")
                    os.makedirs(backup_dir, exist_ok=True)
                    backup_name = os.path.basename(filepath)
                    backup_path = os.path.join(backup_dir, backup_name)
                    if SWITCH:
                        shutil.move(filepath, backup_path)
                        shutil.copy2(source, filepath)
                        print(f"replace {shorten_path(filename):<40} size: {file_size:>10}")
                    else:
                        print(f"preview {shorten_path(filename):<40} size: {file_size:>10}")
                except (OSError, PermissionError) as e:
                    print(f"Warning: Unable to create or move to backup folder {backup_dir}: {e}")

                matches.append(filename)
    return matches

def get_hashes_from_files(filepaths):
    """Calculate hashes from a list of file paths."""
    hashes = []
    for filepath in filepaths:
        if os.path.isfile(filepath):
            try:
                file_hash = get_file_hash(filepath)
                hashes.append(file_hash)
                print(f"Computed hash for {filepath}: {file_hash}")
            except Exception as e:
                print(f"Error computing hash for {filepath}: {e}")
        else:
            print(f"File not found: {filepath}")
    return hashes

if __name__ == "__main__":
    # 双击直接运行: 打开 GUI 窗口收集配置, 并在窗口日志区运行显示结果
    launch_gui()
