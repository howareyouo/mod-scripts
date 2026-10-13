# -*- coding: utf-8 -*-
r"""
fix_mesh_anchor.py — RE Engine mesh 跨角色移植绑定重锚定工具

用途：把一个角色 A 的发型/部件 mesh 移植到角色 B 后，Blender 里显示错位
（游戏内正常）的问题一次性修好：将 mesh 的绑定坐标系刚体重锚定到
角色 B 身体 mesh 的指定骨骼（默认 Head）。

原理：
  A = I_mesh(anchor) @ W_body(anchor)   (row-vector 约定, p' = p @ M)
  顶点/法线/切线 v' = v @ A
  world:  W' = W @ A        inverse: I' = A^-1 @ I
  骨骼 AABB 随 A 刚体变换；UV/权重/面/顶点色/local 矩阵不动。
  游戏不变性（逐骨骼严格成立）：I'(A v) = I v  → 蒙皮输出逐比特不变。

用法：
  python fix_mesh_anchor.py --mesh <要修的.mesh.xxx> --body <参照角色身体.mesh.xxx>
                            [--bone Head] [--out <输出路径>] [--no-backup]

  --mesh  待修复 mesh（移植品），原地覆盖（除非 --out）
  --body  目标角色的身体/头部 mesh（其骨架含锚定骨骼，提供正确的绑定空间）
  --bone  锚定骨骼名，默认 Head
  --out   输出到别处（默认原地覆盖并自动生成 .bak 备份）

依赖：numpy；同目录或 --addon 下需有 RE-Mesh-Editor 的 modules/
      交互 UI 组件见同目录 tui.py
"""

import argparse
import os
import shutil
import sys

import numpy as np

from tui import hl, clean_path, ask_path, select_body_mesh

# ---------- RE Mesh Editor 模块定位（只读，不修改插件） ----------
# 修改此处（或设置环境变量 RE_MESH_EDITOR_PATH）即可切换插件路径
ADDON_DIR = os.environ.get('RE_MESH_EDITOR_PATH',
                           'F:/Backup/BlenderPortable/scripts/addons/RE-Mesh-Editor')


def _find_addon(explicit=None):
    cands = []
    if explicit:
        cands.append(explicit)
    cands.append(ADDON_DIR)
    cands.append('F:/Program Files/Blender/portable/scripts/addons/RE-Mesh-Editor')
    for c in cands:
        if os.path.isdir(os.path.join(c, 'modules', 'mesh')):
            return c
    raise SystemExit("找不到 RE-Mesh-Editor 的 modules/，请用 --addon 指定插件目录")


def load_mesh(path, addon):
    sys.path.insert(0, addon)
    from modules.mesh.file_re_mesh import REMesh
    from modules.mesh.mesh_versions import VERSION_RE4
    from modules.gen_functions import openFileRead
    with openFileRead(path) as f:
        m = REMesh()
        m.read(f, VERSION_RE4)
    if m.skeletonHeader is None or m.meshBufferHeader is None:
        raise SystemExit(f"{path}: 缺少骨架或网格缓冲，不是可处理的 mesh 文件")
    sk = m.skeletonHeader
    names = [m.rawNameList[m.boneNameRemapList[i]] for i in range(sk.boneCount)]
    W = np.array([np.asarray(x.matrix, dtype=np.float32).reshape(4, 4) for x in sk.worldMatList])
    I = np.array([np.asarray(x.matrix, dtype=np.float32).reshape(4, 4) for x in sk.inverseMatList])
    return m, names, W, I


