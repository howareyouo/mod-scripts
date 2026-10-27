# -*- coding: utf-8 -*-
"""Compare skeleton matrices across files + byte-diff broken vs source."""
import sys, os
import numpy as np

# RE-Mesh-Editor 插件路径 (只读)：修改此处或设置环境变量 RE_MESH_EDITOR_PATH
ADDON_DIR = os.environ.get('RE_MESH_EDITOR_PATH',
                           'F:/Backup/BlenderPortable/scripts/addons/RE-Mesh-Editor')
sys.path.insert(0, ADDON_DIR)
from modules.mesh.file_re_mesh import REMesh
from modules.mesh.mesh_versions import VERSION_RE4
from modules.gen_functions import openFileRead

def load(path):
    with openFileRead(path) as f:
        m = REMesh()
        m.read(f, VERSION_RE4)
    sk = m.skeletonHeader
    names = [m.rawNameList[m.boneNameRemapList[i]] for i in range(sk.boneCount)]
    mats = {}
    for key, lst in (('world', sk.worldMatList), ('inverse', sk.inverseMatList), ('local', sk.localMatList)):
        mats[key] = np.array([np.asarray(mm.matrix, dtype=np.float32).reshape(4, 4) for mm in lst])
    return m, names, mats

def detect_trans_layout(M, label):
    """Print row3 vs col3 to find where translation lives."""
    print(f"[{label}] row3 (M[3,:3]) sample: {M[1][3,:3].round(3)}  col3 (M[:3,3]) sample: {M[1][:3,3].round(3)}")

def _ask(msg, default):
    """提示输入路径, 回车用默认值；无输入可用(EOF)时也用默认值"""
    try:
        s = input(f"{msg} (回车={os.path.basename(default)}): ").strip().strip('"').strip("'")
    except EOFError:
        return default
    return s if s else default

if __name__ == '__main__':
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meshes')
    REF_DEF = os.path.join(d, 'ada_hair.221108797')
    BRK_DEF = os.path.join(d, 'ashley_hair_beta.221108797')
    SRC_DEF = os.path.join(d, 'ashley_hair.221108797')
    # 命令行参数优先: compare.py <参照> <待比> <源>
    if len(sys.argv) >= 4:
        ref_p, brk_p, src_p = sys.argv[1:4]
    else:
        print("RE Engine mesh 对比工具 (回车 = 使用默认值)")
        ref_p = _ask("① 参照(正常)", REF_DEF)
        brk_p = _ask("② 待比(错位)", BRK_DEF)
        src_p = _ask("③ 源(原版)", SRC_DEF)
    p = lambda f: f if os.path.isabs(f) else os.path.join(d, f)

    mref, nref, Mref = load(p(ref_p))
    mbrk, nbrk, Mbrk = load(p(brk_p))
    msrc, nsrc, Msrc = load(p(src_p))

    detect_trans_layout(Mref['world'], 'ref world')
    detect_trans_layout(Mref['inverse'], 'ref inverse')

    print("\n--- same-name bone matrix comparison (world), broken vs reference ---")
    common = [n for n in nbrk if n in nref]
    print(f"common bone names ({len(common)}): {common}")
    ib_ref = {n: i for i, n in enumerate(nref)}
    worst = []
    for n in common:
        i_b, i_r = nbrk.index(n), ib_ref[n]
        dW = np.abs(Mbrk['world'][i_b] - Mref['world'][i_r]).max()
        worst.append((dW, n, i_b, i_r))
    worst.sort(reverse=True)
    for dW, n, i_b, i_r in worst[:15]:
        tb, tr = Mbrk['world'][i_b][3, :3], Mref['world'][i_r][3, :3]
        print(f"  {n[:30]:30s} maxDiff={dW:8.4f}  brk_t=({tb[0]:7.3f},{tb[1]:7.3f},{tb[2]:7.3f}) ref_t=({tr[0]:7.3f},{tr[1]:7.3f},{tr[2]:7.3f})")

    print("\n--- broken vs source: skeleton identical? ---")
    if nbrk == nsrc:
        print("bone names identical")
        for key in ('world', 'inverse', 'local'):
            diff = np.abs(Mbrk[key] - Msrc[key]).max()
            print(f"  {key} max diff: {diff}")
    else:
        print("bone names DIFFER")

    print("\n--- 待比 vs 源: byte diff regions ---")
    b1 = open(p(brk_p), 'rb').read()
    b2 = open(p(src_p), 'rb').read()
    print(f"sizes: {len(b1)} vs {len(b2)}")
    if len(b1) == len(b2):
        diff_idx = np.where(np.frombuffer(b1, dtype=np.uint8) != np.frombuffer(b2, dtype=np.uint8))[0]
        print(f"differing bytes: {len(diff_idx)}")
        if len(diff_idx):
            # group into ranges
            groups = []
            start = prev = int(diff_idx[0])
            for i in diff_idx[1:]:
                i = int(i)
                if i - prev > 32:
                    groups.append((start, prev))
                    start = i
                prev = i
            groups.append((start, prev))
            print(f"{len(groups)} diff regions (first 20):")
            for s, e in groups[:20]:
                print(f"  0x{s:06x}-0x{e:06x} ({e - s + 1} bytes)")
