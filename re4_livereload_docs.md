# re4_livereload.lua — RE4 角色 mod 热重载完整复刻指南

> **本文件目标**：让任何不熟悉本项目的 AI / 工程师读一遍文档就能从零
> 复现"装/换 mod 后不重启游戏即让玩家角色换装"的能力，包括 C++ 插件
> 与 Lua 脚本两侧的完整实现。
>
> 对应源码：
> - Lua 脚本：`reframework/autorun/re4_livereload.lua`（v2.15，死代码清理后约 1600 行）
> - C++ 插件：`G:\re4-mod-manager\src\hooks.cpp`、`src\util.cpp`、`src\mod_index.cpp`、
>   `src\redirect.cpp`；热重载已原生移植到 `src\live_reload.cpp`（REFramework 插件 DLL）

---

## 目录

0. 一句话原理
1. 背景：RE Engine 资源加载机制与我们要绕开的缓存
2. C++ 侧三层 hook 详细规格（必须先有）
3. REFramework Lua API 速查（含沙箱限制与坑点）
4. Lua 脚本完整架构
5. 核心机制详解（alias / add_ref / Holder / staged 跨帧）
6. 完整实现代码模板（含注释解释每段在做什么）
7. UI 实现
8. 验证三件套 + 失败诊断流程
9. 坑点全表（症状 → 根因 → 修法）
10. 恢复 / 回滚 / 重启
11. 跨项目可复用 skill 沉淀
12. COVERED_LIST 动态化方案(设计稿)

---

## 0. 一句话原理

RE Engine 的资源缓存键是**路径字符串**。`create_resource(同路径)`
永远返回缓存旧对象。绕过方法：

1. C++ 把 mod 文件路径的 hash 毒化成固定哨兵，让引擎在原路径上
   cache miss（即使引擎内部 hash 表把原路径指向哨兵也找不到东西）。
2. Lua 用 `create_resource(alias_path)`，alias_path 与原路径仅大小写
   不同，引擎视为全新路径 → 第二次 cache miss → 真去读盘 → 读盘
   触发 Win32 hook 把路径改写到 mod 文件 → 拿到 mod 的字节。
3. `add_ref()` 把新资源注册进引擎表。
4. 包成 Holder 挂到材质槽位上。

---

## 1. 背景：RE Engine 资源加载机制

### 1.1 RE Engine 是什么

RE Engine（Capcom 自研）跑在 RE4 / RE2R / RE3R / RE7 / DMC5 等。
关键运行时特征：

- 资源以 path 字符串为唯一标识符（**大小写敏感**）。
- 同一 path 调 `create_resource` 永远返回缓存里的对象（**永不过期**）。
- 资源加载通过原生 Win32 `CreateFileW` → 读 pak 文件 / 原生文件系统。
- 资源在内存里组织成 `Resource` 类（含引用计数 `m_refCount`），
  通过 `add_ref`/`release` 管理。**未 add_ref 的资源不能被引擎引用**。

### 1.2 资源类型（热重载涉及的三类）

| TDB 类型名 | 文件后缀 | 内容 | 挂到 mesh 的方法 |
| --- | --- | --- | --- |
| `via.render.TextureResource` | `.tex` | GPU 贴图 | `mesh:setMaterialTexture(m, t, holder)` |
| `via.render.MeshMaterialResource` | `.mdf2` | 材质（贴图引用表 + shader 参数） | `mesh:set_Material(holder)` |
| `via.render.MeshResource` | `.mesh` | 几何体（顶点/索引/蒙皮/LOD） | `mesh:setMesh(holder)`（仅 staged） |

每种资源都有一个 `Holder` 类型（`TypeName + "Holder"`），作用是把
资源指针 + 元数据封装成可绑到 mesh 上的载体。

### 1.3 Mesh 组件结构（通过 sdk.find_type_definition 反射可见）

`via.render.Mesh`（玩家角色身上的 mesh 组件）关键方法：
- `get_MaterialNum()` → Int32，材质段数（每段材质有独立贴图数组）
- `getMaterialName(m)` → string，材质名
- `getMaterialTextureNum(m)` → Int32，该材质有几个贴图槽位
- `getMaterialTextureName(m, t)` → string，贴图通道语义名（如
  `BaseDielectricMap`/`NormalMap`/`AlphaTranslucentOcclusionCavityMap`）
- `getMaterialTexture(m, t)` → 当前绑的贴图 Holder（**注意：返回的是
  Holder 不是 TextureResource**）
- `setMaterialTexture(m, t, holder)` → 替换贴图（holder 是 Holder 指针）
- `get_Material()` → 当前绑的 mdf Holder
- `set_Material(holder)` → 替换 mdf2
- `getMesh()` → 当前绑的 mesh Holder
- `setMesh(holder)` → 替换几何体（仅 staged 路径，默认等待 90 帧）

### 1.4 资源缓存键

引擎内部用 path 字符串（**未规范化大小写**）作 key。意味着：
- `natives/x64/.../cha200_00.tex` 和 `natives/x64/.../cha200_00.TEX`
  在引擎眼里是**两个不同 key**。
- 但 Win32 文件系统（NTFS）默认大小写不敏感，所以实际指向同一文件。
- 这正是 alias 大小写翻转能绕过的关键漏洞。

### 1.5 玩家 mesh 的获取方式

**生产路径（v2.14 起唯一保留的取法）**：拿玩家上下文单例
（`sdk.get_managed_singleton(sdk.game_namespace("CharacterManager"))`
或 `app.CharacterManager`，RE4R 命名空间实为 `chainsaw.`）→
`getPlayerContextRef()` → `get_BodyGameObject()` / `get_HeadGameObject()`
→ 在 Body 子树里 `findChild("cha200_00" / "cha200_10" / "hair")` 拿到
Body/Head/Hair 三个 GameObject，再对它们及子树做
`getComponent(typeof(via.render.Mesh))`。

> 历史：早期版本用过 `via.SceneManager` → `get_CurrentScene()` →
> `scene:findComponents(via.render.Mesh)` 全场景扫描（武器/UI/地形/NPC 全混在
> 一起，需要额外过滤）。该路径属诊断探针，v2.15 已删除。

---

## 2. C++ 侧三层 hook 详细规格

> **重要**：Lua 端不直接改文件 IO。Lua 只负责"在合适时机
> create_resource + 绑回材质"，真正让引擎去读 mod 文件的，是这三个
> C++ hook。三者必须同时工作，缺一个就会 cache miss 后找不到文件。

### 2.1 路径规范化（`util.cpp`）

```cpp
// 把任意路径字符串规范成引擎内部用的格式
void normalize_into(char* dst, size_t dst_sz, const char* src) {
    // 1. 反斜杠化 (/) -> (\)
    // 2. 全 ASCII 小写化 (ascii_lower)
    // 3. 去掉前导 ./ 或 /
    // 结果：natives\x64\... 形式
}
```

