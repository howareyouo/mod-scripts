# -*- coding: utf-8 -*-
"""Patch broken.mesh (Ashley beta hair port on cha200):
re-anchor the whole bind frame to Ada's Head bind via rigid transform A.

Game-invariance proof (per bone i, per vertex v):
  invBindNew_i (A v) = (I_i A^-1)(A v) = I_i v = invBindOld_i v   (exact)
so skinned output sum_i w_i pose_i invBindNew_i v_new == original, bit-for-bit intent.

Transformed: positions, normals+tangents, world mats, inverse mats, bone AABBs.
Untouched:   local mats, weights, faces, UVs, colors, all other bytes.
"""
import sys, os
import numpy as np

# RE-Mesh-Editor 插件路径 (只读)：修改此处或设置环境变量 RE_MESH_EDITOR_PATH
ADDON_DIR = os.environ.get('RE_MESH_EDITOR_PATH',
                           'F:/Backup/BlenderPortable/scripts/addons/RE-Mesh-Editor')
sys.path.insert(0, ADDON_DIR)
from modules.mesh.file_re_mesh import REMesh, BoneAABBGroup
from modules.mesh.mesh_versions import VERSION_RE4
from modules.gen_functions import openFileRead

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meshes')
BROKEN = os.path.join(D, 'ashley_hair_beta.221108797')
BODY = os.path.join(D, 'ada_head.221108797')
OUT = os.path.join(D, 'fixed.mesh')

def load(path):
    with openFileRead(path) as f:
        m = REMesh(); m.read(f, VERSION_RE4)
    sk = m.skeletonHeader
    names = [m.rawNameList[m.boneNameRemapList[i]] for i in range(sk.boneCount)]
    return m, names

# ---------- 1. compute re-anchoring map A_row (file convention is ROW-vector: p' = p @ M) ----------
# p_ada_world = p @ I_ashleyHead @ W_adaHead  ->  A_row = I_ash @ W_ada
mb, nb = load(BODY)
md, nd = load(BROKEN)
Wb = np.array([np.asarray(x.matrix, dtype=np.float32).reshape(4, 4) for x in mb.skeletonHeader.worldMatList])
Wd = np.array([np.asarray(x.matrix, dtype=np.float32).reshape(4, 4) for x in md.skeletonHeader.worldMatList])
Id = np.array([np.asarray(x.matrix, dtype=np.float32).reshape(4, 4) for x in md.skeletonHeader.inverseMatList])
Ld = np.array([np.asarray(x.matrix, dtype=np.float32).reshape(4, 4) for x in md.skeletonHeader.localMatList])
A_row = Id[nd.index('Head')] @ Wb[nb.index('Head')]
Rr, tr = A_row[:3, :3], A_row[3, :3]
print(f"A_row translation: {tr.round(5)}, rotation max|I-R|: {np.abs(np.eye(3) - Rr).max():.4f}")
assert np.abs(Rr @ Rr.T - np.eye(3)).max() < 1e-4, "A rotation not orthonormal"
A_row_inv = np.eye(4); A_row_inv[:3, :3] = Rr.T; A_row_inv[3, :3] = -tr @ Rr.T
# column-view used for vertex/normal application (p @ A_row == A_col @ p)
A_col = A_row.T
R, t = A_col[:3, :3], A_col[:3, 3]
# invariance sanity for game: A_row @ I_new == I_old per bone; I_new = A_row_inv @ I_old
# Head check: W_new_head == W_ada_head, I_new_head == I_ada_head
_head_i = nd.index('Head')
assert np.abs((Wd[_head_i] @ A_row) - Wb[nb.index('Head')]).max() < 1e-4
assert np.abs((A_row_inv @ Id[_head_i]) - np.array(
    [np.asarray(x.matrix, dtype=np.float32).reshape(4, 4) for x in mb.skeletonHeader.inverseMatList][nb.index('Head')])).max() < 1e-4
print("Head re-anchor check: W/I now equal Ada body's Head bind")

# ---------- 2. load raw bytes & locate blocks ----------
raw = bytearray(open(BROKEN, 'rb').read())
fh = md.fileHeader
mmb = md.meshBufferHeader
vbo = mmb.vertexBufferOffset  # absolute base of vertex buffer (meshOffset is the header's own offset!)
elems = [(int(e['typing']), int(e['stride']), int(e['posStartOffset'])) for e in mmb.vertexElementList]
pos_el = next(e for e in elems if e[0] == 0)
nor_el = next(e for e in elems if e[1 - 1] == 1)  # typing 1
pos_abs = vbo + pos_el[2]
n_verts = None
for i, (ty, st, off) in enumerate(elems):
    end = elems[i + 1][2] if i + 1 < len(elems) else len(mmb.vertexBuffer)
    if ty == 0:
        n_verts = (end - off) // st
print(f"verts={n_verts}, pos block abs={hex(pos_abs)}, nor block abs={hex(vbo + nor_el[2])}")

# skeleton matrix blocks: use the file's OWN stored absolute offsets (verified below)
sk = md.skeletonHeader
bc, rc = sk.boneCount, sk.remapCount
world_abs = sk.boneWorldMatrixOffset
inverse_abs = sk.boneInverseMatrixOffset
# verify against parsed values
chk = np.frombuffer(bytes(raw[world_abs:world_abs + 64]), dtype='<16f').reshape(4, 4)
assert np.abs(chk - Wd[0]).max() < 1e-6, "world matrix block offset mismatch"
chk = np.frombuffer(bytes(raw[inverse_abs:inverse_abs + 64]), dtype='<16f').reshape(4, 4)
assert np.abs(chk - Id[0]).max() < 1e-6, "inverse matrix block offset mismatch"
print(f"world mats @ {hex(world_abs)}, inverse mats @ {hex(inverse_abs)}  (verified)")
print("NOTE: local matrices left untouched (not skinning-critical; port evidence: locals differ wildly from source yet works)")

