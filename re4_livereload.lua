-- re4_livereload.lua v2.0
-- RE4R charactermodel/material/texture[hot-reload]verifyscript (REFramework autorun)
--
-- ===========================================================================
-- v1.3 tested (2026-09-11 15:25, main Ada cha200) -- twoconclusion
-- ===========================================================================
-- [conclusion 1] sdk.create_resource(type, path) right[alreadyloadover's path]return's thenis
--          enginecacheinsidethatobject, notiscreateresource. 
--          evidence: 25/25  mesh 's  set_Material allis old==new. 
--            old = current mesh 's  material holder inlayerresourcepointer( 0x10)
--            new = create_resource back res:get_address()
--          twosame REFramework : 
--            Resource::create_holder() = { add_ref(); *(Resource**)(inst+0x10)=this; }
--            get_address() = (uintptr_t)res  ->  and 0x10 place's issameonepointer
--          so old==new is's [cache hit], notis. 
--          => [resource]notto mod newin, mustletcache entry, 
--            orswapone[engineinsidediff]'s pathgoload(path alias). 
--
-- [conclusion 2] set_Material() characterhitcheckerboard(= invalidmaterial/textureunparse's 
--          engineplaceholder). causeisthisscript's  bug: 
--            a) get_MaterialNum() righthas mesh return 0 -> texture slotoneallenumerate, 
--               thusonly set_Material, afterno setMaterialTexture . 
--            b) holder 's fallbackconstructpath .ctor(): 
--               res:create_holder(tn) want tn is via.ResourceHolder 's subkind, 
--               via.render.MeshMaterialResourceHolder maynot -> return nil
--               -> toconstruct sdk.create_instance(tn, true)  call(".ctor()")
--               -> holder basekindfielduninitialized -> upgothenisinvalidmaterial -> checkerboard. 
--               (EMV-Engine 's is .ctor() 's , v1.3 . )
--          => v2.0 defaultnot set_Material, onlytake setMaterialTexture; 
--            and holder constructtwoall .ctor(), stillwill[take]hitlog. 
--
-- important: checkerboardonlyisrunwhenstate, nowrite-to-disk. game / resume. 
-- ===========================================================================
--
-- v2.0 right v1.3 's change
-- ---------------------------------------------------------------------------
-- [safe] set_Material defaultoff(material=false). defaultonlyrebindtexture -- thisis
--        mod realpos's , alsoisrisklow's orig. 
-- [safe] new[3. Restore original]: modifyfront mesh 's original material/mesh
--        holder andtexture slot's original holder all BACKUP( add_ref ), 
--        issuerestore, notgame. 
-- [probe] new[1b. PROBE accessors]:  material 's has's 
--        originalreturn/wrongallhit(not), useconfirmmaterialcounttobottom
--        from API  -- not. 
-- [fix] materialcountmany + probe(mat index 0..15 
--        getMaterialTextureNum/getMaterialResourceNum/getMaterialName), 
--        fully's  get_MaterialNum(). 
-- [fix] setMaterialTexture after getMaterialTexture(m,t) , 
--        sub[bindok]/[callwrongslotchange]-- thisis API is
--        real's 's . 
-- [fix] holder constructtwoall .ctor(); realtake's is. 
-- [fix] current_scene() rightorigsingletonuse sdk.find_type_definition(typename) 
--        type(v1.3 use obj:get_type_definition() rightorigsingletonnotto -> whole
--        static callsilentreturn nil -> scene 0, nothiterror). 
--
-- output: reframework/data/re4_livereload.txt
-- recommended(buttonbetween 1 s): 
--   1. Scan player        -> seecannotcanenumeratetexture slot
--   1b. PROBE accessors   -> seecounttobottom
--   2. Swap textures only -> onlyswaptexture, notmaterialset (safe)
--   3. Restore original   -> restore
--   4. Full rebind        -> materialset+textureswap (hasrisk, issue 3 restore/)
--
-- mustusemain(Ada cha200 thatkindhastextureoverride's scene). Mercenaries(cha8xx) down
-- Corset Noir 's changenotoverridetexture, doallnotwillhaschange. 

-- ===========================================================================
-- v2.4 -- twotimes c0000005 crash's  + fix (2026-09-11 16:11 )
-- ===========================================================================
-- []click[2. Swap TEXTURES only]-> logshow 38/38 all BIND-OK
--         -> 1ms backdead -> reframework_crash.dmp
--
-- [threelog's root]
--   1) Lua log : 38 ok, 247 failed, 169 skipped | NEW=38 SAME=0 bindinvalid=0
--   2) RFW log : setMaterialTexture becall 38 times -> [38 times]becaught's exception
--                 (call == exception, onenot),  1 timesuncaught AV
--                 RIP at re4.exe, RCX=0(null pointer), RBX=0x7342BDC0
--                  0x7342BDC0 posisusealiascreate's  cha000_hair_nrmr resource
--   3) pluginlog: aliaspathindeedbe Poison + Redirect to mod file
--                 => path//overridelist[allisright's ], notisthatlayer's issue
--
-- [conclusion]bad's notis"what to bind"alsonotis"is the path correct", is"bind from which thread/time". 
--   weat re.on_draw_ui insidedirectresource. thatcallbackrunat[render thread, 
--   ImGui during]-- render threadischaractermaterial, weatitdownswapresource. 
--   aliaswillcreateresource, enginewantdoload/upload, bebig, 
--   render threadthususeunready's  -> RCX=0 . 
--   (v2.0 so: itnoalias, create_resource returnsameonecacheobject, 
--    upgoetcswap, almost -- alsothennotto mod newin. )
--
-- [authoritative]4 alreadyswap MOD (Ada FieldAgent / Infiltrator /
--   ProtocolAmber / WinterOps) allresourcechangeat
--       re.on_application_entry("PrepareRendering", fn)
--   -- thatis[main thread, thisrenderstartbefore]'s whenclick. 
--   they's  re.on_draw_ui onlyscreen, re.on_frame only, allnotresource. 
--   webeforeonealluseright. 
--
-- [this]
--   * hasresourcechange[enqueue], atmain thread PrepareRendering insidedequeueexecute
--     (request_apply / run_apply_queue). 
--   * newsubphasebind STAGED: onlycreateresourcelive -> main threadetc N 
--     (letengineresourceload/upload) -> bind. bottom"new resource not ready"'s . 
--   * OPT.alias default false(BUTTON 2 nowissafeline). 
--   * new S1(onlycreatenotbind, risk) / S2(onlyoneslot) / S3(subphasebind)
--     threelevelladder, levelallcanissue. 
--   * new dump via.render.TextureResource member -- we dump overthis
--     type, hasitcanhasno"ready/size"thiskind's . 
--
-- []REFramework will REMethodDefinition::invoke inside's  SEH exception
--   return -- so Lua sideseeto's  call=true / after==new allmayisfake's . 
--   origcallhasnoreal, is reframework_log.txt inside
--   'Exception thrown in REMethodDefinition::invoke for <method name>'. 
-- ===========================================================================
-- v2.14 -- remove the "immediate" swap button (single staged path only)
-- ===========================================================================
-- [why] the button was labeled "textures-only" but copied OPT wholesale and only
--   forced mesh=false: with "reload mdf" checked it ALSO rebound
--   MeshMaterialResource after just 4 frames. Two problems:
--     a) name/behavior mismatch (mdf included; docs claimed textures-only);
--     b) 4 frames is only "never crashed yet" for mdf, not a proven-safe window
--        (mesh at 4 frames is a proven crash: bind ok -> next frame c0000005).
-- [change] exactly ONE swap path remains: the staged button (default 90 frames),
--   honoring the mdf/mesh checkboxes above it.
-- [cleanup] S1 (create-only) / S2 (bind-one) probes, dump_type_members and the
--   ONE slot table removed -- lost their UI entries when the probe buttons were
--   dropped in earlier versions; confirmed unreferenced by grep before deletion.
-- [carry-over v2.13] on_draw_ui pcall-wrapped; cross-thread STAGED indicator removed.
-- ===========================================================================
-- v2.15 -- remove all remaining dead/probe code (dead-code sweep, net -716 lines)
-- ===========================================================================
-- Every function below had NO UI entry and NO caller on the live path; all were
-- confirmed unreferenced by grep before deletion:
--   swap_textures / full_rebind / do_swap / do_full_rebind / do_reload_scene,
--   probe_accessors / call_static / current_scene / scene_meshes / scan_player /
--   probe_player / path_probe,
--   plus helpers only they used: dump_mesh (+MOD_SLOT_HINTS), null_texture_holder
--   (+NULL_TEX/null_holder_cache), res_name, try_prop, seq_get + to_table_seq,
--   args_str, fmt_val.
-- Live path (unchanged): UI -> staged_phase1 / do_restore;
--   PrepareRendering -> run_apply_queue / run_staged.
-- ===========================================================================

