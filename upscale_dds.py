#!/usr/bin/env python3
"""
upscale_dds.py
使用 Real-ESRGAN 将 DDS 文件放大并保存为 PNG(或也保存为DDS,取决于后端支持)。
支持批量：传入文件、多个文件，或传入目录处理目录下所有 .dds 文件。
需要: pillow, pillow-dds, torch, realesrgan
"""

import sys
import os
from pathlib import Path
from PIL import Image
# 确保 pillow-dds 已安装，否则读取 DDS 可能失败

try:
    from realesrgan import RealESRGAN
except Exception as e:
    print("无法导入 Real-ESRGAN。请确认已安装 'realesrgan' 包。")
    raise

def collect_inputs(args):
    paths = []
    if not args:
        print("用法: python upscale_dds.py <file_or_dir> [more_files_or_dirs...]")
        sys.exit(1)
    for a in args:
        p = Path(a)
        if p.is_dir():
            for f in p.glob("*.dds"):
                paths.append(f)
        elif p.is_file():
            paths.append(p)
        else:
            print(f"警告: 未找到 {a} （跳过）")
    return paths

def ensure_outdir(in_path: Path, out_root: Path):
    out_root.mkdir(parents=True, exist_ok=True)
    return out_root / (in_path.stem + f"_x{SCALE}.png")  # 输出 PNG，带 scale 后缀

def load_image(path: Path):
    # 使用 Pillow 打开 DDS（若 pillow-dds 已安装通常可用）
    im = Image.open(path)
    # 如果是带 alpha，保留 alpha 通道
    # Convert to RGBA if has alpha, otherwise RGB
    if im.mode in ("RGBA", "LA") or ("transparency" in im.info):
        im = im.convert("RGBA")
    else:
        im = im.convert("RGB")
    return im

def process_dds(args, scale=4):
    paths = collect_inputs(args)
    if not paths:
        print("没有找到任何 .dds 文件可以处理。")
        return

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("使用设备:", device)

    model = RealESRGAN(device, scale=scale)
    weights_path = Path("G:\\webui\\models\\ESRGAN\\4x_ESRGAN_64nf_23nb-misc.pth")
    if not weights_path.exists():
        print(f"错误: 未发现模型权重: {weights_path}")
        print("请从 Real-ESRGAN 项目下载合适的权重并放到此路径，或修改脚本中的 weights_path。")
        return

    print("加载模型权重 ...（可能需要一些时间）")
    model.load_weights(str(weights_path))

    out_root = Path("upscaled_outputs")
    out_root.mkdir(parents=True, exist_ok=True)

    for p in paths:
        print("处理:", p)
        try:
            img = load_image(p)
        except Exception as e:
            print("  无法读取文件（可能不是标准 DDS 或缺少插件）:", e)
            continue

        try:
            sr = model.predict(img)
        except Exception as e:
            print("  超分过程出错:", e)
            continue

        out_path = out_root / (p.stem + f"_x{scale}.png")
        sr.save(out_path)
        print("  已保存:", out_path)

    print("全部完成。输出目录：", out_root)


if __name__ == "__main__":
    process_dds(["E:\RE4R Mods\\InGame\\Ada Dancer Clubni4ka\\Ada Dancer Clubni4ka\\natives\\stm\\_chainsaw\\character\\ch\\cha2\\cha200\\00\\"])  