def run(args):
    addon = _find_addon(args.addon)
    out_path = args.out or args.mesh

    print(f"\n[1/6] 加载 mesh: {args.mesh}")
    md, nd, Wd, Id = load_mesh(args.mesh, addon)
    print(f"[2/6] 加载参照身体: {args.body}")
    mb, nb, Wb, _ = load_mesh(args.body, addon)

    if args.bone not in nd:
        raise SystemExit(f"mesh 骨架中不存在骨骼 '{args.bone}'（可用骨骼前几个: {nd[:8]}...）")
    if args.bone not in nb:
        raise SystemExit(f"参照身体骨架中不存在骨骼 '{args.bone}'")

    # A_row = I_mesh(bone) @ W_body(bone)
    A_row = Id[nd.index(args.bone)] @ Wb[nb.index(args.bone)]
    Rr, tr = A_row[:3, :3], A_row[3, :3]
    orth = np.abs(Rr @ Rr.T - np.eye(3)).max()
    if orth > 1e-3:
        raise SystemExit(f"锚定变换旋转分量不正交（{orth:.4f}），骨骼数据异常，中止")
    A_row_inv = np.eye(4)
    A_row_inv[:3, :3] = Rr.T
    A_row_inv[3, :3] = -tr @ Rr.T
    A_col = A_row.T
    R, t = A_col[:3, :3], A_col[:3, 3]
    shift = np.linalg.norm(t)
    print(f"    平移量 {np.linalg.norm(t)*100:.2f} cm, 旋转 {np.degrees(np.arccos(np.clip((np.trace(R)-1)/2,-1,1))):.2f}°")
    if shift < 1e-4 and orth < 1e-4:
        print("    两个绑定坐标系已一致，无需修复。")
        return

    # Head 校验：补丁后 mesh 锚定骨骼 == 参照身体锚定骨骼
    head_check = Wd[nd.index(args.bone)] @ A_row
    assert np.abs(head_check - Wb[nb.index(args.bone)]).max() < 1e-3, "锚定校验失败"

    print("[3/6] 定位数据块")
    raw = bytearray(open(args.mesh, 'rb').read())
    if len(raw) != md.fileHeader.fileSize:
        raise SystemExit("文件大小与 header 不符，文件可能已损坏，中止")
    fh, mmb = md.fileHeader, md.meshBufferHeader
    vbo = mmb.vertexBufferOffset  # 顶点缓冲绝对基址
    sk = md.skeletonHeader
    bc = sk.boneCount
    elems = [(int(e['typing']), int(e['stride']), int(e['posStartOffset'])) for e in mmb.vertexElementList]

    def block(typing):
        el = next((e for e in elems if e[0] == typing), None)
        if el is None:
            return None
        idx = elems.index(el)
        end = elems[idx + 1][2] if idx + 1 < len(elems) else len(mmb.vertexBuffer)
        return vbo + el[2], el[1], (end - el[2]) // el[1]

    pos_blk = block(0)
    nor_blk = block(1)
    wt_blk = block(4)
    if pos_blk is None:
        raise SystemExit("mesh 无 Position 顶点元素")
    pos_abs, pos_stride, n_verts = pos_blk
    world_abs = sk.boneWorldMatrixOffset
    inverse_abs = sk.boneInverseMatrixOffset
    # 偏移验证
    assert np.abs(np.frombuffer(bytes(raw[world_abs:world_abs + 64]), '<16f').reshape(4, 4) - Wd[0]).max() < 1e-6
    assert np.abs(np.frombuffer(bytes(raw[inverse_abs:inverse_abs + 64]), '<16f').reshape(4, 4) - Id[0]).max() < 1e-6
    print(f"    顶点 {n_verts}, pos@{hex(pos_abs)}, world@{hex(world_abs)}, inverse@{hex(inverse_abs)}")

    print("[4/6] 变换顶点/法线/矩阵/AABB")
    pos_before = np.frombuffer(bytes(raw[pos_abs:pos_abs + n_verts * pos_stride]), '<f4').reshape(n_verts, 3).copy()
    P = pos_before @ R.T + t
    raw[pos_abs:pos_abs + n_verts * pos_stride] = np.asarray(P, dtype='<f4').tobytes()

    if nor_blk is not None:
        nor_abs, nor_stride, n_nor = nor_blk
        NB = np.frombuffer(bytes(raw[nor_abs:nor_abs + n_nor * nor_stride]), np.int8).reshape(n_nor, 2, 4).copy()
        for slot in (0, 1):  # 0=法线 1=切线
            v = NB[:, slot, :3].astype(np.float32) / 127.0
            NB[:, slot, :3] = np.clip(np.round((v @ R.T) * 127.0), -127, 127).astype(np.int8)
        raw[nor_abs:nor_abs + n_nor * nor_stride] = NB.tobytes()

    W_all = np.frombuffer(bytes(raw[world_abs:world_abs + bc * 64]), '<f4').reshape(bc, 4, 4)
    raw[world_abs:world_abs + bc * 64] = (W_all @ A_row).astype(np.float32).tobytes()
    I_all = np.frombuffer(bytes(raw[inverse_abs:inverse_abs + bc * 64]), '<f4').reshape(bc, 4, 4)
    raw[inverse_abs:inverse_abs + bc * 64] = (A_row_inv @ I_all).astype(np.float32).tobytes()

    if fh.aabbOffset:
        from modules.mesh.file_re_mesh import BoneAABBGroup
        with open(os.path.join(args.mesh), 'rb') as f:
            f.seek(fh.aabbOffset)
            aabb = BoneAABBGroup()
            aabb.read(f)
        boxes = np.empty((aabb.count, 2, 4), np.float32)
        for i, e in enumerate(aabb.bboxList):
            boxes[i, 0] = [e.min.x, e.min.y, e.min.z, e.min.w]
            boxes[i, 1] = [e.max.x, e.max.y, e.max.z, e.max.w]
        prod_lo = R[None] * boxes[:, 0:1, :3]
        prod_hi = R[None] * boxes[:, 1:2, :3]
        mins = np.minimum(prod_lo, prod_hi).sum(2) + t
        maxs = np.maximum(prod_lo, prod_hi).sum(2) + t
        out = np.empty((aabb.count, 2, 4), np.float32)
        out[:, 0, :3], out[:, 0, 3] = mins, boxes[:, 0, 3]
        out[:, 1, :3], out[:, 1, 3] = maxs, boxes[:, 1, 3]
        aabb_abs = fh.aabbOffset + 16
        raw[aabb_abs:aabb_abs + aabb.count * 32] = out.tobytes()

    print("[5/6] 校验（蒙皮不变性抽样）")
    I_after = np.frombuffer(bytes(raw[inverse_abs:inverse_abs + bc * 64]), '<f4').reshape(bc, 4, 4)
    P_after = np.frombuffer(bytes(raw[pos_abs:pos_abs + n_verts * pos_stride]), '<f4').reshape(n_verts, 3)
    rng = np.random.default_rng(0)
    sample = rng.choice(n_verts, min(500, n_verts), replace=False)
    if wt_blk is not None:
        wt_abs, wt_stride, _ = wt_blk
        wb = np.frombuffer(bytes(mmb.vertexBuffer[wt_blk[2]:wt_blk[2] + wt_stride * n_verts]),
                           np.uint8).reshape(n_verts, wt_stride)
        idx4 = wb[:, :4].astype(np.int32)
        w4 = wb[:, 4:8].astype(np.float32) / 255.0
        err = 0.0
        for vi in sample:
            h1 = np.append(pos_before[vi], 1.0)
            h2 = np.append(P_after[vi], 1.0)
            s1 = np.zeros(4)
            s2 = np.zeros(4)
            for k in range(4):
                if w4[vi, k] > 0 and idx4[vi, k] < bc:
                    s1 += w4[vi, k] * (h1 @ Id[idx4[vi, k]])
                    s2 += w4[vi, k] * (h2 @ I_after[idx4[vi, k]])
            err = max(err, np.abs(s1 - s2).max())
        if err > 1e-3:
            raise SystemExit(f"蒙皮不变性校验失败（误差 {err}），已中止，不写出文件")
        print(f"    蒙皮不变性: 最大误差 {err:.2e} (要求 < 1e-3)  ✓")
    if not np.isfinite(P_after).all():
        raise SystemExit("顶点出现 NaN，中止")
    print(f"    新顶点范围: {P_after.min(0).round(3)} ~ {P_after.max(0).round(3)}")

    print("[6/6] 写出")
    if not args.out and not args.no_backup:
        root, ext = os.path.splitext(args.mesh)
        bak = root + '_bak' + ext
        if not os.path.exists(bak):
            shutil.copy2(args.mesh, bak)
            print(f"    备份: {bak}")
        else:
            print(f"    备份已存在，保留: {bak}")
    with open(out_path, 'wb') as f:
        f.write(bytes(raw))
    print(f"完成: {out_path} ({len(raw)} 字节)")