local unpack_fn = table.unpack or unpack

-- ===========================================================================
-- log
-- ===========================================================================

local LOG = {}
local MAX_LOG = 12000

local function ts()
    local ok, s = pcall(os.date, "%H:%M:%S")
    if ok and type(s) == "string" then
        return s
    end
    return "??:??:??"
end

local function logf(fmt, ...)
    local n = select("#", ...)
    local args = { ... }
    local ok, msg = pcall(string.format, fmt, unpack_fn(args, 1, n))
    if not ok then
        msg = tostring(fmt)
    end
    LOG[#LOG + 1] = "[" .. ts() .. "] " .. tostring(msg)
    if #LOG > MAX_LOG then
        table.remove(LOG, 1)
    end
    log.info("[live_reload] " .. tostring(msg))
end

local function flush()
    local ok = pcall(fs.write, "re4_livereload.txt", table.concat(LOG, "\n") .. "\n")
    if not ok then
        log.warn("[live_reload] could not write re4_livereload.txt")
    end
end

-- ===========================================================================
-- value
-- ===========================================================================

local function addr_str(v)
    if type(v) == "number" then
        return string.format("0x%X", v)
    end
    return tostring(v)
end

local obj_type_name

-- ===========================================================================
-- usecall: oneobjectup's member, mayis managed method, origgeneratefunction, or static method
-- ===========================================================================

obj_type_name = function(o)
    if o == nil then
        return nil
    end
    local ok, td = pcall(function()
        return o:get_type_definition()
    end)
    if not ok or td == nil then
        return nil
    end
    local ok2, n = pcall(function()
        return td:get_full_name()
    end)
    if ok2 and type(n) == "string" then
        return n
    end
    local ok3, n2 = pcall(function()
        return td:get_name()
    end)
    if ok3 and type(n2) == "string" then
        return n2
    end
    return nil
end

local function type_def_of(o)
    local tn = obj_type_name(o)
    if tn == nil then
        return nil
    end
    local ok, td = pcall(sdk.find_type_definition, tn)
    if ok then
        return td
    end
    return nil
end

local call_any

-- raw_call(obj, name, ...) -> ok(boolean), value, err(string|nil)
-- noterror: callfail's cause, thisisthiswrong's . 
local function raw_call(obj, name, ...)
    if obj == nil then
        return false, nil, "obj is nil"
    end
    local n = select("#", ...)
    local args = { ... }
    local errs = {}

    -- 1) REFramework managed 
    local ok1, r1 = pcall(function()
        return obj:call(name, unpack_fn(args, 1, n))
    end)
    if ok1 then
        if r1 ~= nil then
            return true, r1, nil
        end
        errs[#errs + 1] = ":call -> nil"
    else
        local e1 = tostring(r1)
        errs[#errs + 1] = ":call -> " .. e1
        -- Bail out immediately on an argument-count mismatch. Retrying with the
        -- other strategies below re-invokes the SAME invalid native call and can
        -- trigger an uncaught c0000005 (this was the button-2 hard-crash root
        -- cause: getMaterialTextureNum(m) on an out-of-range material index).
        if e1:find("number of arguments", 1, true)
           or e1:find("Invalid number of arguments", 1, true) then
            return false, nil, table.concat(errs, " | ")
        end
    end

    -- 2) orig usertype memberfunction
    local okf, fn = pcall(function()
        return obj[name]
    end)
    if okf and type(fn) == "function" then
        local ok2, r2 = pcall(function()
            return fn(obj, unpack_fn(args, 1, n))
        end)
        if ok2 then
            if r2 ~= nil then
                return true, r2, nil
            end
            errs[#errs + 1] = "usertype -> nil"
        else
            errs[#errs + 1] = "usertype -> " .. tostring(r2)
        end
    end

    -- 3) typemethod ( static)
    local td = type_def_of(obj)
    if td ~= nil then
        local okm, m = pcall(function()
            return td:get_method(name)
        end)
        if okm and m ~= nil then
            local ok3, r3 = pcall(function()
                return m:call(obj, unpack_fn(args, 1, n))
            end)
            if ok3 and r3 ~= nil then
                return true, r3, nil
            end
            local ok4, r4 = pcall(function()
                return m:call(unpack_fn(args, 1, n))
            end)
            if ok4 and r4 ~= nil then
                return true, r4, nil
            end
            errs[#errs + 1] = "td:get_method -> nil"
        else
            errs[#errs + 1] = "td:get_method missing"
        end

        -- 4) sdk.call_native_func (nowhenname)
        if n == 0 then
            local ok5, r5 = pcall(sdk.call_native_func, obj, td, name .. "()")
            if ok5 and r5 ~= nil then
                return true, r5, nil
            end
        end
    else
        errs[#errs + 1] = "no type definition"
    end

    return false, nil, table.concat(errs, " | ")
end

-- silent: onlywantvalue, notwanterrorinfo
call_any = function(obj, name, ...)
    local ok, v = raw_call(obj, name, ...)
    if ok then
        return v
    end
    return nil
end

local function try_num(obj, name, ...)
    local v = call_any(obj, name, ...)
    if type(v) == "number" then
        return v
    end
    return nil
end

local function try_str(obj, name, ...)
    local v = call_any(obj, name, ...)
    if type(v) == "string" then
        return v
    end
    return nil
end

-- ===========================================================================
-- Holder / resourceaddress
-- ===========================================================================

local function holder_path(holder)
    if holder == nil then
        return nil
    end
    local s = call_any(holder, "ToString()") or call_any(holder, "ToString")
    if type(s) == "string" then
        local p = s:match("^.+%[@?(.+)%]")
        if p ~= nil and p ~= "" then
            return p:lower()
        end
    end
    local rp = try_str(holder, "get_ResourcePath") or try_str(holder, "get_Path")
    if rp ~= nil and rp ~= "" then
        return rp:lower()
    end
    return nil
end

-- Holder inlayerrealrealresourceobjectaddress. 
-- REFramework  Resource::create_holder():
--     *(sdk::Resource**)((uintptr_t)instance + sizeof(::REManagedObject)) = this;
-- sizeof(REManagedObject) == 0x10, so 0x10 's thenisresourceobjectpointerthis, 
-- and res:get_address() same -- twocandirect. 
local function holder_inner_addr(holder)
    if holder == nil then
        return nil
    end
    local ok, v = pcall(function()
        return holder:read_qword(0x10)
    end)
    if ok and type(v) == "number" then
        return v
    end
    return nil
end

local function resource_addr(o)
    if o == nil then
        return nil
    end
    local tn = obj_type_name(o)
    if tn ~= nil and tn:find("Holder", 1, true) then
        local inner = holder_inner_addr(o)
        if inner ~= nil then
            return inner
        end
    end
    local ok, a = pcall(function()
        return o:get_address()
    end)
    if ok and type(a) == "number" then
        return a
    end
    return nil
end

local STATS = { new = 0, same = 0, unknown = 0, bind_fail = 0 }

local function reset_stats()
    STATS.new, STATS.same, STATS.unknown, STATS.bind_fail = 0, 0, 0, 0
end

local function stats_line()
    return string.format("NEW(!=slot)=%d SAME(=slot)=%d bind-invalid=%d addr-incomparable=%d",
        STATS.new, STATS.same, STATS.bind_fail, STATS.unknown)
end

-- only[create 's returnisnotisetccurrentslot]: old = origresourceaddress, new = createresourceaddress. 
-- [note 2026-09-11 thismarknotetc[inisnew]]-- upalready: 
-- RESTORE back 2 times create return's stillis 1 timesthatobject, script NEW. 
-- hasalias(alias)whenitalso NEW(timesallisnew), sorealpos's onlyhastwo: 
--   1) pluginlog reframework/re4_mod_manager.log atwhenbetweenin's  Redirect: line
--      (>0 isreal; =0 thenispureincache)
--   2) swapobviousdiff's texturebackscreenhasnochange
local function verdict_of(old_a, new_a)
    if type(old_a) == "number" and type(new_a) == "number" then
        if old_a == new_a then
            STATS.same = STATS.same + 1
            return "SAME(=current slot)"
        end
        STATS.new = STATS.new + 1
        return "NEW(!=current slot)"
    end
    STATS.unknown = STATS.unknown + 1
    return "?(addr incomparable)"
end

-- [bindisnotisreal's ]: after = bindback's slotresourceaddress
local function verdict_bind(new_a, after_a)
    if type(new_a) == "number" and type(after_a) == "number" then
        if new_a == after_a then
            return "BIND-OK"
        end
        STATS.bind_fail = STATS.bind_fail + 1
        return "BIND-NO-EFFECT(slot unchanged!)"
    end
    return "BIND-UNKNOWN"
end

-- read a resource object's identity/name via any available accessor
-- ===========================================================================
-- resourcecreate
-- ===========================================================================

local live_refs = {}

local function keep(obj)
    live_refs[#live_refs + 1] = obj
    if #live_refs > 6000 then
        table.remove(live_refs, 1)
    end
end

--  holder typerealtake's constructpath(onlyhittimes, )
local HOLDER_PATH_USED = {}

local OPT = {
    mesh = false,       -- few(mesh)
    material = false,   -- materialset(mdf2) -- v1.3 thisstepdanger, default
    textures = true,    -- texture
    filter = "",
    official_holder = false, -- false = MOD ecosystemstandard(create_instance + .ctor()), recommended
    only_character = true,   -- onlymove Body/Head/Hair, not/UI/that mesh
    alias = true,            -- path alias ON by default; no UI toggle. case-variant path
                             -- forces a cache miss so the current mod is re-read on every swap.
                             -- never disable: alias=off makes swap walk the original path = restore.
    bind_delay = 90,         -- STAGED subphasebind: createresourcebacketcmanyfew
}

-- ===========================================================================
-- path alias(epoch casechange)-- 2026-09-11 PATH PROBE tested
--
-- engine's resourcecache[pathcharstring]do; plugin's  mod indexmatchiscasenot's 
-- (src/util.cpp normalize_into enginepath + tolower backindex). 
-- soonlycasethensamewhentotwo: 
--   * engineside: fromover's path -> cache miss -> realdisk-read -> mod newin
--   * pluginside: tolower backhit mod  -> CreateFileW beto mod file
--
-- PATH PROBE tested(main Ada cha200, A_base = 0x71A289D0): 
--   F2_mixed_case   _CHAINSAW/character/...  -> DIFF(resource) + pluginloghas Redirect  [OK]
--   B_file_prefix   __p4r1__xxx.tex          -> resource, pluginlogis "serving
--                                               placeholder"(index, onlycanforplaceholdertexture)[X]
--   C_dir_segment   sameup                       [X]
--   D/E back -> nil; F big -> nil; H tailempty -> nil
-- => onlyhas[purecasechange]overenginecache, canhit mod index. 
--
-- epoch useatpath's  ASCII up, times reload +1 -> 65536 timesmayuse
-- samealiaspath. name(backone '.' after)notand, movetoback. 
-- ===========================================================================
local ALIAS_BITS = 16
local EPOCH = 1

local function alias_safe_positions(p)
    local last_dot = nil
    for i = #p, 1, -1 do
        if p:sub(i, i) == "." then
            last_dot = i
            break
        end
    end
    local stop = (last_dot ~= nil) and (last_dot - 1) or #p

    local idx = {}
    for i = 1, stop do
        if p:sub(i, i):match("[a-z]") then
            idx[#idx + 1] = i
            if #idx >= ALIAS_BITS then
                break
            end
        end
    end
    return idx
end

-- returnaliaspath, be's . epoch >= 1  != origpath. 
local function alias_path(p, epoch)
    local idx = alias_safe_positions(p)
    if #idx == 0 then
        return nil, 0 -- no mutable ASCII character: caller must skip aliasing
    end

    local n = epoch % (2 ^ #idx)
    if n <= 0 then
        n = 1
    end

    local chars = {}
    for i = 1, #p do
        chars[i] = p:sub(i, i)
    end

    local flipped = 0
    for b = 1, #idx do
        if math.floor(n / 2 ^ (b - 1)) % 2 == 1 then
            local pos = idx[b]
            chars[pos] = string.upper(chars[pos])
            flipped = flipped + 1
        end
    end

    local out = table.concat(chars)
    if out == p then
        return alias_path(p, epoch + 1) -- tonot, fallbacksamepath
    end
    return out, flipped
end

-- ===========================================================================
-- mod overridelist: alias + rebind's **front**
--
-- [2026-09-11 crash, thisblockbefore]
--
-- aliasonlycase -> enginenewcharstring hash ->  cache miss. aftersubtwo: 
--   * path**at**plugin mod indexinside -> plugin hash(should_poison_hash onlyat
--     index->find_view hitfileavailablewhenreturn true) -> engine pak miss -> 
--     loose file -> CreateFileW betoyou's  mod file -> torealresource [OK]
--   * path**notat**indexinside -> pluginnot -> engine[aliasstring's original hash]
--     pak -> miss -> pluginalsonowillfallback -> create_resource returnone
--     [object nil empty]'s resource ->  setMaterialTexture thenisuse
--     null pointer -> c0000005 crash [X]
--
-- testedevidence(threelog): 
--   reframework_log.txt   setMaterialTexture exception 2 times(be REFramework , 
--                         so Lua side pcall seeto's isok -- log), 
--                          3 timesdirect c0000005 + RCX: 0 null pointer +  dump
--   re4_mod_manager.log   15:56:48 crashin Poison=1972 Redirect=87
--                         placeholder=0  <- aliaspathbealsotoplaceholder
--   re4_livereload.txt    crashfrontbacktimes SWAP: 207 ok / 194 failed
--   's pathallnotatindexinside: systems/rendering/*, _chainsaw/vfx/recordsystem/
--   .../rendertargetlist_rtt_l_00.rtex(rendermark!), re_engine_library/.../
--   tex_capcom_vector_water_0011_array_nrmr.tex(group!)
--
-- => alias + rebind**onlyright mod realposoverride's path**do. itsskip. 
--
-- [list's ]Lua sidenottopluginindex: 
--   * REFramework 's  io.open beat reframework/data
--     (src/mods/bindings/FS.cpp get_correct_subpath:  ".." andrightpath), 
--     sonotto reframework/re4_mod_manager.log
--   * fs.glob 's rootdironlycanis <gamedir>/natives, reframework/data, 
--     reframework/autorun, notto E:\RE4 Mods
--   sohere**fast**, ispluginlog's  "Poison (mod):" line --
--   thatlineonlyatindexhitfileavailablewhenhit, etcplugin[thisI]. 
--
-- [listover](swap mod / new mod newfile)
--   regenerate: node G:/re4-mod-manager/.workbuddy/tmp/gen_covered.js
--   -> override .workbuddy/tmp/covered_keys.lua ->  .tex/.mdf2/.mesh thatline
--   C++ not-existthisissue: plugindirect's index (index->find_view(key) != nil), 
--   thisposisaliasdowntoplugin's . 
-- ===========================================================================
local COVERED_LIST = {
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00.mdf2",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00.mesh",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_beltholster_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_beltholster_atoc.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_beltholster_nrmr.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_heels_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_heels_atoc.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_heels_nrmr.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_props_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_props_atoc.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_props_nrmr.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_skin_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_skin_atoc.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_skin_mskm.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_skin_nrmr.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_upperbody_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_upperbody_atoc.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_upperbody_mskm.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_upperbody_nrmr.tex",
    "_chainsaw/character/ch/cha2/cha200/00/cha200_00_wetmask_msk1.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10.mdf2",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10.mesh",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_cm1_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_cm2_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_eye_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_eyelash_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_face_albd.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_face_atoc.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_face_nrmr.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_wm1_nrmr.tex",
    "_chainsaw/character/ch/cha2/cha200/10/cha200_10_wm2_nrmr.tex",
    "_chainsaw/character/ch/cha2/cha200/20/cha200_20.mdf2",
    "_chainsaw/character/ch/cha2/cha200/20/cha200_20.mesh",
    "_chainsaw/character/ch/cha2/cha200/wiwilz/cha000_hair_albs.tex",
    "_chainsaw/character/ch/cha2/cha200/wiwilz/cha000_hair_atoc.tex",
    "_chainsaw/character/ch/cha2/cha200/wiwilz/cha000_hair_nrmr.tex",
    "_chainsaw/ui/dlc/dlc_1003/tex/cs_ui4040_thumb_1003_iam.tex",
    "_chainsaw/ui/ui4000/tex/cs_ui4010_thumb_iam.tex",
    "_chainsaw/ui/ui4000/tex/cs_ui4040_thumb_iam.tex",
    "_mercenaries/character/ch/cha8/cha800/00/cha800_00.mesh",
    "_mercenaries/character/ch/cha8/cha800/20/cha800_20.mdf2",
    "_mercenaries/character/ch/cha8/cha800/20/cha800_20.mesh",
}

local COVERED = {}
for _, k in ipairs(COVERED_LIST) do
    COVERED[k] = true
end
local COVERED_N = #COVERED_LIST

-- listalsonot's type(pure, ). 
-- rtex = rendermark; _array = group; systems/ re_engine_library/ = engineinternal. 
-- texturetheseslotupalreadyovertimes. 
local function is_never_touch(p)
    return p:sub(1, 8) == "systems/"
        or p:sub(1, 18) == "re_engine_library/"
        or p:find("%.rtex$") ~= nil
        or p:find("rendertargetlist", 1, true) ~= nil
        or p:find("_array", 1, true) ~= nil
end

-- thispathis[mod real's override]-- onlyatreturn true whenallowaliasandrebind
local function is_covered(path)
    if type(path) ~= "string" or path == "" then
        return false
    end
    local k = path:lower()
    k = k:match("^.+%[@?(.+)%]") or k
    if is_never_touch(k) then
        return false
    end
    return COVERED[k] == true
end

-- make_holder(raw_type, path, no_alias) -> holder, err, res_addr, built_by, used_path
local function make_holder(raw_type, path, no_alias)
    if type(path) ~= "string" or path == "" then
        return nil, "path is empty"
    end
    path = path:lower()
    path = path:match("^.+%[@?(.+)%]") or path

    local used_path = path
    local alias_on = (not no_alias) and OPT.alias and is_covered(path)
    if alias_on then
        local aliased = alias_path(path, EPOCH)
        if aliased ~= nil then
            used_path = aliased
        else
            alias_on = false
            logf("  [alias] skipped (no mutable ASCII character): '%s'", path)
        end
    end

    local ok, res = pcall(sdk.create_resource, raw_type, used_path)
    if not ok or res == nil then
        return nil, "create_resource('" .. raw_type .. "','" .. used_path .. "') -> nil"
    end

    -- match gamescript MOD ecosystem Utils.createResource(): the resource returned by
    -- create_resource is only fully registered/valid AFTER add_ref(). Without this the
    -- engine silently rejects the holder in setMaterialTexture and the mesh keeps the
    -- original texture -> "bind-invalid" / after==old for every slot.
    local okr, r2 = pcall(function()
        return res:add_ref()
    end)
    if okr and r2 ~= nil then
        res = r2
    end

    local res_addr = nil
    local oka, a = pcall(function()
        return res:get_address()
    end)
    if oka then
        res_addr = a
    end

    if type(res_addr) ~= "number" then
        return nil, "res:get_address() is not a number"
    end

    local holder = nil
    local built_by = nil

    --  A(default): gamescript MOD ecosystem's standard, verbatimcopy
    -- Ada ProtocolAmber / FieldAgent / WinterOps 's  Utils.createResource(): 
    --
    --   local new_resource = sdk.create_resource(type, path)
    --   new_resource = new_resource and new_resource:add_ref()
    --   local addr = new_resource:get_address()
    --   local holder = sdk.create_instance(type .. "Holder", true)
    --   holder = holder:add_ref()          --  add_ref
    --   holder:call(".ctor()")             --  ctor  <- v1.3 's thenisthisstep
    --   holder:write_qword(0x10, addr)
    --
    -- noteit**notuse** res:create_holder(): thatwant holder typeis
    -- via.ResourceHolder 's subkind, via.render.*Holder maynot -> return nil. 
    if not (official_holder == true) then
        local oki, h2 = pcall(sdk.create_instance, raw_type .. "Holder", true)
        if oki and h2 ~= nil then
            local okr = pcall(function()
                h2:add_ref()
            end)
            local okc, cerr = pcall(function()
                h2:call(".ctor()")
            end)
            local okw, werr = pcall(function()
                h2:write_qword(0x10, res_addr)
            end)
            -- validgate(copy MOD 's  is_valid_obj): mustisobject, use > 0
            local refc = nil
            pcall(function()
                refc = h2:read_qword(0x8)
            end)
            local valid_ok, valid_value = pcall(sdk.is_managed_object, h2)
            local valid = valid_ok and valid_value == true
            if okc and okw and valid then
                holder = h2
                built_by = string.format("create_instance(+add_ref=%s,.ctor=%s,refc=%s)",
                    tostring(okr), tostring(okc), tostring(refc))
            else
                logf("    holder construct failed %sHolder: valid=%s ctor=%s(%s) write=%s(%s)",
                    raw_type, tostring(valid), tostring(okc), tostring(cerr),
                    tostring(okw), tostring(werr))
            end
        end
    end

    --  B(): REFramework . want holder typeis via.ResourceHolder
    -- 's subkind, return nil -- thismustcansee, notsilentfallback. 
    if holder == nil and official_holder == true then
        local okh, h = pcall(function()
            return res:create_holder(raw_type .. "Holder")
        end)
        if okh and h ~= nil then
            holder = h
            built_by = "res:create_holder"
        else
            logf("    res:create_holder(%sHolder) returned nil -> type is not a via.ResourceHolder subclass",
                raw_type)
            return nil, "official factory returned nil (and official_holder on, trying manual construct)"
        end
    end

    if holder == nil then
        return nil, "holder construct failed (" .. raw_type .. "Holder)"
    end

    pcall(function()
        return holder:add_ref()
    end)

    local seen_key = raw_type .. "|" .. tostring(built_by)
    if not HOLDER_PATH_USED[seen_key] then
        HOLDER_PATH_USED[seen_key] = true
        logf("  [holder] %sHolder construct path = %s", raw_type, tostring(built_by)
            .. (OPT.official_holder and "" or " (official_holder=off)"))
    end

    keep(res)
    keep(holder)

    return holder, nil, res_addr, built_by, used_path, res
end

-- ===========================================================================
-- group / 
-- ===========================================================================
--
-- REFramework 's  WrappedArrayContainer_* is sol2 usertype, bindis
--   size/get_size/empty/clear + meta index(0 base) + meta pairs
-- C# List<T> is get_Count/get_Item. twoallwant. 

local function seq_count(seq)
    if seq == nil then
        return nil
    end
    if type(seq) == "table" then
        return #seq
    end
    local c = try_num(seq, "get_size") or try_num(seq, "get_Count") or try_num(seq, "get_count")
    if type(c) == "number" then
        return c
    end
    local ok, n = pcall(function()
        return #seq
    end)
    if ok and type(n) == "number" then
        return n
    end
    local ok2, v = pcall(function()
        return seq.size
    end)
    if ok2 and type(v) == "number" then
        return v
    end
    local ok3, v3 = pcall(function()
        return seq.Count
    end)
    if ok3 and type(v3) == "number" then
        return v3
    end
    return nil
end

-- ===========================================================================
-- character Mesh 
-- ===========================================================================

local MESH_TYPEOF = nil

local function mesh_typeof()
    if MESH_TYPEOF == nil then
        local ok, t = pcall(sdk.typeof, "via.render.Mesh")
        if ok then
            MESH_TYPEOF = t or false
        else
            MESH_TYPEOF = false
        end
    end
    if MESH_TYPEOF == false then
        return nil
    end
    return MESH_TYPEOF
end

local function walk_transforms(root, out, depth)
    if root == nil or depth > 8 or #out > 4000 then
        return
    end
    out[#out + 1] = root
    local child = call_any(root, "get_Child")
    while child ~= nil do
        walk_transforms(child, out, depth + 1)
        child = call_any(child, "get_Next")
    end
end

local function mesh_on_gameobject(go)
    if go == nil then
        return nil
    end
    local t = mesh_typeof()
    if t == nil then
        return nil
    end
    local m = call_any(go, "getComponent(System.Type)", t)
    if m == nil then
        m = call_any(go, "getComponent", t)
    end
    return m
end

--  GameObject namerecursivesubclick. 
-- verbatimcopygamescript MOD ecosystem's  Utils.findChild():  get_Transform():get_Child(), 
-- hitthenreturn get_GameObject(), recursivesubclick,  get_Next() take. 
local function find_child(gameObject, childName)
    if gameObject == nil then
        return nil
    end
    local xform = call_any(gameObject, "get_Transform")
    if xform == nil then
        return nil
    end
    local firstChild = call_any(xform, "get_Child")
    if firstChild == nil then
        return nil
    end

    local function go_name(x)
        local g = call_any(x, "get_GameObject")
        if g == nil then
            return nil, nil
        end
        return try_str(g, "get_Name"), g
    end

    local n0, g0 = go_name(firstChild)
    if n0 == childName then
        return g0
    end

    local found = find_child(g0, childName)
    if found ~= nil then
        return found
    end

    local nextChild = call_any(firstChild, "get_Next")
    while nextChild ~= nil do
        local n, g = go_name(nextChild)
        if n == childName then
            return g
        end
        found = find_child(g, childName)
        if found ~= nil then
            return found
        end
        nextChild = call_any(nextChild, "get_Next")
    end
    return nil
end

-- character's  Body / Head / Hair three GameObject down's  player_parts()

local function player_gameobjects()
    local out = {}
    local candidates = {
        { "CharacterManager", "getPlayerContextRef" },
        { "PlayerManager", "getPlayerContextRef" },
    }

    local ctx = nil
    local via = nil
    for i = 1, #candidates do
        local name = candidates[i][1]
        local singleton = nil
        pcall(function()
            singleton = sdk.get_managed_singleton(sdk.game_namespace(name))
                or sdk.get_managed_singleton("app." .. name)
        end)
        if singleton ~= nil then
            local c = call_any(singleton, candidates[i][2])
            if c ~= nil then
                via = name
                ctx = c
                break
            end
        end
    end

    if ctx == nil then
        return out, nil
    end

    local body = call_any(ctx, "get_BodyGameObject")
    local head = call_any(ctx, "get_HeadGameObject")
    if body ~= nil then
        out[#out + 1] = { label = "Body", go = body }
    end
    if head ~= nil then
        out[#out + 1] = { label = "Head", go = head }
    end
    return out, "app." .. tostring(via) .. ":getPlayerContextRef"
end

-- character's  Body / Head / Hair three GameObject. 
-- pathfullycopy MOD 's  Utils.findGameAda(): 
--   getPlayerContextRef() -> get_BodyGameObject() -> findChild("cha200_00"/"cha200_10"/hair)
-- cha200_00/10 isplayerup's name; hair has hair / Hair / cha200_20 three. 
local function player_parts()
    local roots, how = player_gameobjects()
    if #roots == 0 then
        return nil, how
    end

    local contextGO = nil
    for i = 1, #roots do
        if roots[i].label == "Body" then
            contextGO = roots[i].go
            break
        end
    end
    if contextGO == nil then
        contextGO = roots[1].go
    end

    local parts = {
        Body = find_child(contextGO, "cha200_00"),
        Head = find_child(contextGO, "cha200_10"),
    }
    parts.Hair = find_child(contextGO, "hair")
        or find_child(contextGO, "Hair")
        or find_child(contextGO, "cha200_20")

    if parts.Body == nil and parts.Head == nil then
        return nil, how
    end
    return parts, how
end

local function player_meshes()
    local meshes = {}
    local seen = {}
    local roots, how = player_gameobjects()
    if #roots == 0 then
        logf("player: cannot get PlayerManager/CharacterManager player context -- still in main menu?")
        return meshes
    end
    logf("player context via %s", tostring(how))

    local function push(m, label)
        if m == nil then
            return
        end
        local a = nil
        local ok, v = pcall(function()
            return m:get_address()
        end)
        if ok then
            a = v
        end
        local key = (type(a) == "number") and a or tostring(m)
        if seen[key] then
            return
        end
        seen[key] = true
        meshes[#meshes + 1] = { mesh = m, label = label }
    end

    -- onlymovecharacterthis: name Body/Head/Hair, notiswhole Transform sub
    -- (will/UI/that 25  mesh , alsowantrisk)
    if OPT.only_character then
        local parts = player_parts()
        if parts == nil then
            logf("player: findChild did not locate cha200_00/cha200_10 -> fall back to whole-tree traversal")
        else
            local names = { "Body", "Head", "Hair" }
            for i = 1, #names do
                local nm = names[i]
                local go = parts[nm]
                if go ~= nil then
                    local label = nm .. "/" .. (try_str(go, "get_Name") or nm)
                    push(mesh_on_gameobject(go), label)
                    local xform = call_any(go, "get_Transform")
                    if xform ~= nil then
                        local subs = {}
                        walk_transforms(xform, subs, 0)
                        for j = 2, #subs do
                            local sgo = call_any(subs[j], "get_GameObject")
                            local sm = mesh_on_gameobject(sgo)
                            if sm ~= nil then
                                push(sm, label .. ">" .. (try_str(sgo, "get_Name") or "?"))
                            end
                        end
                    end
                end
            end
            logf("player: only_character -> %d mesh(es) (Body/Head/Hair and subtree)", #meshes)
            return meshes
        end
    end

    for i = 1, #roots do
        local go = roots[i].go
        local label = roots[i].label

        local xform = call_any(go, "get_Transform")
        if xform ~= nil then
            local transforms = {}
            walk_transforms(xform, transforms, 0)
            for j = 1, #transforms do
                local tgo = call_any(transforms[j], "get_GameObject")
                local m = mesh_on_gameobject(tgo)
                if m ~= nil then
                    local n = try_str(tgo, "get_Name") or "?"
                    push(m, label .. "/" .. n)
                end
            end
        end

        push(mesh_on_gameobject(go), label .. "(self)")
    end
    return meshes
end

-- ===========================================================================
-- click / slot
-- ===========================================================================

-- materialcount: many + probe. 
-- v1.3 's is get_MaterialNum()  0, soherenot API. 
local function material_count(mesh)
    local cands = {}
    local note = {}
    local MAX_MAT = 32  -- safety cap: a garbage/huge count must never drive the enumeration loop

    local ok, v, err = raw_call(mesh, "get_MaterialNum")
    note[#note + 1] = string.format("get_MaterialNum=%s(%s)", tostring(v), ok and "ok" or tostring(err))
    if ok and type(v) == "number" and v > 0 then
        if v > MAX_MAT then
            note[#note + 1] = string.format("[capped %d]", MAX_MAT)
            v = MAX_MAT
        end
        cands[#cands + 1] = v
    end

    local c = seq_count(call_any(mesh, "get_Materials"))
    note[#note + 1] = "get_Materials#" .. tostring(c)
    if type(c) == "number" and c > 0 then
        cands[#cands + 1] = c
    end

    c = seq_count(call_any(mesh, "get_MaterialNames"))
    note[#note + 1] = "get_MaterialNames#" .. tostring(c)
    if type(c) == "number" and c > 0 then
        cands[#cands + 1] = c
    end

    -- probe:  m stillcan, thenmeans m exist
    local probed = 0
    for m = 0, 15 do
        local n = try_num(mesh, "getMaterialTextureNum", m)
        local r = try_num(mesh, "getMaterialResourceNum", m)
        local nm = try_str(mesh, "getMaterialName", m)
        local hit = false
        if type(n) == "number" and n > 0 then hit = true end
        if type(r) == "number" and r > 0 then hit = true end
        if nm ~= nil and nm ~= "" then hit = true end
        if hit and (m + 1) > probed then
            probed = m + 1
        end
    end
    note[#note + 1] = "probe=" .. tostring(probed)
    if probed > 0 then
        cands[#cands + 1] = probed
    end

    local best = 0
    for i = 1, #cands do
        if cands[i] > best then
            best = cands[i]
        end
    end
    if best > MAX_MAT then
        best = MAX_MAT
    end
    return best, table.concat(note, " ")
end

-- texture slot: use (m,t) indexemptybetween, and EMV 's  setMaterialTexture(mat,tex,holder) right. 
-- SAFETY: cap material/texture counts and STOP enumerating a mesh as soon as a slot
-- accessor rejects the index (out-of-range / arg-mismatch). Previously an unbounded
-- loop over a garbage mat_num called getMaterialTextureNum(m) on invalid indices,
-- which threw "Invalid number of arguments" and triggered an uncaught c0000005
-- (the button-2 hard crash). Path is taken from the holder (parameterless, safe)
-- instead of getMaterialResourceName(m,t), which also throws on hostile meshes.
local function discover_slots(mesh, mat_num)
    local slots = {}
    local MAX_MAT = 32
    local MAX_TEX = 128
    mat_num = (type(mat_num) == "number" and mat_num or 0)
    if mat_num > MAX_MAT then
        mat_num = MAX_MAT
    end
    for m = 0, mat_num - 1 do
        -- validate this material index before drilling in
        local tex_num = try_num(mesh, "getMaterialTextureNum", m)
        if tex_num == nil then
            -- accessor rejected this index (OOB / arg mismatch) -> no more valid materials
            break
        end
        if type(tex_num) ~= "number" or tex_num <= 0 then
            -- material has no textures; keep going (next material may have some)
        elseif tex_num >= MAX_TEX then
            -- garbage count; skip this material instead of looping forever
        else
            for t = 0, tex_num - 1 do
                local h = call_any(mesh, "getMaterialTexture", m, t)
                local p = holder_path(h)  -- safe, parameterless; avoids getMaterialResourceName
                if p == nil or p == "" then
                    p = try_str(mesh, "getMaterialResourceName", m, t)
                    if p ~= nil then
                        p = p:lower()
                        p = p:match("^.+%[@?(.+)%]") or p
                    end
                end
                local fp = holder_path(h)
                if p == nil or p == "" then
                    p = fp
                end
                slots[#slots + 1] = {
                    m = m,
                    t = t,
                    name = try_str(mesh, "getMaterialTextureName", m, t),
                    mat_name = try_str(mesh, "getMaterialName", m),
                    path = p,
                    holder_path = fp,
                    holder = h,
                    inner = resource_addr(h),
                    tex_index = try_num(mesh, "getMaterialTextureIndex", m, t),
                }
            end
        end
    end
    return slots
end

local function mesh_inventory(mesh)
    local inv = { slots = {}, mdf_path = nil, mesh_path = nil }

    inv.mat_num, inv.count_note = material_count(mesh)

    local mdf_holder = call_any(mesh, "get_Material")
    local mesh_holder = call_any(mesh, "getMesh")
    inv.mdf_holder = mdf_holder
    inv.mesh_holder = mesh_holder
    inv.mdf_path = holder_path(mdf_holder)
    inv.mesh_path = holder_path(mesh_holder)
    inv.mdf_inner = resource_addr(mdf_holder)
    inv.mesh_inner = resource_addr(mesh_holder)
    inv.material_ready = call_any(mesh, "get_MaterialReady")
    inv.mesh_ready = call_any(mesh, "get_MeshReady")

    inv.slots = discover_slots(mesh, inv.mat_num)
    return inv
end

local function slot_path(s)
    return s.path
end

-- ===========================================================================
-- BACKUP / restore
-- ===========================================================================

local BACKUP = {}
local BACKUP_ORDER = {}
local request_apply

local function mesh_key(mesh)
    local ok, a = pcall(function()
        return mesh:get_address()
    end)
    if ok and type(a) == "number" then
        return a
    end
    return tostring(mesh)
end

local function pin(o)
    if o == nil then
        return
    end
    pcall(function()
        return o:add_ref()
    end)
    keep(o)
end

-- onlyat[timestothis mesh]whenoriginalstate, afterhasmodifyall. 
local function backup_mesh(mesh, inv, label)
    local k = mesh_key(mesh)
    local b = BACKUP[k]
    if b == nil then
        b = { mesh = mesh, label = label, slots = {}, first = true }
        BACKUP[k] = b
        BACKUP_ORDER[#BACKUP_ORDER + 1] = k
        pin(mesh)
    end
    if b.material_holder == nil then
        b.material_holder = inv.mdf_holder
        b.material_path = inv.mdf_path
        pin(b.material_holder)
    end
    if b.mesh_holder == nil then
        b.mesh_holder = inv.mesh_holder
        b.mesh_path = inv.mesh_path
        pin(b.mesh_holder)
    end
    for i = 1, #inv.slots do
        local s = inv.slots[i]
        local sk = tostring(s.m) .. "," .. tostring(s.t)
        if b.slots[sk] == nil then
            b.slots[sk] = s.holder
            pin(s.holder)
        end
    end
    return b
end

local function do_restore()
    logf("=== RESTORE original bindings ===")
    local n, slots_total = 0, 0
    for i = 1, #BACKUP_ORDER do
        local b = BACKUP[BACKUP_ORDER[i]]
        if b ~= nil then
            local okm, em = true, nil
            local okmesh, emesh = true, nil
            -- A first scan can legitimately have no material/mesh holder; never
            -- call a void setter with nil during restore.
            if b.material_holder ~= nil then
                okm, _, em = raw_call(b.mesh, "set_Material", b.material_holder)
            end
            if b.mesh_holder ~= nil then
                okmesh, _, emesh = raw_call(b.mesh, "setMesh", b.mesh_holder)
            end
            local sl = 0
            for sk, h in pairs(b.slots) do
                local m, t = sk:match("^(%-?%d+),(%-?%d+)$")
                if m ~= nil and h ~= nil then
                    raw_call(b.mesh, "setMaterialTexture", tonumber(m), tonumber(t), h)
                    sl = sl + 1
                end
            end
            logf("  restore '%s': set_Material=%s%s setMesh=%s%s slots=%d (path=%s)",
                b.label, tostring(okm), okm and "" or ("!" .. tostring(em)),
                tostring(okmesh), okmesh and "" or ("!" .. tostring(emesh)), sl,
                tostring(b.material_path))
            n = n + 1
            slots_total = slots_total + sl
        end
    end
    logf("=== RESTORE done: %d mesh(es), %d slot(s) ===", n, slots_total)
    flush()
end

-- ===========================================================================
-- [v2.4 fix]resourcechangeatmain thread's  PrepareRendering insideexecute
--
-- twotimes c0000005 's sameroot: weat re.on_draw_ui(render thread, ImGui during)
-- direct setMaterialTexture, render threadischaractermaterial -- . 
-- 4 alreadyswap MOD alluse re.on_application_entry("PrepareRendering", fn), 
-- thatismain thread, thisrenderstartbefore's whenclick. filehead v2.4 block's wholeevidence. 
--
-- => UI buttononly[enqueue], changeat PrepareRendering 's hookinsidedequeueexecute. 
-- ===========================================================================

local APPLY_QUEUE = {}
local APPLY_BUSY = false

request_apply = function(tag, fn)
    APPLY_QUEUE[#APPLY_QUEUE + 1] = { tag = tag, fn = fn }
    logf("[queue] '%s' enqueued -> will run in [main-thread PrepareRendering]", tag)
    logf("         (if crash, log stops at the 'start' line above -- that means the action itself is unsafe)")
    flush()
    return true
end

local function run_apply_queue()
    if APPLY_BUSY or #APPLY_QUEUE == 0 then
        return
    end
    APPLY_BUSY = true
    local job = table.remove(APPLY_QUEUE, 1)
    logf("=== [main-thread PrepareRendering] START '%s' ===", job.tag)
    flush()
    local ok, err = pcall(job.fn)
    if not ok then
        logf("!!! [main-thread] '%s' error: %s", job.tag, tostring(err))
    end
    logf("=== [main-thread PrepareRendering] '%s' DONE ===", job.tag)
    flush()
    APPLY_BUSY = false
end

-- ---------------------------------------------------------------------------
-- subphasebind STAGED: onlycreateresource( add_ref/live) -> main threadetc N 
-- (forenginewhenbetweendoloadand GPU upload) -> bind. 
-- thisis"new resource touched by render thread before it is ready"'s . 
-- ---------------------------------------------------------------------------
local STAGED = nil

-- set"slots that should be bound": only mod override, notatnotlistinside's 
-- mesh (geometry) reload via setMesh is controlled by the UI checkbox below.
-- It must use the staged path: short windows (e.g. the old 4-frame "immediate"
-- path, removed in v2.14) are not safe for MeshResource because the bind may
-- succeed before the resource is fully ready, causing a crash on the next frame.
-- Texture (.tex), material (.mdf2), and mesh (.mesh) reload all share the staged
-- pipeline; mesh reload is opt-in via "reload mesh (geometry)".

-- mesh (geometry) reload via setMesh needs a longer ready window than textures:
-- the staged path (default 90 frames) is the only supported path. Mesh is therefore
-- only ever processed by the staged button.

local function build_bind_jobs(opts)
    local jobs = {}
    local meshes = player_meshes()
    for i = 1, #meshes do
        local inv = mesh_inventory(meshes[i].mesh)
        backup_mesh(meshes[i].mesh, inv, meshes[i].label)
        -- mdf2 material file reload: replace the whole material resource on the mesh
        if opts.material and type(inv.mdf_path) == "string" and inv.mdf_path ~= ""
            and is_covered(inv.mdf_path) then
            jobs[#jobs + 1] = {
                kind = "material", mesh = meshes[i].mesh, path = inv.mdf_path,
                old_inner = inv.mdf_inner, label = meshes[i].label,
            }
        end
        -- mesh geometry reload: replace the whole mesh resource
        if opts.mesh and type(inv.mesh_path) == "string" and inv.mesh_path ~= ""
            and is_covered(inv.mesh_path) then
            jobs[#jobs + 1] = {
                kind = "mesh", mesh = meshes[i].mesh, path = inv.mesh_path,
                old_inner = inv.mesh_inner, label = meshes[i].label,
            }
        end
        for j = 1, #inv.slots do
            local s = inv.slots[j]
            local p = slot_path(s)
            if type(p) == "string" and p ~= ""
                and is_covered(p)
                and (opts.filter == "" or p:find(opts.filter, 1, true)) then
                jobs[#jobs + 1] = {
                    kind = "texture",
                    mesh = meshes[i].mesh, m = s.m, t = s.t, path = p,
                    old_inner = s.inner, label = meshes[i].label,
                }
            end
        end
    end
    return jobs
end

local function staged_phase1(tag, opts)
    if COVERED_N == 0 then
        logf("!! cover list is empty, refusing to run !!")
        flush()
        return
    end
    logf("=== STAGED phase1(%s) epoch=%d alias=%s material=%s mesh=%s filter='%s' holder=%s ===",
        tag, EPOCH, tostring(opts.alias), tostring(opts.material), tostring(opts.mesh),
        tostring(opts.filter), tostring(OPT.official_holder))
    logf("    this phase only creates resources + keeps them alive, [does NOT call setMaterialTexture] (so it cannot crash)")
    local jobs = build_bind_jobs(opts)
    logf("    candidate slots %d (only inside mod cover list)", #jobs)
    local ready = {}
    for i = 1, #jobs do
        local j = jobs[i]
        local rtype = "via.render.TextureResource"
        if j.kind == "material" then
            rtype = "via.render.MeshMaterialResource"
        elseif j.kind == "mesh" then
            rtype = "via.render.MeshResource"
        end
        local holder, err, new_addr = make_holder(rtype, j.path, false)
        if holder == nil then
            logf("    create FAIL [%s] m=%s t=%s '%s': %s", tostring(j.kind), tostring(j.m), tostring(j.t), j.path, tostring(err))
        else
            j.holder = holder
            j.new_addr = new_addr
            ready[#ready + 1] = j
            logf("    create OK   [%s] m=%s t=%s addr=%s '%s'", tostring(j.kind), tostring(j.m), tostring(j.t), addr_str(new_addr), j.path)
        end
    end
    logf("    phase1 done: %d/%d resources created and kept alive", #ready, #jobs)
    flush()
    if #ready == 0 then
        logf("    [!] none created -> phase2 cancelled")
        flush()
        return
    end
    STAGED = { jobs = ready, frames = opts.bind_delay or 90, delay = opts.bind_delay or 90 }
    logf("    -> main thread waits %d frames then auto-binds (do NOT switch area/reload save during this)", opts.bind_delay or 90)
    flush()
end

local function run_staged()
    if STAGED == nil then
        return
    end
    if STAGED.frames > 0 then
        STAGED.frames = STAGED.frames - 1
        return
    end
    local st = STAGED
    STAGED = nil
    logf("=== STAGED phase2: waited %d frames, start binding %d slots ===", st.delay, #st.jobs)
    reset_stats()
    local ok_n, fail_n = 0, 0
    for i = 1, #st.jobs do
        local j = st.jobs[i]
        local alive = false
        pcall(function()
            local v = sdk.is_managed_object(j.mesh)
            alive = (v == true)
        end)
        if not alive then
            logf("    bind [%s] '%s' skipped: mesh invalidated", tostring(j.kind), j.path)
            fail_n = fail_n + 1
        elseif j.kind == "material" then
            local ok, _, cerr = raw_call(j.mesh, "set_Material", j.holder)
            local after = resource_addr(call_any(j.mesh, "get_Material"))
            logf("    bind [material] '%s' call=%s%s new=%s after=%s | %s",
                j.path, tostring(ok), ok and "" or ("!" .. tostring(cerr)),
                addr_str(j.new_addr), addr_str(after), verdict_of(j.old_inner, after))
            if ok then ok_n = ok_n + 1 else fail_n = fail_n + 1 end
        elseif j.kind == "mesh" then
            local ok, _, cerr = raw_call(j.mesh, "setMesh", j.holder)
            local after = resource_addr(call_any(j.mesh, "getMesh"))
            logf("    bind [mesh] '%s' call=%s%s new=%s after=%s | %s",
                j.path, tostring(ok), ok and "" or ("!" .. tostring(cerr)),
                addr_str(j.new_addr), addr_str(after), verdict_of(j.old_inner, after))
            if ok then ok_n = ok_n + 1 else fail_n = fail_n + 1 end
        else
            local ok, _, cerr = raw_call(j.mesh, "setMaterialTexture", j.m, j.t, j.holder)
            local after = resource_addr(call_any(j.mesh, "getMaterialTexture", j.m, j.t))
            logf("    bind [texture] m=%d t=%d '%s' call=%s%s new=%s after=%s | %s",
                j.m, j.t, j.path, tostring(ok), ok and "" or ("!" .. tostring(cerr)),
                addr_str(j.new_addr), addr_str(after), verdict_bind(j.new_addr, after))
            if ok then ok_n = ok_n + 1 else fail_n = fail_n + 1 end
        end
    end
    logf("=== STAGED done: %d ok, %d failed | %s ===", ok_n, fail_n, stats_line())
    logf("    [!] call=true does NOT mean no crash -- must search reframework_log.txt for this time window:")
    logf("      'Exception thrown in REMethodDefinition::invoke for via.render.Mesh.setMaterialTexture'")
    EPOCH = EPOCH + 1
    logf("=== next epoch=%d ===", EPOCH)
    flush()
end

re.on_application_entry("PrepareRendering", function()
    run_apply_queue()
    run_staged()
end)

-- ===========================================================================
-- UI (simplified: only the controls needed to swap / restore mod textures)
-- ===========================================================================

re.on_draw_ui(function()
    -- the whole body is pcall-wrapped: any UI rendering error is logged but does
    -- NOT crash the game (previously a cross-thread race on the STAGED table between
    -- this render-thread handler and the main-thread run_staged corrupted ImGui
    -- state and crashed in igItemSize_Vec2 -- the STAGED indicator was removed too).
    local ok, err = pcall(function()
        imgui.text("RE4 live reload v2.15")
        imgui.text(string.format("alias epoch = %d | mod cover list = %d entries", EPOCH, COVERED_N))

        local ch
        ch, OPT.only_character = imgui.checkbox("only Body/Head/Hair (skip weapons/UI)", OPT.only_character)
        ch, OPT.material = imgui.checkbox("reload mdf (material file)", OPT.material)
        ch, OPT.mesh = imgui.checkbox("reload mesh (geometry)", OPT.mesh)

        imgui.push_item_width(120)
        local _, dv = imgui.input_text("##wf", tostring(OPT.bind_delay or 90))
        imgui.pop_item_width()
        imgui.same_line()
        imgui.text("wait frames")
        if type(dv) == "string" then
            local n = tonumber(dv)
            if n ~= nil and n >= 0 and n <= 1800 then
                OPT.bind_delay = math.floor(n)
            end
        end

        imgui.text("--- swap (runs on main thread, not render thread) ---")
        if imgui.button("Swap textures (staged, recommended)") then
            request_apply("S3 staged phase1", function()
                staged_phase1("staged", OPT)
            end)
        end

        if imgui.button("Restore original bindings") then
            do_restore()
        end

        if imgui.button("Clear log") then
            LOG = {}
            logf("log cleared")
            flush()
        end
    end)
    if not ok then
        log.warn("[live_reload] on_draw_ui error: " .. tostring(err))
    end
end)

logf("=== re4_livereload v2.15 loaded (dead-code sweep: removed swap_textures/full_rebind/probe/scene/path_probe + helpers. exactly one swap path remains -- staged, default 90 frames, honors the mdf/mesh checkboxes. UI stays pcall-wrapped.) ===")
logf("* v2.4 fix: previously all resource changes ran in re.on_draw_ui(render thread/ImGui period),")
logf("  while the render thread was iterating character materials we swapped resources under it -> race -> c0000005.")
logf("  now UI only enqueues, changes run in main-thread PrepareRendering (same timing as the 4 published outfit MODs).")
logf("* tested fact: setMaterialTexture was called 38 times -> threw 38 exceptions swallowed by REFramework;")
logf("  then 1ms later render-thread AV, RBX = the cha000_hair_nrmr resource just created via alias.")
logf("  => binding an alias-created resource inside on_draw_ui = guaranteed crash.")
logf("* binding path (v2.15): staged binding only -- create first -> main thread waits N frames -> then bind (dead probes removed)")
logf("* criteria (do NOT just look at call=true / NEW label -- REFramework swallows exceptions then returns normally):")
logf("  1) does reframework_log.txt have 'Exception thrown ... setMaterialTexture' in this window")
logf("  2) re4_mod_manager.log Redirect: lines >0 this window = real disk read")
logf("  3) does the screen change accordingly")
logf("if screen has issues: press 3.Restore first; if that fails restart game (only runtime state changed, nothing written to disk)")
flush()
