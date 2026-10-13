# RE4 RE Engine Mesh 修改工作区

本目录用于 RE Engine（生化危机 4 重制版）`.mesh` 二进制文件的解析、诊断与直接修改。
核心成果：**跨角色移植发型/部件后"游戏内位置正常但 Blender 错位"的绑定重锚定修复**。

## 目录结构

```
G:\mod-scripts\mesh_anchor_fix\
├── fix_mesh_anchor.py      ★ 可复用修复工具（CLI，详见下文）
├── analyze.py               解析脚本：dump 骨架/骨骼名/顶点位置/逐骨骼统计（诊断用）
├── compare.py               对比脚本：骨架矩阵 diff + 逐字节文件 diff（诊断用）
├── patch.py                 一次性补丁脚本（已由 fix_mesh_anchor.py 取代，留作参考）
└── meshes\                  工作副本（源文件均在 E:\RE4 Mods\，见下表）
```

## 环境

| 项 | 值 |
|---|---|
| Python | `F:\Program Files\Python\python.exe`（需 `pip install numpy`，已装） |
| RE-Mesh-Editor 插件（**只读引用，勿修改**） | `F:\Backup\BlenderPortable\scripts\addons\RE-Mesh-Editor`；Blender 插件在 `F:\Program Files\Blender\portable\scripts\addons\` |
| Blender | `F:\Program Files\Blender` |
| 导入 addon 时 | sys.path 指向插件目录，`from modules.mesh.file_re_mesh import REMesh` |

**插件路径配置**：每个脚本顶部都有全局变量 `ADDON_DIR`（默认指向 F:\Backup 下的插件），
改路径只需改脚本顶部的 `ADDON_DIR`，或设置环境变量 `RE_MESH_EDITOR_PATH`（优先级更高，
无效时自动回退到内置备用路径）。

## meshes\ 工作副本

| 文件 | 说明 |
|---|---|
| `ashley_hair_beta.221108797` | **待修对象**：Ashley beta 发型原版（cha100 空间，绑 Ashley 的 Head 位）。`_bak.221108797` 为原始副本 |
| `ashley_hair_beta_fixed.221108797` | ★ 修复输出：已重锚定到 Ada Head（用 `ada_head` 作参照生成） |
| `ada_head.221108797` | 参照：Ada 头部 mesh（231 骨架），提供正确锚定空间 |
| `ada_hair.221108797` | 参照：正常 Ada 发型（46 骨骼，`frontR01/frontL01` 命名体系） |
| `ada_body.221108797` | 参照：Ada 身体 mesh（231 骨架）。三者 Head 绑定一致（差 <3e-5），任选其一作 `--body` 均可 |
| `ashley_head.221108797` / `ashley_hair.221108797` | Ashley 头部/头发原版（对照用，`ashley_hair` 为 9MB 完整版） |
| `sherry_hair.221108797` | Sherry 发型（另一命名体系参照：`TopHairF/MidHairA` 等） |
| `fixed.mesh.221108797` | 早期修复输出（输入为 cha200 移植版 e7a536，已部署到游戏并验证） |

## 核心知识：RE Engine mesh 格式要点（本案例实测）

- **版本**：RE4 = 文件后缀 `221108797`（内部版本 110/220822879），`mesh_versions.py` 有映射表。
- **顶点**：float32，**SOA 分块布局**（非交错）。每个顶点元素 `(typing, stride, posStartOffset)`：
  typing `0=Position(stride12) 1=NorTan(8, int8×2组) 2/3=UV(4,float16) 4=Weight(16) 5=Color(4)`；
  元素块的绝对地址 = `meshBufferHeader.vertexBufferOffset + posStartOffset`；
  块大小 = stride × 顶点数，顶点数 = (下一元素偏移 − 本偏移) / stride。
  ⚠️ 不要用 `fileHeader.meshOffset` 当顶点基址——那是 MeshBufferHeader 自身的偏移。
- **矩阵存储是 row-vector 约定**（与 Blender 相反）：平移分量在 `reshape(4,4)` 后的**第 4 行 `M[3,:3]`**，列 3 为 0。插件导出时做 `.transposed()`（blender_re_mesh_export.py:386）。组合变换按 `p @ M` 的顺序。
- **蒙皮**：`v' = Σ w_i · v @ I_i @ Pose_i`；游戏用 mesh 自带的 inverse 矩阵 + 运行时同名骨骼的 pose。**同名骨骼即可跨角色绑定**（RE4R 角色共享标准头发骨骼命名：`Head/front01/topR01_chain_00/...`；Ashley 体系骨骼在 Ada 骨架上全部存在）。
- **mesh 文件骨架只是子集**：Ada 身体 mesh(231 骨)不含链骨骼，头发骨骼在运行时骨架里解析。
- **local 矩阵不关键**：移植品 local 与原版差异巨大仍正常工作；插件导出时 inverse 直接由 world 求逆（file_re_mesh.py:393），导入优先用存的 `reMeshWorldMatrix`（:379）。

