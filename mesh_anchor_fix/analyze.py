# -*- coding: utf-8 -*-
"""Analyze RE4 mesh files: skeleton, bone names, vertex positions (SOA layout)."""
import sys, os
import numpy as np

# RE-Mesh-Editor 插件路径 (只读)：修改此处或设置环境变量 RE_MESH_EDITOR_PATH
ADDON_DIR = os.environ.get('RE_MESH_EDITOR_PATH',
                           'F:/Backup/BlenderPortable/scripts/addons/RE-Mesh-Editor')
sys.path.insert(0, ADDON_DIR)
from modules.mesh.file_re_mesh import REMesh
from modules.mesh.mesh_versions import VERSION_RE4
from modules.gen_functions import openFileRead

TYPE_NAMES = ["Position", "NorTan", "UV", "UV2", "Weight", "Color", "SF6", "ExtraWeight", "Face"]

def analyze(path):
    print(f"===== {os.path.basename(path)} =====")
    with openFileRead(path) as f:
        m = REMesh()
        m.read(f, VERSION_RE4)
    fh = m.fileHeader
    print(f"fileSize={fh.fileSize} nameCount={fh.nameCount}")

    sk = m.skeletonHeader
    names = []
    if sk is None:
        print("NO SKELETON")
    else:
        print(f"boneCount={sk.boneCount} remapCount={sk.remapCount}")
        for i in range(sk.boneCount):
            try:
                names.append(m.rawNameList[m.boneNameRemapList[i]])
            except Exception as e:
                names.append(f"<err {e}>")
        if sk.worldMatList:
            w = np.array([np.asarray(mw.matrix, dtype=np.float32).reshape(4, 4) for mw in sk.worldMatList])
            l = np.array([np.asarray(ml.matrix, dtype=np.float32).reshape(4, 4) for ml in sk.localMatList])
            print("bone | world translation (x,y,z) | local translation")
            for i in range(min(sk.boneCount, 50)):
                wt_, lt = w[i][:3, 3], l[i][:3, 3]
                print(f"  [{i:2d}] {names[i][:34]:34s} W=({wt_[0]:8.3f},{wt_[1]:8.3f},{wt_[2]:8.3f}) "
                      f"L=({lt[0]:7.3f},{lt[1]:7.3f},{lt[2]:7.3f})")

    mb = m.meshBufferHeader
    if mb is None:
        print("NO MESH BUFFER\n")
        return None
    print(f"vertexBufferSize={mb.vertexBufferSize} faceBufferSize={mb.faceBufferSize} elems={mb.vertexElementCount}")
    for el in mb.vertexElementList:
        print(f"  elem {TYPE_NAMES[int(el['typing'])]:10s} stride={int(el['stride']):3d} offset={int(el['posStartOffset'])}")

    # SOA: each element block is [offset, next offset) sized stride*n
    elems = [(int(el['typing']), int(el['stride']), int(el['posStartOffset'])) for el in mb.vertexElementList]
    n = None
    pos = None
    for i, (t, stride, off) in enumerate(elems):
        end = elems[i + 1][2] if i + 1 < len(elems) else len(mb.vertexBuffer)
        cnt = (end - off) // stride
        if t == 0:
            n = cnt
            raw = np.frombuffer(bytes(mb.vertexBuffer[off:off + stride * cnt]), dtype='<f4').reshape(cnt, 3)
            pos = raw
            print(f"vertexCount={n}")
            print(f"pos min={raw.min(axis=0).round(2)} max={raw.max(axis=0).round(2)} center={raw.mean(axis=0).round(2)}")
        if t == 4 and sk is not None and pos is not None:
            wb = np.frombuffer(bytes(mb.vertexBuffer[off:off + stride * cnt]), dtype=np.uint8).reshape(cnt, stride)
            idx = wb[:, :4].astype(np.int32)
            wt = wb[:, 4:8].astype(np.float32) / 255.0
            dom = np.argmax(wt, axis=1)
            dom_bone = idx[np.arange(cnt), dom]
            valid = dom_bone < sk.boneCount
            rows = []
            for b in np.unique(dom_bone[valid]):
                mask = valid & (dom_bone == b)
                c = pos[mask].mean(axis=0)
                rows.append((int(b), names[int(b)], int(mask.sum()), c))
            rows.sort(key=lambda r: -r[2])
            print("per-dominant-bone stats (top 10):")
            for b, nm, c2, c in rows[:10]:
                print(f"  bone[{b:2d}] {nm[:34]:34s} n={c2:6d} centroid=({c[0]:8.2f},{c[1]:8.2f},{c[2]:8.2f})")
    print()
    return m

def _ask(msg, default):
    """提示输入路径, 回车用默认值；无输入可用(EOF)时也用默认值"""
    try:
        s = input(f"{msg} (回车={os.path.basename(default) or '跳过'}): ").strip().strip('"').strip("'")
    except EOFError:
        return default
    return s if s else default

if __name__ == '__main__':
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meshes')
    # 命令行参数优先: analyze.py <file1> [file2 ...]
    files = sys.argv[1:]
    if not files and len(sys.argv) == 1:
        print("RE Engine mesh 分析工具 (回车 = 使用默认值)")
        files = [
            _ask("① 发型A", os.path.join(d, 'ada_hair.221108797')),
            _ask("② 发型B", os.path.join(d, 'ashley_hair_beta.221108797')),
            _ask("③ 其它(可留空跳过)", ''),
        ]
        files = [f for f in files if f]
    if not files:
        files = [os.path.join(d, 'ada_hair.221108797'),
                 os.path.join(d, 'ashley_hair_beta.221108797'),
                 os.path.join(d, 'ashley_hair.221108797')]
    for f in files:
        analyze(f if os.path.isabs(f) else os.path.join(d, f))