# aabb block
with openFileRead(BROKEN) as f:
    f.seek(fh.aabbOffset)
    aabb = BoneAABBGroup(); aabb.read(f)
print(f"aabb count={aabb.count} @ {hex(fh.aabbOffset)}")
aabb_data_abs = fh.aabbOffset + 16

# snapshot before
pos_before = np.frombuffer(bytes(raw[pos_abs:pos_abs + n_verts * 12]), dtype='<f4').reshape(n_verts, 3).copy()

# ---------- 3. patch positions ----------
P = pos_before @ R.T + t  # (A @ [p,1])[:3]
raw[pos_abs:pos_abs + n_verts * 12] = np.asarray(P, dtype='<f4').tobytes()

# ---------- 4. patch normals + tangents ----------
nor_abs = vbo + nor_el[2]
NB = np.frombuffer(bytes(raw[nor_abs:nor_abs + n_verts * 8]), dtype=np.int8).reshape(n_verts, 2, 4).copy()
for slot in (0, 1):  # 0=normals, 1=tangents
    v = NB[:, slot, :3].astype(np.float32) / 127.0
    v = v @ R.T
    NB[:, slot, :3] = np.clip(np.round(v * 127.0), -127, 127).astype(np.int8)
raw[nor_abs:nor_abs + n_verts * 8] = NB.tobytes()

# ---------- 5. patch world & inverse matrices (row-vector convention) ----------
# W_new = W_old @ A_row ; I_new = A_row_inv @ I_old ; locals untouched
W_all = np.frombuffer(bytes(raw[world_abs:world_abs + bc * 64]), dtype='<f4').reshape(bc, 4, 4).copy()
raw[world_abs:world_abs + bc * 64] = (W_all @ A_row).astype(np.float32).tobytes()
I_all = np.frombuffer(bytes(raw[inverse_abs:inverse_abs + bc * 64]), dtype='<f4').reshape(bc, 4, 4).copy()
raw[inverse_abs:inverse_abs + bc * 64] = (A_row_inv @ I_all).astype(np.float32).tobytes()

# ---------- 6. patch bone AABBs ----------
boxes = np.empty((aabb.count, 2, 4), dtype=np.float32)
for i, e in enumerate(aabb.bboxList):
    boxes[i, 0] = [e.min.x, e.min.y, e.min.z, e.min.w]
    boxes[i, 1] = [e.max.x, e.max.y, e.max.z, e.max.w]
# rotated AABB: for each output axis k, new_min[k] = t[k] + sum_j min(R[k,j]*min_j, R[k,j]*max_j)
lo = boxes[:, 0, :3]  # (n,3)
hi = boxes[:, 1, :3]
prod_lo = R[None, :, :] * lo[:, None, :]      # (n, 3out, 3in) R[k,j]*lo[j]
prod_hi = R[None, :, :] * hi[:, None, :]
mins = np.minimum(prod_lo, prod_hi).sum(axis=2) + t[None, :]
maxs = np.maximum(prod_lo, prod_hi).sum(axis=2) + t[None, :]
out = np.empty((aabb.count, 2, 4), dtype=np.float32)
out[:, 0, :3] = mins; out[:, 0, 3] = boxes[:, 0, 3]
out[:, 1, :3] = maxs; out[:, 1, 3] = boxes[:, 1, 3]
raw[aabb_data_abs:aabb_data_abs + aabb.count * 32] = out.tobytes()

# ---------- 7. verify game-invariance ----------
I_after = np.frombuffer(bytes(raw[inverse_abs:inverse_abs + bc * 64]), dtype='<f4').reshape(bc, 4, 4)
P_after = np.frombuffer(bytes(raw[pos_abs:pos_abs + n_verts * 12]), dtype='<f4').reshape(n_verts, 3)
wbuf = np.frombuffer(bytes(mmb.vertexBuffer), dtype=np.uint8)[:0]  # placeholder
# weights from original parse (weights untouched)
wt_el = next(e for e in elems if e[0] == 4)
wraw = np.frombuffer(bytes(mmb.vertexBuffer[wt_el[2]:wt_el[2] + 16 * n_verts]), dtype=np.uint8).reshape(n_verts, 16)
idx = wraw[:, :4].astype(np.int32); wts = wraw[:, 4:8].astype(np.float32) / 255.0
rng = np.random.default_rng(0)
sample = rng.choice(n_verts, 500, replace=False)
err = 0.0
for vi in sample:
    vh = np.append(pos_before[vi], 1.0); vh2 = np.append(P_after[vi], 1.0)
    s1 = np.zeros(4); s2 = np.zeros(4)
    for k in range(4):
        if wts[vi, k] > 0 and idx[vi, k] < bc:
            s1 += wts[vi, k] * (vh @ Id[idx[vi, k]])       # row convention: p @ I
            s2 += wts[vi, k] * (vh2 @ I_after[idx[vi, k]])
    err = max(err, np.abs(s1 - s2).max())
print(f"game-invariance check (rest-pose skinned pos, 500 samples): max err = {err:.2e}")

print("new pos bbox:", P_after.min(axis=0).round(3), P_after.max(axis=0).round(3))
print("ada head-mesh region ~ y1.47-1.69 z-0.06-0.12 (from earlier measurement)")

open(OUT, 'wb').write(bytes(raw))
print(f"written {OUT} ({len(raw)} bytes)")