## 本案例的根因与修复原理

**根因**：移植发型的顶点相对 Ashley 的 Head 绑定位（y≈1.5483）排布，Ada 的 Head 绑定位在
(0, 1.5547, 0.0172)——差约 2cm 平移 + 2.4° 旋转。游戏靠蒙皮补偿所以正常；
Blender rest 视图显示原始顶点（armature modifier 在 rest 下恒等），所以错位。

**修复**：刚体重锚定 `A_row = I_mesh(Head) @ W_body(Head)`（row 约定）：

```
顶点/法线/切线: v' = v @ A_row        world:  W' = W @ A_row
inverse:        I' = A_row⁻¹ @ I      AABB:   刚体变换后重算 min/max
不动:           local 矩阵、UV、权重、面、顶点色、名字表（权重数据块仅读取校验，不写入）
```

游戏不变性**逐骨骼严格成立**：`I'(A·v) = A⁻¹·I·A·v = I·v` → 蒙皮输出逐比特不变。
校验：抽样 500 顶点蒙皮误差 = 0；补丁后 Head 绑定与身体完全一致；`W@I = 单位阵`。

## fix_mesh_anchor.py 用法

```bash
"F:\Program Files\Python\python.exe" fix_mesh_anchor.py \
  --mesh <要修的mesh> --body <目标角色身体mesh> [--bone Head] [--out 路径] [--no-backup]
```

- 自动：计算锚定差 → 变换顶点/法线/world/inverse/AABB → 蒙皮不变性校验 → NaN 检查 → 原地覆盖（先自动 `_bak.221108797`）。
- 已一致时提示"无需修复"直接退出；任何校验失败中止且不写文件。
- 已实测：对原始备份重跑，输出与已部署文件 SHA256 一致（`0ed63987...`）。
- 适用于：**游戏内位置正常、Blender 内错位**的跨角色移植 mesh。若游戏内也错位，是别的问题（骨骼名不匹配/权重丢失），此脚本不适用。

### 交互模式（无参数双击运行）

1. ① 输入待修复 mesh 路径（支持拖放）
2. ② 从 `meshes\` 列表选择目标身体 mesh（上下键/数字键/拖放）
3. ③ 锚定骨骼名 → 跳过，默认 `Head`
4. ④ 输出方式 → 跳过，默认原地覆盖
5. ⑤ 备份 → 跳过，默认生成 `原名_bak.221108797`

第②步后直接进入处理，无需任何额外输入。

## 踩过的坑（重要）

1. `meshOffset` ≠ 顶点缓冲基址，必须用 `meshBufferHeader.vertexBufferOffset`。
2. 矩阵平移在**第 4 行**，按列向量方式组合 world/inverse 会写坏其它 44 根骨骼的旋转。
3. 插件解析代码 `analyze.py` 初版按"交错顶点"读导致 NaN——RE4 是 SOA 分块。
4. AABB 块：`aabbOffset` 处 `count(u64) + offset(u64)` + count×32 字节（min/max 各 Vec4）；本例 count=23 < boneCount=45 属正常。
5. 插件 `REMesh.read` 读矩阵是**连续读**（不 seek 到存的 offset 字段），但文件里存的 `boneWorldMatrixOffset/boneInverseMatrixOffset` 是可靠的绝对偏移（已断言验证）。
