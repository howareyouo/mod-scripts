import os, sys, ctypes, shutil, hashlib, threading, queue
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

    frm = tk.Frame(root, padx=10, pady=10)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(0, weight=1)

    tk.Label(frm, text="游戏目录 (INGAME_DIR):").grid(row=0, column=0, sticky="w")
    dir_var = tk.StringVar(value=INGAME_DIR)

    def browse_dir():
        chosen = filedialog.askdirectory(parent=root, initialdir=dir_var.get() or os.getcwd())
        if chosen:
            dir_var.set(os.path.normpath(chosen))

    tk.Button(frm, text="浏览...", command=browse_dir).grid(row=0, column=1, padx=(5, 0), sticky="e")
    tk.Entry(frm, textvariable=dir_var, width=70).grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 8))

    tk.Label(frm, text="源文件 (DEFAULT_SOURCE_FILES), 每行一个:").grid(row=2, column=0, sticky="w")
    files_text = tk.Text(frm, width=70, height=6)
    files_text.grid(row=3, column=0, sticky="we", pady=(0, 8))
    for filepath in DEFAULT_SOURCE_FILES:
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
    prefix_var = tk.StringVar(value=", ".join(PREFIXES))
    tk.Entry(frm, textvariable=prefix_var, width=70).grid(row=5, column=0, columnspan=2, sticky="we", pady=(0, 8))

    tk.Label(frm, text="后缀 SUFFIXES (逗号分隔, 留空则不过滤):").grid(row=6, column=0, sticky="w")
    suffix_var = tk.StringVar(value=", ".join(SUFFIXES))
    tk.Entry(frm, textvariable=suffix_var, width=70).grid(row=7, column=0, columnspan=2, sticky="we", pady=(0, 8))

    switch_var = tk.BooleanVar(value=SWITCH)

    def toggle_source():
        if switch_var.get():
            source_frame.grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 0))
        else:
            source_frame.grid_forget()

    tk.Checkbutton(frm, text="执行替换 (不勾选则仅预览)", variable=switch_var, command=toggle_source).grid(row=8, column=0, sticky="w")

    source_var = tk.StringVar(value=HIDE_ATOC)
    source_frame = tk.Frame(frm)
    source_label = tk.Label(source_frame, text="替换源:")
    source_label.pack(side="left")
    rb_hide = tk.Radiobutton(source_frame, text="HIDE_ATOC", variable=source_var, value=HIDE_ATOC)
    rb_show = tk.Radiobutton(source_frame, text="SHOW_ATOC", variable=source_var, value=SHOW_ATOC)
    rb_pubs = tk.Radiobutton(source_frame, text="PUBS_SHOW", variable=source_var, value=PUBS_SHOW)
    rb_hide.pack(side="left", padx=(10, 0))
    rb_show.pack(side="left", padx=(10, 0))
    rb_pubs.pack(side="left", padx=(10, 0))

    if SWITCH:
        toggle_source()

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

    def poll_log():
        try:
            while True:
                item = log_queue.get_nowait()
                if item is None:
                    running[0] = False
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
        global INGAME_DIR, PREFIXES, SUFFIXES, SWITCH
        directory = dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
            messagebox.showerror("错误", f"游戏目录无效:\n{directory}", parent=root)
            return
        sources = [line.strip() for line in files_text.get("1.0", "end").splitlines() if line.strip()]
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

        # 切换到日志界面
        root.title("ATOC 替换工具 - 运行中")
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

        threading.Thread(target=worker, args=(sources, directory, SOURCE), daemon=True).start()
        root.after(100, poll_log)

    tk.Button(frm, text="开始", command=on_start, width=12).grid(row=10, column=0, columnspan=2, pady=(10, 0))

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

def replace_matching_files(directory=INGAME_DIR, hashes=None, source=HIDE_ATOC):
    if hashes is None:
        hashes = []
    matches = []
    for root, dirs, files in os.walk(directory, topdown=True):
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
                        print(f"replace {shorten_path(filename):<60} size: {file_size}")
                    else:
                        print(f"preview {shorten_path(filename):<60} size: {file_size}")
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
