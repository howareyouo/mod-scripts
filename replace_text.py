import os
import re

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

# 是否在替换前先打印匹配信息而不真正写入（为 False 时才真正替换）
DRY_RUN = False


def apply_replacements(text):
    """依次应用所有正则替换，返回替换后的文本与替换次数。"""
    total = 0
    for pattern, replacement in REPLACEMENTS:
        text, count = re.subn(pattern, replacement, text)
        total += count
    return text, total


def main():
    if not os.path.isdir(TARGET_DIR):
        print(f"错误：目标文件夹不存在: {TARGET_DIR}")
        return

    compiled = [(re.compile(p), r) for p, r in REPLACEMENTS]
    processed = changed = 0

    for root, _dirs, files in os.walk(TARGET_DIR):
        for name in files:
            _, ext = os.path.splitext(name)
            if ext.lower() not in EXTENSIONS:
                continue

            file_path = os.path.join(root, name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original = f.read()
            except (UnicodeDecodeError, OSError) as e:
                print(f"跳过（无法读取）: {file_path} ({e})")
                continue

            text, count = apply_replacements(original)
            processed += 1

            if count == 0:
                continue

            changed += 1
            print(f"[{count:>3} 处] {file_path}")

            if DRY_RUN:
                continue

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)

    mode = "预览（未写入）" if DRY_RUN else "已替换"
    print(f"\n完成: 扫描 {processed} 个文件, {mode} {changed} 个文件")


if __name__ == "__main__":
    main()