def main():
    ap = argparse.ArgumentParser(
        description='RE Engine mesh 绑定重锚定修复（不带参数运行 = 交互模式）')
    ap.add_argument('--mesh', default=None, help='待修复的 mesh 文件')
    ap.add_argument('--body', default=None, help='参照角色的身体 mesh 文件')
    ap.add_argument('--bone', default=None, help='锚定骨骼名（默认 Head）')
    ap.add_argument('--out', default=None, help='输出路径（默认原地覆盖）')
    ap.add_argument('--no-backup', action='store_true', help='不生成 .bak 备份')
    ap.add_argument('--addon', default=None, help='RE-Mesh-Editor 插件目录')
    args, unknown = ap.parse_known_args()

    interactive = args.mesh is None  # 双击/直接运行 = 交互模式
    if len(sys.argv) == 1:
        print("=" * 62)
        print("  RE Engine mesh 移植错位修复工具 (fix_mesh_anchor)")
        print("  修复: 游戏内位置正常、Blender 里错位的跨角色移植 mesh")
        print("=" * 62)

    # 拖拽 mesh 到脚本图标上时, sys.argv[1] 就是文件路径
    if args.mesh is None and len(sys.argv) == 2 and os.path.isfile(sys.argv[1]):
        args.mesh = sys.argv[1]

    if args.mesh is None:
        args.mesh = ask_path(f"① 输入「{hl('待修复的 mesh')}」路径 (支持拖放): ")
    if args.body is None:
        meshes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meshes')
        args.body = select_body_mesh(meshes_dir)
    if args.bone is None:
        args.bone = 'Head'
    if interactive and args.out is None:
        args.out = None  # 默认原地覆盖
    if interactive and not args.no_backup:
        args.no_backup = False  # 默认生成备份

    try:
        run(args)
    except SystemExit as e:
        print(f"\n[中止] {e}")
    except Exception as e:
        print(f"\n[错误] {type(e).__name__}: {e}")
        if not interactive:
            raise
    finally:
        if interactive:
            input("\n按回车键退出...")


if __name__ == '__main__':
    main()