这是 mod 索引查 mod 文件路径用的底层函数。

### 2.2 path_to_hash 哈希毒化（`hooks.cpp`）

```cpp
constexpr uint64_t kPoisonHash = 0x100000000ULL;  // 固定哨兵

// 引擎调用 path_to_hash(path) 时:
// 如果 path 是 mod 覆盖的路径，返回 kPoisonHash
// 否则返回引擎原算法算出的真实 hash
uint64_t hook_path_to_hash(const char* path) {
    if (mod_index.contains(normalize(path))) {
        return kPoisonHash;
    }
    return original_path_to_hash(path);
}
```

效果：引擎的 hash 表里所有 mod 路径都映射到同一个哨兵值 →
缓存查表命中哨兵 → 哨兵不在缓存里 → cache miss → 真去 IO。

### 2.3 via.io.file::exists 覆盖

引擎 cache miss 后会调 `via.io.file::exists(path)` 验证文件是否存在。
需要让它对 mod 路径返回 true，否则引擎会跳过加载。

```cpp
bool hook_via_io_file_exists(const char* path) {
    std::string n = normalize(path);
    if (mod_index.contains(n)) return true;
    return original_via_io_file_exists(path);
}
```

### 2.4 Win32 CreateFileW 路径改写

引擎最后通过 Win32 `CreateFileW(path, ...)` 真去读盘。这里把
原路径改写到 mod 实际文件路径：

```cpp
HANDLE WINAPI hook_CreateFileW(LPCWSTR lpFileName, ...) {
    std::string narrow = utf16_to_utf8(lpFileName);
    std::string normalized = normalize(narrow);
    auto it = mod_index.find(normalized);
    if (it != mod_index.end()) {
        // 重定向到 mod 目录下的实际文件
        std::wstring redirected = utf8_to_utf16(it->second);
        return original_CreateFileW(redirected.c_str(), ...);
    }
    return original_CreateFileW(lpFileName, ...);
}
```

注：必须保留其它参数（access mode、share mode 等），只改路径。

### 2.5 mod 索引（`re4_mod_manager.cpp`）

mod 索引数据结构（构建时机：插件加载时扫描 `E:\RE4 Mods\`）：
```cpp
struct ModIndex {
    // key: 原引擎路径（规范化后）
    // value: mod 实际文件路径
    std::unordered_map<std::string, std::string> path_map;
};
```

构建过程：
1. 扫描用户配置的 mod 根目录（默认 `E:\RE4 Mods\InGame\`）
2. 对每个 mod 文件，记录"原路径 → mod 文件路径"映射
3. 原路径从 mod 文件名或 mod 的 manifest 推断

### 2.6 注入方式

编译产物是 `re4_mod_manager.dll`，重命名为 `DINPUT8.dll` 放在游戏根
目录（RE Framework 注入机制：dinput8.dll 被游戏加载时启动插件）。

CMake 构建后 → 复制到 `D:\Games\Resident Evil 4\DINPUT8.dll`。

---

## 3. REFramework Lua API 速查

### 3.1 模块一览

| 模块 | 作用 |
| --- | --- |
| `sdk` | 反射核心：find_type_definition / create_instance / create_resource / get_managed_singleton |
| `re` | 框架：on_draw_ui / on_application_entry / log |
| `imgui` | UI：button / checkbox / text / input_text / same_line / push_item_width |
| `fs` | 文件系统（**沙箱限制**：只能访问特定子目录） |
| `log` | info / warn / error（**注意：log.info 不写 reframework_log.txt，只在内存**） |
| `json` | JSON 编解码 |

### 3.2 沙箱限制

- **没有** `io.open` / 标准 Lua 文件 IO。
- 文件写入必须用 `fs.write(filename, content)`，`fs.read(filename)`，
  `fs.glob(pattern)`。相对路径以 REFramework data 目录为基准
  （实测写 `"re4_livereload.txt"` → `reframework/data/re4_livereload.txt`）。
- 没有 `os.execute` / `os.remove` 等系统调用。
- 没有 `require`，但 `dofile` 似乎可用（视版本而定，不依赖）。
- 没有 `socket` / `os.tmpname`。

### 3.3 关键 API 详细说明

#### sdk.find_type_definition(name)
返回 `RETypeDefinition`，提供 `:get_method(name)`、`:get_field(name)`、
`:get_methods()`（数组）、`:get_fields()`（数组）。

#### sdk.create_instance(type_name, add_ref)
创建托管对象实例。`add_ref=true` 自动加引用。返回实例或 nil。

#### sdk.create_resource(type_name, path)  ← **核心 API**
根据 path 字符串从引擎加载资源（**触发 path_to_hash + file::exists + CreateFileW 三层 hook**）。
返回 `TextureResource`/`MeshResource` 等。**返回的对象必须 add_ref
才真正注册**，否则后续 setMaterialTexture 静默拒绝。

#### sdk.get_managed_singleton(type_name)
获取单例（如 `via.SceneManager`、`via.GameInstance`）。返回 nil 时
用 `sdk.get_native_singleton` 兜底再试。

#### sdk.is_managed_object(obj)
判断 obj 是否还有效（gc 释放或 invalidate 后会 false）。
**重要**：setMaterialTexture 之前必须先 is_managed_object 检查 mesh
是否还有效，否则会触发已释放对象的访问。

#### sdk.call_native_func(obj, type_def, "MethodName(arg_types)")
直接走 native 调用。**比 `:method()` 调用更稳定**，因为前者绕过
某些重载解析问题。常用模式：
```lua
sdk.call_native_func(mesh, td, "setMaterialTexture(Int32,Int32,Object)")
```

### 3.4 反射调用对象的最佳实践

Lua 里调 C# 风格对象方法有 4 种方式，按可靠性排序：
1. `obj:method(args)` — 简洁，但重载解析有时出错
2. `sdk.call_native_func(obj, td, "method(Types)")` — 最稳
3. `td:get_method(name):call(obj, args)` — 中等
4. 直接 `td:get_method(name)` 拿到 MethodInfo，手动 invoke

本项目里的 `raw_call(obj, name, ...)` 封装了 1/3 方式重试：
```lua
local function raw_call(obj, name, ...)
    local methods = { obj[obj_method_name], td_get_method, ... }
    for _, m in methods do
        local ok, r = pcall(m, obj, ...)
        if ok then return true, r end
    end
    return false, nil, "all attempts failed"
end
```

### 3.5 imgui 控件注意点

| 控件 | 签名 | 返回值 | 注意事项 |
| --- | --- | --- | --- |
| `imgui.button(label)` | 单参数 | boolean | 一次点击只触发一次 true |
| `imgui.checkbox(label, current)` | label + 当前值 | `(changed, new_value)` | 第一次 unpack 时一定拿 new_value |
| `imgui.input_text(label, value)` | label + 当前值 | `(changed, new_value)` | **第三个可选参数 width 不被所有版本支持**，用 push_item_width 控制宽度 |
| `imgui.text(str)` | 单参数 | nil | 用于静态文本 |
| `imgui.same_line()` | 无参 | nil | 让下一个控件接到当前行右侧 |
| `imgui.push_item_width(px)` | 像素宽度 | nil | 与 pop_item_width 配对 |
| `imgui.pop_item_width()` | 无参 | nil | 恢复到默认宽度 |

### 3.6 线程模型

- `re.on_draw_ui(fn)`：**ImGui 渲染线程**调用
- `re.on_application_entry("PrepareRendering", fn)`：**主线程**调用
- 这两条线程**共享 Lua 全局状态**（表、变量），但**没有锁**。
  跨线程读写同一表会触发 race → 数据撕坏 → 后续崩溃。
- **绝对禁止**在 on_draw_ui 里改资源（渲染线程正画角色时会碰到正在改的资源）。
- **跨线程共享变量**（如 STAGED、APPLY_QUEUE）必须在 UI 端用 pcall + 本地快照读。

### 3.7 log 写入的陷阱

- `log.info("text")`：**只写内存**，**不**写到 `reframework_log.txt`。
  REFramework 自己的崩溃栈才会写到 `reframework_log.txt`。
- `fs.write(filename, content)`：脚本自己的日志必须用这个写文件。
  整个文件**每次都覆盖**（不是 append），需要 `LOG` 表累积 + 定期
  flush。
- 推荐模式：
```lua
local LOG = {}
local function logf(fmt, ...) LOG[#LOG+1] = string.format(fmt, ...) end
local function flush()
    local ok = pcall(fs.write, "re4_livereload.txt", table.concat(LOG, "\n") .. "\n")
end
```

---

## 4. Lua 脚本完整架构

### 4.1 文件分层

```
re4_livereload.lua (v2.15, 死代码清理后约 1600 行)
├── 配置层：OPT 表（mesh/material/filter/alias/bind_delay 等开关）
├── 工具层：logf / flush / raw_call / call_any / resource_addr / addr_str
├── 资源层：make_holder / alias_path / is_covered / COVERED_LIST
├── 场景层：player_gameobjects / player_parts / player_meshes /
│           mesh_inventory / discover_slots / backup_mesh / do_restore
├── staged 层：build_bind_jobs / staged_phase1 / run_staged / STAGED
├── 调度层：APPLY_QUEUE / request_apply / run_apply_queue
└── UI 层：re.on_draw_ui（pcall 包裹）
```

> v2.15 已删除（均无 UI 入口、live 路径无调用者）：swap_textures /
> full_rebind / do_swap / do_full_rebind / do_reload_scene / current_scene /
> scene_meshes / call_static / scan_player / probe_player / probe_accessors /
> path_probe / dump_mesh(+MOD_SLOT_HINTS) / null_texture_holder / res_name /
> try_prop / seq_get / to_table_seq / args_str / fmt_val（净 -716 行）。

### 4.2 全局状态机

```lua
local OPT = { ... }              -- 配置（checkbox 状态）
local EPOCH = 1                  -- 别名计数器（每次 swap +1；从 1 起，保证首个别名 != 原路径）
local COVERED_LIST = { ... }     -- 写死的 42 条 mod 路径
local COVERED_N = 42             -- 列表长度

local LOG = {}                   -- 日志累积
local BACKUP = {}                -- mesh_key -> backup_table
local BACKUP_ORDER = {}          -- 备份顺序

local APPLY_QUEUE = {}           -- 待执行任务队列
local APPLY_BUSY = false         -- 防重入
local STAGED = nil               -- staged 管线状态：{jobs, frames, delay}
```

### 4.3 关键不变式

- `STAGED` / `APPLY_QUEUE` / `BACKUP` **只能由主线程读写**。UI 端要读
  必须 pcall + 本地快照。
- `EPOCH` 每次 swap 后 `+1`，别名池 `2^(字母位数)`，短时间循环耗尽
  不是问题（实测量级上千）。
- `COVERED_LIST` 是安全闸门——任何不在列表里的路径，脚本都跳过不操作。

---

## 5. 核心机制详解

### 5.1 alias_path(p, epoch) — 大小写别名

```lua
local function alias_path(p, epoch)
    -- 在路径字符串里挑几位字母，翻转其大小写
    -- epoch 控制挑哪几位（保证两次 swap 不会撞回同一路径）
    -- 例如 epoch=1: cha200_00 -> cHa200_00
    --     epoch=2: cha200_00 -> chA200_00 (不同位置)
    -- ...
end
```

**为什么够用**：RE Engine 资源缓存键严格区分大小写。同一文件大小写
变体是全新字符串 → 引擎视为从未见过的资源 → cache miss → 真去读盘。
**NTFS 默认大小写不敏感**，所以 `cHa200_00.TEX` 实际指向同一个物理
文件 → Win32 CreateFileW hook 把它改写到 mod 文件。

### 5.2 make_holder(raw_type, path) — Holder 标准写法

```lua
local function make_holder(raw_type, path)
    -- 1. 大小写别名
    local used = OPT.alias and alias_path(path, EPOCH) or path
    -- 2. create_resource 触发三层 hook 真读盘
    local res = sdk.create_resource(raw_type, used)
    if res == nil then return nil, "create_resource failed", nil, nil, used end
    -- 3. add_ref（关键修复，缺这一步 setMaterialTexture 静默拒绝）
    local okr, r2 = pcall(function() return res:add_ref() end)
    if okr and r2 ~= nil then res = r2 end
    -- 4. Holder 类型名 = "TypeName + Holder"
    local holder_type = raw_type .. "Holder"
    local holder = sdk.create_instance(holder_type, true)
    -- 5. 初始化 Holder
    holder:add_ref()
    holder:ctor()
    -- 6. 把资源指针写到 Holder 偏移 0x10
    local res_addr = resource_addr(res)
    holder:write_qword(0x10, res_addr)
    -- 7. 保活（防止 gc）
    holder:add_ref()
    return holder, nil, res_addr, nil, used, res
end
```

**关键修复点**：`res:add_ref()` 在 v2.7 加入。之前漏这一步导致
38 个贴图槽位全部 bind-invalid（引擎默默拒绝，但 call=true）。

**Holder 偏移 0x10**：实测发现 Holder 类在偏移 0x10 处是 `m_Resource`
指针字段。直接 write_qword 比走反射调 setter 更快更稳。

### 5.3 staged_phase1 + run_staged — 跨帧 create/bind

```lua
local function staged_phase1(tag, opts)
    if COVERED_N == 0 then return  -- 覆盖列表为空，直接拒
    local jobs = build_bind_jobs(opts)  -- 收集要绑的所有槽位
    local ready = {}
    for i = 1, #jobs do
        local j = jobs[i]
        local rtype = kind_to_type(j.kind)  -- texture/mdf2/mesh
        local holder, err, new_addr = make_holder(rtype, j.path)
        if holder ~= nil then
            j.holder = holder
            j.new_addr = new_addr
            ready[#ready + 1] = j
        end
    end
    STAGED = { jobs = ready, frames = opts.bind_delay or 90, delay = opts.bind_delay or 90 }
    -- ^ 关键：保存到 STAGED 全局，主线程每帧倒计 frames
end

local function run_staged()
    if STAGED == nil then return end
    if STAGED.frames > 0 then
        STAGED.frames = STAGED.frames - 1
        return
    end
    local st = STAGED
    STAGED = nil
    for i = 1, #st.jobs do
        local j = st.jobs[i]
        if sdk.is_managed_object(j.mesh) then
            if j.kind == "material" then
                raw_call(j.mesh, "set_Material", j.holder)
            elseif j.kind == "mesh" then
                raw_call(j.mesh, "setMesh", j.holder)
            else  -- texture
                raw_call(j.mesh, "setMaterialTexture", j.m, j.t, j.holder)
            end
        end
    end
    EPOCH = EPOCH + 1
end

re.on_application_entry("PrepareRendering", function()
    run_apply_queue()  -- UI 按钮入队的同步任务
    run_staged()       -- staged 倒计 + phase2 绑定
end)
```

**为什么必须分两阶段**：TextureResource/MeshResource 的 GPU 上传是异步
的。同帧 create + bind → 下一帧渲染线程拿半成品 → c0000005。phase1
先 create + 保活，等 N 帧让引擎消化，再 phase2 bind。

其中 `MeshResource` 的 `setMesh(holder)` 运行时替换已启用，但只允许走
staged 路径；旧的 4 帧 immediate 路径已删除。默认等待 90 帧（约 1.5 秒，
60 FPS），因为 mesh 绑定可能在资源完全就绪前成功，并在下一帧渲染时崩溃。
即使等待 90 帧仍崩溃，也可能是 mod mesh 与原 mesh 的骨骼/蒙皮结构不兼容，
这属于 mod 文件本身的问题。

### 5.4 is_covered 闸门

```lua
local COVERED_LIST = {
    -- 42 条硬编码路径（Ada 服装相关）
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00.mdf2", ...
}

local COVERED = {}
for _, k in ipairs(COVERED_LIST) do
    COVERED[k] = true               -- 集合，精确匹配
end
local COVERED_N = #COVERED_LIST

local function is_covered(path)
    if type(path) ~= "string" or path == "" then return false end
    local k = path:lower()                       -- 小写
    k = k:match("^.+%[@?(.+)%]") or k              -- 去 holder 的 "...@[path]" 包装
    if is_never_touch(k) then return false end   -- 第二道闸门
    return COVERED[k] == true                    -- 精确命中（非子串匹配）
end
```

> `is_never_touch` 拒绝引擎内部/不可安全绑定的路径：
> `systems/`、`re_engine_library/`、结尾 `.rtex`、含 `rendertargetlist`、含 `_array`。
> 名单本身只能说明“mod 覆盖了它”，不代表绑定安全，这层过滤不能省。

**作用**：alias 强制 cache miss 后，引擎会去 pak 找原路径对应的文件。
如果路径不在 mod 覆盖范围（`is_covered=false`）→ 引擎找不到 → 返回
空资源 → setMaterialTexture 用空指针 → c0000005。所以 alias 必须配
合 is_covered 闸门，否则会打崩非 mod 路径。

---

## 6. 完整实现代码模板

### 6.1 最小可运行骨架

```lua
-- ============================================================
-- re4_livereload.lua skeleton
-- 假设 C++ 三层 hook 已就绪 (path_to_hash + via.io.file::exists + CreateFileW)
-- ============================================================

local OPT = {
    alias = true,             -- 大小写别名（不可关）
    mesh = false,             -- mesh 重载开关（staged only）
    material = false,          -- mdf2 重载开关
    textures = true,
    bind_delay = 90,           -- staged 等待帧数（90 ≈ 1.5s @ 60fps）
    filter = "",               -- 路径过滤（空=全部）
}

local EPOCH = 0
local LOG = {}
local APPLY_QUEUE = {}
local STAGED = nil
local BACKUP = {}
local BACKUP_ORDER = {}

-- ----- 日志 -----
local function logf(fmt, ...)
    local line = string.format(fmt, ...)
    LOG[#LOG + 1] = line
end
local function flush()
    pcall(fs.write, "re4_livereload.txt", table.concat(LOG, "\n") .. "\n")
end

-- ----- alias -----
local function alias_path(p, epoch)
    -- 翻转路径里某些字母的大小写
    -- 这里简化实现：固定翻转第 8 位
    if #p < 8 then return p end
    local pos = 8
    local byte = string.byte(p, pos)
    if byte >= string.byte("a") and byte <= string.byte("z") then
        return p:sub(1, pos - 1) .. string.char(byte - 32) .. p:sub(pos + 1)
    elseif byte >= string.byte("A") and byte <= string.byte("Z") then
        return p:sub(1, pos - 1) .. string.char(byte + 32) .. p:sub(pos + 1)
    end
    return p
end

-- ----- Holder -----
local function make_holder(raw_type, path)
    local used = OPT.alias and alias_path(path, EPOCH) or path
    local res = sdk.create_resource(raw_type, used)
    if res == nil then return nil end
    pcall(function() res:add_ref() end)
    local holder = sdk.create_instance(raw_type .. "Holder", true)
    if holder == nil then return nil end
    holder:add_ref()
    pcall(function() holder:ctor() end)
    -- 资源指针写到 Holder 偏移 0x10
    pcall(function() holder:write_qword(0x10, tostring(res)) end)
    return holder
end

-- ----- 队列 -----
local function request_apply(tag, fn)
    APPLY_QUEUE[#APPLY_QUEUE + 1] = { tag = tag, fn = fn }
    logf("[queue] '%s' enqueued", tag)
    flush()
end

local function run_apply_queue()
    if #APPLY_QUEUE == 0 then return end
    local job = table.remove(APPLY_QUEUE, 1)
    pcall(job.fn)
end

-- ----- staged -----
local function run_staged()
    if STAGED == nil then return end
    STAGED.frames = STAGED.frames - 1
    if STAGED.frames > 0 then return end
    local st = STAGED
    STAGED = nil
    for _, j in ipairs(st.jobs) do
        if sdk.is_managed_object(j.mesh) then
            pcall(function()
                if j.kind == "mesh" then j.mesh:setMesh(j.holder)
                    elseif j.kind == "material" then j.mesh:set_Material(j.holder)
                    else j.mesh:setMaterialTexture(j.m, j.t, j.holder) end
                end)
        end
    end
    EPOCH = EPOCH + 1
end

re.on_application_entry("PrepareRendering", function()
    run_apply_queue()
    run_staged()
end)

-- ----- staged_phase1 -----
local function staged_phase1(opts)
    if OPT.textures then
        -- 简化：只列举几个已知槽位
        -- 实际项目里要通过 player_meshes() + mesh_inventory() 动态获取
        local jobs = {}
        -- TODO: 动态枚举玩家 mesh / 贴图槽位
        STAGED = { jobs = jobs, frames = opts.bind_delay or 90 }
    end
end

-- ----- UI（pcall 包裹）-----
re.on_draw_ui(function()
    local ok, err = pcall(function()
        imgui.text("re4_livereload v0.1")
        if imgui.button("Swap textures") then
            request_apply("swap", function() staged_phase1(OPT) end)
        end
        imgui.text("bind delay")
        imgui.same_line()
        imgui.push_item_width(60)
        local _, dv = imgui.input_text("##bd", tostring(OPT.bind_delay or 90))
        imgui.pop_item_width()
        if type(dv) == "string" then
            local n = tonumber(dv)
            if n and n >= 0 and n <= 1800 then OPT.bind_delay = math.floor(n) end
        end
    end)
    if not ok then log.warn("[live_reload] UI error: " .. tostring(err)) end
end)

logf("=== re4_livereload skeleton loaded ===")
flush()
```

### 6.2 完整实现的扩展点

上面骨架只是**最小复现**。要达到生产质量，还需要：

1. **完整的 mesh/mdf/slot 枚举**（`player_meshes()`, `mesh_inventory()`）
2. **资源路径 is_covered 闸门**（写死的 COVERED_LIST 或动态生成）
3. **资源地址验证**（`resource_addr()`, `addr_str()`, `verdict_bind()`）
4. **backup/restore 机制**（swap 前备份原 holder，restore 时还原）
5. **失败容错**（raw_call 多路重试，pcall 包裹每个关键调用）
6. **诊断日志**（创建 / 绑定的成功/失败/跳过都要打日志）

---

## 7. UI 实现

### 7.1 控件清单

| 控件 | 类型 | 作用 |
| --- | --- | --- |
| swap textures (staged) | button | 唯一 swap 路径：90 帧等就绪后绑（v2.14 起已删除 immediate 按钮） |
| restore original bindings | button | 按 backup 还原 |
| clear log | button | 清空 LOG 表 |
| only Body/Head/Hair | checkbox | 限定 mesh 范围 |
| reload mdf (material file) | checkbox | 是否换 mdf2 |
| reload mesh (geometry) | checkbox | 是否换几何体；启用后通过 staged `setMesh` 替换（默认等待 90 帧） |
| wait frames | input_text | staged 等待帧数（默认 90） |

### 7.2 关键 UI 规范

- **整个 on_draw_ui 用 pcall 包裹**：任何 UI 渲染异常只 log.warn 不崩游戏。
- **不要在 UI 里读跨线程状态**（STAGED / APPLY_QUEUE 等）：会触发 race。
- **alias 不要暴露开关**：alias 关 = 走原路径 = cache hit = 绑回自己。
- **input_text 宽度**：用 `push_item_width(60)` + 隐藏标签 `##name`，
  不要依赖 input_text 第三参数（兼容性差）。

---

## 8. 验证三件套 + 失败诊断流程

### 8.1 三件套

每次 swap 后确认：

1. **`re4_livereload.txt` 末尾**：
   ```
   === STAGED done: N ok, 0 failed | NEW(!=slot)=X SAME=0 bind-invalid=0 ===
   === next epoch=N ===
   ```
   - `ok` = 实际绑定成功数（call=true 且资源指针换了）
   - `bind-invalid` = setMaterialTexture 静默拒绝数（应恒为 0）

2. **`re4_mod_manager.log` 该窗口**：
   出现 `Redirect: 原路径 -> mod文件路径` 行 = 真读盘了（hook 触发）。
   没出现 = 三层 hook 没工作，swap 视觉上零变化。

3. **`reframework_log.txt` 该窗口**：
   **不**应出现 `c0000005` / `igItemSize_Vec2` 栈 / `Exception thrown
   in REMethodDefinition::invoke for via.render.Mesh.setMaterialTexture`。
   任何一条都说明有问题。

### 8.2 call=true 的谎言

**`call=true` 不等于成功**。REFramework 会吞掉 `setMaterialTexture`
抛出的异常并返回 true。必须看：
- `bind-invalid=0`（脚本层面统计）
- `reframework_log.txt` 无异常

双重确认才能算成功。

### 8.3 失败诊断流程

| 症状 | 第一时间排查 |
| --- | --- |
| 视觉零变化 | re4_mod_manager.log 无 Redirect → 三层 hook 没工作 |
| | re4_livereload.txt ALL SAME → alias 关了 |
| | re4_livereload.txt list does not match → COVERED_LIST 不匹配 |
| 崩在 setMaterialTexture | is_covered 闸门漏判 / Holder 没 add_ref |
| 崩在 igItemSize_Vec2 | on_draw_ui 读跨线程状态触发 race |
| 崩在 setMesh | MeshResource 就绪时间不够，加 bind_delay |
| reframework_log.txt 全是 Exception thrown | 几乎肯定是 Holder 构造错（缺 add_ref 或偏移写错） |

---

## 9. 坑点全表

### 9.1 C++ 侧

| 症状 | 根因 | 修法 |
| --- | --- | --- |
| 换 mod 无视觉变化 | 三层 hook 没生效 | 检查 CreateFileW hook 是否成功注入；mod 索引是否正确构建 |
| 视觉变化但部分贴图错位 | hash 毒化覆盖范围太大 | 收紧 mod 索引的路径匹配（避免误命中） |
| 崩溃在 via.io.file::exists 路径 | 该 hook 改变了大小写比较行为 | 保持大小写敏感语义 |

### 9.2 Lua 侧

| 症状 | 根因 | 修法 |
| --- | --- | --- |
| bind-invalid = 槽位数 | `create_resource` 后**漏了 `add_ref`** | make_holder 里补 `res:add_ref()` |
| bind-invalid = 38, reframework_log Exception thrown | setMaterialTexture 收到空 Holder | Holder 偏移 0x10 没正确写入资源指针 |
| ALL SAME 警告，NEW=0 | alias 没开 / 路径被 COVERED_LIST 拦截 | 开 alias（默认已开）/ 扩 COVERED_LIST |
| NEW>0 但视觉无变化 | 实际没换 mod（重读出同样字节） | 这是预期行为，不是 bug |
| Phase1 创建全 FAIL | create_resource 返回 nil | 三层 hook 没工作；查 re4_mod_manager.log |
| igItemSize_Vec2 崩 | on_draw_ui 读 STAGED 跨线程 race | 删掉 STAGED 指示器 + pcall 包裹 on_draw_ui |
| mesh swap 等待帧数太少崩 | MeshResource 没就绪 | mesh 只走 staged（默认 90 帧）；immediate 快速路径已于 v2.14 删除 |
| staged(90 帧) mesh swap 也崩 | 模的 mesh 文件不是原 mesh 的"无缝替换"（骨骼/蒙皮对不上） | 这是 mod 本身问题，非脚本问题 |
| setMaterialTexture 抛 NotImplemented | TDB 方法签名匹配错 | 用 sdk.call_native_func 强制走 native |

### 9.3 通用 Lua 沙箱坑

| 症状 | 根因 | 修法 |
| --- | --- | --- |
| log.info 输出在内存，reframework_log.txt 没记录 | REFramework 不会把 Lua log 转发 | 自己用 fs.write 写文件 |
| fs.write 每次都覆盖文件 | REFramework 的 fs 实现 | 用 LOG 表累积 + 定期 flush |
| imgui.input_text 第三参数 width 无效 | 部分 REFramework 版本不识别 | 用 push_item_width(px) + pop_item_width() 配对 |

---

## 10. 恢复 / 回滚 / 重启

### 10.1 出问题的第一动作

**点 Restore original bindings** 按钮。
- 会按 backup 表还原所有材质/贴图/mesh 到原始 holder。
- mesh/mdf/tex 一起还原（v2.12 起 do_restore 重新启用 setMesh）。

### 10.2 Restore 也崩的情况

**重启游戏**。
- 运行时状态被改坏，但**没写盘**。
- 重启后 EPOCH、所有 BACKUP、引擎资源缓存全部清零。
- 重新勾 staged + reload mesh（如需），再 swap。

### 10.3 改脚本后

**必须 Reload Scripts**（REFramework UI 里，或重启游戏）。
- Lua 脚本不会热更新正在运行的 autorun。
- Reload 后脚本的 OPT 状态会重置（checkbox 回到默认）。

---

## 11. 跨项目可复用 skill 沉淀

把本项目里总结出来的"RE Engine mod 热重载"模式做成 skill，
下次接 RE2R / RE3R / DMC5 等同样引擎的游戏可直接复用：

- **算法层**：alias 大小写别名 + add_ref + 跨帧 create/bind 三件套
- **C++ hook 层**：path_to_hash 毒化 + via.io.file::exists + CreateFileW
- **Lua 模式层**：UI 入队 + PrepareRendering 主线程调度 + staged 管线
- **诊断层**：三件套日志（脚本日志 / 重定向日志 / 崩溃日志）

引擎版本/资源类型名（`via.render.TextureResource` 等）每作不同，
需要重新通过 `sdk.find_type_definition` 反射查 TDB 确认。

---

## 12. COVERED_LIST 动态化方案(设计稿)

> **本节状态**：**Lua 侧未实施**（`re4_livereload.lua` v2.15 仍用内置 COVERED_LIST）。
> 但其中“覆盖名单由插件 mod 索引动态推导”的目标，已在 C++ 原生移植版
> `G:\re4-mod-manager\src\live_reload.cpp` 中以更直接的方式实现：C++ 在
> `is_covered()` 里直接遍历插件 mod 索引的键（做 `natives/`+`stm/` 前缀与尾部
> `.NNN` 归一化），**不再需要导出到 `reframework/data` 让 Lua 读取**。本节保留为
> Lua 方案的原始设计记录；若日后仍需维护 Lua 版，可按下述文件交接方案实现。
>
> 原设计目标：让 `re4_livereload.lua` 里的 `COVERED_LIST`(44 条硬编码)改为
> **由插件导出、Lua 运行时加载**，
> 名单永远和当前已装 mod 同步，取消"重跑生成脚本 + 手工粘贴"流程。

### 12.1 现状与问题

**现存名单的来源链路**(两条语句拼出来的)：

1. 插件在 `should_poison_hash()`(`src/redirect.cpp:325`)里查 mod 索引，
   命中且 mod 文件可用时打一行 `Poison (mod): <原路径>`(`redirect.cpp:354`)。
2. 离线脚本 `G:\re4-mod-manager\.workbuddy\tmp\gen_covered.js` 抓这些行，
   按 `logicalKey()` 规范化(反斜杠→`/`、小写、去 `natives/` 前缀、去尾部
   `.N`)，写出 `.workbuddy\tmp\covered_keys.lua`(实测 123 条)。
3. 人工挑出其中 `.tex/.mdf2/.mesh` 的 44 条，粘贴进 Lua 的 `COVERED_LIST`。

**问题**：

| 问题 | 后果 |
| --- | --- |
| 静态快照 | 换新 mod / 新角色(如 Leon cha000)后路径不在名单里 → 全部 `skipped` → swap 零效果 |
| 手工再生成 | 必须重跑 node 脚本 + 手工筛 44 条 + 手改 Lua, 易漏 |
| 名单与索引可能不一致 | 少键 = 该换的不换; 多键 = 无害(闸门只是放行, 真正决定是否换成功的是索引命中) |

**当初为什么硬编码**：Lua 沙箱够不着插件索引。

- `io.open` 被禁; `fs.glob` 的根只有 `<gamedir>/natives`、`reframework/data`、
  `reframework/autorun`, 到不了 mod 根目录 `E:\RE4 Mods`;
- `fs` 的相对路径以 `reframework/data` 为基准(`FS.cpp get_correct_subpath`
  还拦 `..`), 所以连插件日志 `reframework/re4_mod_manager.log` 也读不到。

**突破口**：`reframework/data` 是 Lua 唯一能读写的目录 —— 让 C++ 把索引
键**写到那里**，链路就通了。

### 12.2 目标 / 非目标

**目标**

- 名单随索引自动更新, 零手工步骤。
- 安全闸门语义完全不变: `is_covered()` 仍必须成立才做 alias + rebind。
- 任何失败路径都安全降级(文件缺失/为空 → 退回内置名单), 绝不因此崩溃。

**非目标**

- 不改 alias / `add_ref` / Holder 0x10 / staged 跨帧机制。
- 不做 Lua↔C++ 实时 IPC: 命名管道在沙箱里被禁, 文件交接是最稳的方式。
- 不在这一版做"按角色/服装过滤"等更上层功能。

### 12.3 总体数据流

```
        [C++] 索引构建/重建
   build_index → publish_index  (mod_index.cpp:490/495)
   plugin.cpp:204 启动时 rebuild_and_publish
   plugin.cpp:198 index_rebuilt_callback 已在用, 可同点挂钩
                    │
                    ▼  export_covered_keys(index)
   <gamedir>\reframework\data\covered_keys.txt   ← Lua 唯一可读目录
                    │
                    ▼  [Lua] 脚本加载时 fs.read("covered_keys.txt")
        COVERED set + COVERED_N  ──►  is_covered()  (闸门不变)
                    │
              (文件缺失/0 条)
                    ▼
        FALLBACK_COVERED_LIST (现 44 条内置名单, 降级保底)
```

### 12.4 C++ 侧设计

**新增**：`export_covered_keys(const std::shared_ptr<ModIndex>&)`
(建议放 `mod_index.cpp` 或新文件 `src/covered_export.cpp` + CMake 加源文件)。

**触发点**(索引每次发布之后都要导一次, 不能只在启动时导):

- `plugin.cpp:204` 启动时 `rebuild_and_publish`;
- `mod_index.cpp:490` / `:495` 后台指纹变化后的重建;
- 或统一挂在现有 `p4r::set_index_rebuilt_callback()`(`plugin.cpp:198`)
  旁边——它已经在索引重建时被调一次。

**导出判据(必须与 `Poison (mod):` 日志行完全对齐)**：

- 遍历索引键, **仅导出 `mod_file_available(路径) == true` 的键**
  ——这正是 `should_poison_hash()` 命中分支的条件(`redirect.cpp:349-357`)。
- 效果: 文件内容 == "当前运行中真正会被毒化/重定向的键集", 与旧
  `gen_covered.js` 的数据源同义, 只是从"事后捞日志"变成"事前查索引"。

**键格式**：与 `index->find_view(key)` 使用的 `canonicalize()` 键同形, 再按
`gen_covered.js` 的 `logicalKey()` 规则输出(小写 / `/` / 去 `natives/`
前缀 / 去尾部 `.N`), 保证与 Lua 侧槽位路径(`holder_path()` 出来已经是
lower + 去 `[...]`)可直接字符串比较。**实施前必须先验证同形性**, 见 12.7。

**文件格式**(UTF-8, LF, 一行一键)：

```
# re4_mod_manager covered keys
# generated: 2026-09-11T08:02:38Z
# count: 123
_chainsaw/character/ch/cha2/cha200/00/cha200_00.mdf2
_chainsaw/character/ch/cha2/cha200/00/cha200_00.mesh
...
```

- 注释头带生成时间与条数, 便于"这份名单多旧"一眼可判。
- 不做增量写: 每次全量覆盖(数千键 < 数百 KB, 一次写无压力)。

**工程细节**：

| 项 | 设计 |
| --- | --- |
| 目录定位 | `util::game_dir() + L"reframework\\data\\"`, 目录不存在则创建 |
| 原子性 | 先写 `covered_keys.txt.tmp`, 再 `MoveFileEx(..., MOVEFILE_REPLACE_EXISTING)` |
| 线程 | 在后台重建线程内做; `current_index()` 返回 `shared_ptr`, 取快照后离锁遍历, 不阻塞主线程 |
| 失败处理 | 写失败只 `log::warn`, 绝不抛/崩; 导出是 best-effort 附属功能 |
| 开关 | 可选 config 项 `export_covered_keys`(默认开), 关闭后 Lua 侧自动走 fallback |

### 12.5 Lua 侧设计

**新增 `load_covered_list()`**, 在脚本加载时调用一次：

```lua
local FALLBACK_COVERED_LIST = { ... }  -- 现 COVERED_LIST 的 44 条, 改名保留
local COVERED, COVERED_N, COVERED_SRC = {}, 0, "fallback"

local function load_covered_list()
    local ok, text = pcall(fs.read, "covered_keys.txt")   -- 相对 reframework/data
    if ok and type(text) == "string" then
        local n = 0
        for line in text:gmatch("[^\r\n]+") do
            if line:sub(1, 1) ~= "#" then                 -- 跳注释
                local k = line:lower():match("^.+%[@?(.+)%]") or line:lower()
                if k:find("%.tex$") or k:find("%.mdf2$") or k:find("%.mesh$") then
                    COVERED[k] = true
                    n = n + 1
                end
            end
        end
        if n > 0 then
            COVERED_N, COVERED_SRC = n, "file"
            return
        end
    end
    for _, k in ipairs(FALLBACK_COVERED_LIST) do COVERED[k] = true end
    COVERED_N = #FALLBACK_COVERED_LIST
    COVERED_SRC = "fallback"
end
```

**只保留 `.tex/.mdf2/.mesh`** 这一条过滤规则与 `gen_covered.js` 的 embed
过滤一致, 也让 Lua 侧不必关心 `.motlist/.user/.pfb` 等不可热重载类型。

**不改动的部分**：

- `is_covered()` 逻辑不变(仍是 `COVERED[k] == true`), 只是数据来源变了;
- `is_never_touch()`(`systems/`、`re_engine_library/`、`.rtex`、
  `rendertargetlist`、`_array`)作为**第二道闸门保持原样** —— 名单来自
  索引也只说明"mod 覆盖了它", 不代表运行时绑它是安全的;
- `COVERED_N == 0` 时拒绝运行的 guard 保留。

**UI / 可观测性**：

- 顶部状态行显示来源与条数:
  `cover list: 121 from covered_keys.txt (gen 2026-09-11T08:02Z)` 或
  `cover list: 44 fallback (covered_keys.txt missing)`。
- 可选加一个 `Reload cover list` 按钮, 经 `request_apply()` 走主线程重读
  (热更新 mod 目录后无需重启也能刷新名单)。

### 12.6 兼容与降级矩阵

| 插件版本 | 文件状态 | 行为 |
| --- | --- | --- |
| 新(有导出) | 存在且有有效键 | 用文件, 零手工 |
| 新(有导出) | 存在但 0 有效键 | fallback + 日志告警(视为异常) |
| 新(有导出) | 目录不可写/写失败 | fallback(=现状), 插件日志有 warn |
| 旧(无导出) | 不存在 | fallback(=现状), 脚本照跑 |
| 任意 | 任意, Lua 是旧版 | 无影响, 只是多一个不被读取的文件 |

关键点: **旧插件 + 新 Lua、新插件 + 旧 Lua 两个组合都不会坏**, 这让两侧
可以分开提交/分开构建, 不必强制同步升级。

### 12.7 实施前必须验证的开放问题

1. **键形同形性是最大风险**：索引 `canonicalize()` 出来的键, 与 Lua 从
   mesh 槽位拿到的 `holder_path()` 字符串是否逐字相同? 实施第一步应在导出
   时同时打 3-5 条样例键到插件日志, 与 `re4_livereload.txt` 里的
   `slot ... path=...` 行肉眼对照; 不一致就在 Lua 侧加一层规范化补丁。
2. `ModIndex` 是否已有键遍历接口? 没有则补一个 const 迭代器(如 `keys()`),
   避免多处友元式访问内部 map。
3. `reframework/data` 在插件启动早期是否已存在(REFramework 先建目录还是
   插件先加载)? 不存在则自建, 并确认与 REFramework 的路径解析一致。
4. `fs.read` 对大文件(数百 KB)的行为与稳定性, 实测一次。
5. 索引重建很频繁时(游戏重获焦点会触发, `plugin.cpp:218`)导出频率是否
   可接受 —— 若不可接受, 改为"内容变化才写"(与旧文件比对 sha/长度)。

### 12.8 测试计划

> 本机无构建环境, 一切编译/验证走 GitHub Actions(见 `AGENTS.md`)。

**C++ 侧**

1. push → `gh run watch` → `gh run download --name re4_mod_manager` →
   DLL 放 `D:/Games/Resident Evil 4/reframework/plugins`。
2. 启动游戏: `reframework/data/covered_keys.txt` 存在; `# count:` 与
   旧 `covered_keys.lua` 的 123 条同量级(差异应可解释)。
3. 在游戏内 UI 改 mod 目录 / 触发 rescan → 文件 mtime 更新, 内容随索引变化。
4. 删掉 mod 目录让其不可用 → 对应键从文件中消失(证明 `mod_file_available`
   判据生效)。

**Lua 侧**

1. autorun 日志出现 `cover list loaded: N from covered_keys.txt`。
2. swap 行为与旧 44 条名单一致(旧名单是文件集的子集, 原命中项应全命中)。
3. 把 `covered_keys.txt` 改名 → 日志显示 fallback, swap 行为不变(降级可用)。
4. 造一个 0 有效键的文件 → 走 fallback 且有告警。

**回归场景**

- 装一个旧名单里没有的 mod(Leon cha000 或新服装) → 重启或 rescan →
  **不改一行 Lua** 直接 swap 生效 —— 这是本方案要解决的核心场景。

### 12.9 实施清单(预估工作量)

| 项 | 内容 | 规模 |
| --- | --- | --- |
| C++ | `export_covered_keys()` + publish 后挂钩 + 原子写 + 可选 config 开关(+ CMake 新文件) | ~80-120 行 |
| Lua | `load_covered_list()` + `COVERED_LIST` 改名 `FALLBACK_COVERED_LIST` + UI 状态行(+ 可选 reload 按钮) | ~40-60 行 |
| 文档 | 实施后回填本节"已实施"状态, 更新 11 章与附录时间线 | 小 |
| 提交拆分 | ① `feat(plugin): export covered keys to reframework/data` ② `feat(lua): load cover list at runtime` | 2 commit |

`gen_covered.js` **保留**, 转为离线诊断工具(排查"索引里到底有没有这个键")。

### 12.10 已考虑并否决的替代方案

| 方案 | 否决原因 |
| --- | --- |
| 只改进 `gen_covered.js`, 自动改写 Lua 文件名单位 | 仍是半自动: 换 mod 后必须记得重跑, 且要求游戏先跑过一次产生 `Poison` 日志 |
| Lua 直接扫 `E:\RE4 Mods` 自建名单 | 沙箱不允许访问该目录; 且"mod 里有文件"≠"引擎会走这个键", 判据不如索引准 |
| 命名管道 / 共享内存 / 导出 C 函数给 Lua 调 | 沙箱禁命名管道; REFramework 无稳定的 C 模块注册通道, 复杂度远高于写文件 |
| 干脆删掉闸门, 全都 alias | 会立刻复现 v2.4 的 c0000005: 不在索引里的别名路径 → 引擎 pak miss + 插件无回落 → `create_resource` 返回空资源 → `setMaterialTexture` 空指针。闸门必须保留(其 Lua 侧成本≈0) |
| 闸门改由插件在 `CreateFileW` 层兜底 | 崩溃发生在 Lua/引擎绑资源阶段, 不是文件读取阶段, 插件拦不到; 兜底只能防"读不到文件", 防不了"拿到空资源还去绑" |

---

## 附录 A：版本演化时间线

| 版本 | 关键变更 |
| --- | --- |
| v2.4 | 原型：基本 swap_textures 路径 |
| v2.5 | 崩溃修复：getMaterialTextureNum 加 MAX_MAT/MAX_TEX 上限 + break |
| v2.6 | alias 诊断提示：绑成功但全 SAME 时提示开 alias |
| v2.7 | **真修复**：create_resource 后补 res:add_ref()（38 槽位 bind-invalid 根因） |
| v2.8 | 诊断修正：res_name 全 nil 假象；alias 默认 ON |
| v2.9 | mesh + mdf 重载接通（UI 加勾选框） |
| v2.10 | immediate 按钮复用 staged_phase1（4 帧延迟） |
| v2.11 | （错误地）整体禁用 mesh；用户纠正后撤回 |
| v2.12 | mesh 复用，immediate 强制 mesh=false |
| v2.15 | mesh reload 保持启用；删除 `MESH_RELOAD_ENABLED` 死开关，mesh 仅走 staged 路径 |
| **v2.13** | on_draw_ui pcall 包裹 + 删 STAGED 跨线程指示器 |
| **v2.14** | 删除 immediate 按钮, swap 仅保留 staged 单路径(4 帧窗口对 mdf 只是"没崩过", 非已证安全); 清理无 UI 入口的 S1/S2 探针死代码(dump_type_members/do_create_only/do_bind_one, -149 行); 其余无入口诊断函数(do_swap/path_probe/scene 探针等 ~450 行)保留, 头部已标注仅供回溯 |
| **v2.15** | 死代码总清理(2314→1598 行, 净 -716): 删除上一行标注的"仅供回溯"函数(swap_textures/full_rebind/do_swap/do_full_rebind/do_reload_scene + scene/probe/path_probe 探针)及其专用 helper(dump_mesh/MOD_SLOT_HINTS/null_texture_holder/res_name/try_prop/seq_get/to_table_seq/args_str/fmt_val)。live 路径不变: UI→staged_phase1/do_restore, PrepareRendering→run_apply_queue/run_staged |

---

## 附录 B：关键代码片段索引

| 片段 | 行号区域 | 说明 |
| --- | --- | --- |
| `alias_path` | ~561 | 大小写翻转 |
| `is_covered` + `COVERED_LIST` | ~640-690 | 安全闸门 |
| `make_holder` | ~706 | create_resource + add_ref + Holder 五步 |
| `player_meshes` / `player_parts` | ~1075 / ~1045 | 玩家 Body/Head/Hair mesh 收集 |
| `mesh_inventory` / `discover_slots` | ~1262 / ~1240 | 枚举材质/贴图槽位 |
| `backup_mesh` | ~1305 | 备份原始 holder 供 restore |
| `do_restore` | ~1350 | 按 backup 还原（含 setMesh） |
| `build_bind_jobs` | ~1460 | 按 opts 收集 texture/material/mesh job |
| `staged_phase1` | ~1490 | phase1：创建 + 保活 |
| `run_staged` | ~1530 | phase2：等 N 帧后绑定 |
| `request_apply` + `run_apply_queue` | ~1390-1415 | UI 入队 → 主线程执行 |
| `on_draw_ui` | ~1580 | UI（v2.13 起 pcall 包裹） |

> 行号为 v2.15 清理后的近似值（死代码删除后整体上移）。v2.15 已删除的
> `swap_textures` / `full_rebind` 不再列出。