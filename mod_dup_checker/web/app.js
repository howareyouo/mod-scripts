(function () {
  "use strict";

  var state = {
    job: null,          // 正在轮询的扫描任务 (取消用)
    resultJob: null,    // 最近一次拿到结果的任务 id (删除用, 轮询结束后仍然有效)
    timer: null,        // 轮询定时器
    result: null,       // 最近一次 /api/result
    keepByGroup: Object.create(null),  // 组 id -> 要保留的路径
    deleted: Object.create(null),      // 已删掉的路径
    rows: Object.create(null),         // 路径 -> 对应的 DOM 行
    busy: false,
    deleting: false
  };

  var ROOTS_KEY = "mod-dup-checker.roots";
  var DEFAULT_TIMEOUT = 15000;   // 普通接口的超时 (毫秒)
  var BROWSE_TIMEOUT = 620000;   // 选择目录窗口：用户可能开着窗口走开一会儿

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  // 输入框内容存进 localStorage：关掉页面再打开还能接着用上次填的目录.
  function loadRoots() {
    try {
      var saved = window.localStorage.getItem(ROOTS_KEY);
      if (saved) $("roots").value = saved;
    } catch (e) { /* 隐私模式或被禁用时忽略 */ }
  }

  function saveRoots() {
    try {
      var text = $("roots").value;
      if (text) window.localStorage.setItem(ROOTS_KEY, text);
      else window.localStorage.removeItem(ROOTS_KEY);
    } catch (e) { /* 同上 */ }
  }

  function fmtBytes(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + " B";
    var units = ["KiB", "MiB", "GiB", "TiB"];
    var v = n / 1024, i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return v.toFixed(2) + " " + units[i];
  }

  function fmtSec(ms) { return (ms / 1000).toFixed(1) + "s"; }

  // 所有请求都带超时：服务端卡住时页面不能无限转圈
  function api(path, options, timeoutMs) {
    var opts = {};
    if (options) {
      for (var k in options) {
        if (Object.prototype.hasOwnProperty.call(options, k)) opts[k] = options[k];
      }
    }
    var ctrl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = null;
    if (ctrl) {
      opts.signal = ctrl.signal;
      timer = setTimeout(function () { ctrl.abort(); }, timeoutMs || DEFAULT_TIMEOUT);
    }
    function stop() {
      if (timer) { clearTimeout(timer); timer = null; }
    }
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) {
          var msg = (body && body.error) || ("请求失败 (HTTP " + r.status + ")");
          throw new Error(msg);
        }
        return body;
      });
    }).then(function (body) {
      stop();
      return body;
    }, function (err) {
      stop();
      if (err && err.name === "AbortError") throw new Error("请求超时：" + path);
      throw err;
    });
  }

  function postJSON(path, data, timeoutMs) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {})
    }, timeoutMs);
  }

  function banner(text, kind) {
    return el("div", "notice" + (kind === "err" ? " err" : ""), text);
  }

  function clearBanners() { $("banners").textContent = ""; }

  // 提示条统一走这里：先清掉旧提示, 再挂一条新的
  function showBanner(text, kind) {
    clearBanners();
    $("banners").appendChild(banner(text, kind));
  }

  function showError(text) { showBanner(text, "err"); }

  // 线程数下拉框由服务端的能力声明决定, 不在 HTML 里写死
  var JOBS_CHOICES = [1, 2, 4, 6, 8, 12, 16, 24, 32];

  function fillJobs(defaultJobs) {
    var sel = $("jobs");
    var def = parseInt(defaultJobs, 10);
    if (!(def > 0)) def = 8;
    var choices = JOBS_CHOICES.slice();
    if (choices.indexOf(def) < 0) {
      choices.push(def);
      choices.sort(function (a, b) { return a - b; });
    }
    sel.textContent = "";
    choices.forEach(function (n) {
      var opt = document.createElement("option");
      opt.value = String(n);
      opt.textContent = String(n);
      sel.appendChild(opt);
    });
    sel.value = String(def);
  }

  // ---- 扫描控制 --------------------------------------------------------
  function collectRoots() {
    return $("roots").value.split("\n").map(function (s) {
      return s.trim().replace(/^"(.*)"$/, "$1");
    }).filter(function (s) { return s.length > 0; });
  }

  function startScan() {
    if (state.busy) return;
    saveRoots();
    var roots = collectRoots();
    if (!roots.length) { showError("请输入至少一个 mod 集合目录 (一行一个)."); return; }
    clearBanners();
    state.busy = true;
    state.result = null;
    $("btn-scan").disabled = true;
    $("btn-json").disabled = true;
    $("btn-csv").disabled = true;
    $("results").textContent = "";
    $("empty-wrap").textContent = "";
    $("warn-wrap").textContent = "";
    $("foot-hint").textContent = "扫描中…";
    $("summary-panel").hidden = false;
    $("progress-body").hidden = false;
    $("result-summary").hidden = true;
    $("btn-cancel").disabled = false;

    postJSON("/api/scan", {
      roots: roots,
      jobs: parseInt($("jobs").value, 10) || 8
    }).then(function (res) {
      state.job = res.job_id;
      state.resultJob = res.job_id;
      poll();
    }).catch(function (err) {
      resetButtons();          // 与 loadResult 失败时同一套收尾
      showError(err.message);
    });
  }

  function cancelScan() {
    if (!state.job) return;
    $("btn-cancel").disabled = true;
    $("foot-hint").textContent = "正在取消…";
    postJSON("/api/cancel", { job_id: state.job }).catch(function (err) {
      showError(err.message);
    });
  }

  function poll() {
    if (!state.job) return;
    api("/api/status?job=" + encodeURIComponent(state.job)).then(function (s) {
      renderProgress(s);
      if (s.done) { finish(s); return; }
      state.timer = setTimeout(poll, 400);
    }).catch(function (err) {
      showError(err.message);
      resetButtons();
    });
  }

  function resetButtons() {
    state.busy = false;
    state.job = null;          // 只清「正在轮询」的标记, resultJob 留着给删除接口用
    $("btn-scan").disabled = false;
    $("btn-cancel").disabled = true;
  }

  function renderProgress(s) {
    $("phase").textContent = s.phase || "扫描中";
    var pct = 0;
    if (s.files_total > 0) pct = Math.min(100, (s.files_done / s.files_total) * 100);
    else if (s.total_mods > 0) pct = Math.min(100, (s.scanned_mods / s.total_mods) * 100);
    $("bar").style.width = pct.toFixed(1) + "%";
    $("p-mods").textContent = (s.scanned_mods || 0) + " / " + (s.total_mods || 0);
    $("p-files").textContent = (s.files_done || 0) + " / " + (s.files_total || 0);
    $("p-bytes").textContent = fmtBytes(s.bytes_read);
    $("p-elapsed").textContent = fmtSec(s.elapsed_ms || 0);
  }

  function finish(status) {
    var cancelled = !!status.cancelled;
    if (status.error) showError(status.error);
    else if (cancelled) showBanner("扫描已取消：下面的结论可能不完整, 未经内容校验的组显示为「疑似重复」.");
    loadResult();
  }

  function loadResult() {
    api("/api/result?job=" + encodeURIComponent(state.job || "")).then(function (res) {
      state.result = res;
      resetButtons();
      renderResult(res);
      $("btn-json").disabled = false;
      $("btn-csv").disabled = false;
      $("foot-hint").textContent = "导出不会写入任何 mod 目录.";
    }).catch(function (err) {
      showError(err.message);
      resetButtons();
    });
  }

  // ---- 渲染结果 --------------------------------------------------------
  function renderResult(res) {
    var wrap = $("results");
    wrap.textContent = "";
    var stats = res.stats || {};
    state.keepByGroup = Object.create(null);
    state.deleted = Object.create(null);
    state.rows = Object.create(null);

    var anySuspect = (res.groups || []).some(function (g) { return g.kind === "structure"; });
    if (anySuspect) {
      $("banners").appendChild(banner("结果包含「疑似重复」组：这些组只通过了结构 + 采样校验, 内容未经全量校验."));
    }

    var summary = $("result-summary");
    summary.textContent = "";
    $("summary-panel").hidden = false;
    $("progress-body").hidden = true;
    summary.hidden = false;
    summary.appendChild(el("div", "phase",
      "共 " + stats.mods + " 个 mod · " + (res.groups || []).length + " 组重复 · 可回收 " + fmtBytes(stats.reclaimable_bytes)));

    var kv = el("div", "kv");
    [
      ["natives 文件数", String(stats.files || 0)],
      ["natives 总字节", fmtBytes(stats.bytes)],
      ["重复 mod 数", String(stats.dup_mods || 0)],
      ["唯一 mod", String(stats.unique || 0)],
      ["空 mod (无 natives 文件)", String(stats.empty || 0)],
      ["耗时", fmtSec(stats.elapsed_ms || 0)]
    ].forEach(function (pair) {
      var d = el("div", null, pair[0] + "：");
      d.appendChild(el("b", null, pair[1]));
      kv.appendChild(d);
    });
    summary.appendChild(kv);

    var actions = el("div", "row");
    var delAll = el("button", "danger");
    delAll.id = "btn-delete-all";
    delAll.onclick = deleteAllDupes;
    actions.appendChild(delAll);
    var delHint = el("span", "hint");
    delHint.id = "delete-all-hint";
    actions.appendChild(delHint);
    summary.appendChild(actions);

    if (!(res.groups || []).length) {
      summary.appendChild(el("div", "empty", stats.mods
        ? "没有发现重复的 mod."
        : "没有找到任何 mod：请确认目录下存在「自身含 natives 子目录」的 mod."));
    }

    (res.groups || []).forEach(function (g) { wrap.appendChild(renderGroup(g)); });

    renderEmptyMods(res.empty_mods || []);
    renderWarnings(res.warnings || []);
    refreshDeleteAll();
  }

  function renderGroup(g) {
    var box = el("div", "group");
    box.setAttribute("data-group", String(g.id));
    box.setAttribute("data-kind", g.kind || "content");

    var head = el("div", "group-head");
    head.appendChild(el("span", "group-no", "组 " + g.id));

    function tag(text, cls) {
      head.appendChild(el("span", "tag" + (cls ? " " + cls : ""), text));
    }
    tag(g.count + " 个成员");
    tag("单个 " + fmtBytes(g.member_bytes));
    tag("可回收 " + fmtBytes(g.reclaimable_bytes), "reclaim");
    tag("结构签名 " + String(g.structure_sig).slice(0, 8), "sig");
    if (g.kind === "structure") tag("疑似重复 (未全量校验)");
    box.appendChild(head);

    // 默认保留第一个成员 (扫描目录顺序靠前、目录层级最浅的那份)
    state.keepByGroup[g.id] = g.members.length ? g.members[0].path : "";
    g.members.forEach(function (m, i) {
      box.appendChild(renderMember(g, box, m, i));
    });
    return box;
  }

  function renderMember(g, box, m, index) {
    var row = el("div", "member" + (index === 0 ? " keep" : ""));
    row.setAttribute("data-path", m.path);
    state.rows[m.path] = row;

    var radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "keep-" + g.id;
    radio.checked = index === 0;
    radio.title = "选为要保留的那一份 (默认选中：扫描目录顺序靠前、目录层级最浅的那份)";
    row.appendChild(radio);
    row.appendChild(el("span", "badge " + (index === 0 ? "keep" : "del"), index === 0 ? "保留" : "删除"));

    var mid = el("div");
    mid.style.flex = "1";
    mid.appendChild(el("div", "path", m.path));
    mid.appendChild(el("div", "meta", m.mod_name + " · " + m.files + " 个文件 · " + fmtBytes(m.bytes)));
    row.appendChild(mid);

    var open = el("button", "small", "在资源管理器打开");
    open.onclick = function () {
      postJSON("/api/reveal", { path: m.path }).catch(function (err) {
        showError(err.message);
      });
    };
    row.appendChild(open);

    var del = el("button", "small danger", "移到回收站");
    if (g.kind !== "content") {
      del.disabled = true;
      del.title = "该组只是「疑似重复」, 内容未经全量校验, 不提供删除";
    } else if (index === 0) {
      del.disabled = true;
      del.title = "保留项不能删；先把另一份选为保留";
    }
    del.onclick = function () { removeMember(g, m, del); };
    row.appendChild(del);

    radio.addEventListener("change", function () {
      if (!radio.checked) return;
      state.keepByGroup[g.id] = m.path;
      syncGroup(g, box);
    });

    // 整行都能点：点在行内任意空白/文字处也算选中这一份
    row.addEventListener("click", function (e) {
      if (row.classList.contains("deleted") || radio.checked) return;
      for (var t = e.target; t && t !== row; t = t.parentNode) {
        var n = t.tagName;
        if (n === "BUTTON" || n === "INPUT" || n === "A") return;
      }
      radio.checked = true;
      state.keepByGroup[g.id] = m.path;
      syncGroup(g, box);
    });
    return row;
  }

  // 组内切换保留项后, 刷新整组的徽章/按钮状态
  function syncGroup(g, box) {
    var keep = state.keepByGroup[g.id] || "";
    g.members.forEach(function (m) {
      var row = state.rows[m.path];
      if (!row || row.classList.contains("deleted")) return;
      var on = m.path === keep;
      row.classList.toggle("keep", on);
      var badge = row.querySelector(".badge");
      if (badge) {
        badge.className = "badge " + (on ? "keep" : "del");
        badge.textContent = on ? "保留" : "删除";
      }
      var btn = row.querySelector("button.danger");
      if (btn && g.kind === "content") btn.disabled = on;
    });
    refreshDeleteAll();
  }

  // 收集「当前没有被标为保留」的成员, 供批量删除使用
  function collectDoomed() {
    var items = [], skipGroups = 0;
    ((state.result && state.result.groups) || []).forEach(function (g) {
      if (g.kind !== "content") { skipGroups++; return; }
      var keep = state.keepByGroup[g.id] || "";
      if (!keep) return;
      g.members.forEach(function (m) {
        if (m.path === keep || state.deleted[m.path]) return;
        items.push({ path: m.path, keep: keep });
      });
    });
    return { items: items, skipGroups: skipGroups };
  }

  function refreshDeleteAll() {
    var btn = $("btn-delete-all"), hint = $("delete-all-hint");
    if (!btn || !hint) return;
    var info = collectDoomed();
    var n = info.items.length;
    btn.textContent = n ? "删除所有重复 mod (" + n + " 个)" : "删除所有重复 mod";
    btn.disabled = n === 0 || state.deleting;
    if (state.deleting) { hint.textContent = "正在移到回收站…"; return; }
    if (!n) { hint.textContent = "没有可删的成员：每组只留「保留」那一份."; return; }
    hint.textContent = "把每组里没标「保留」的 " + n + " 个文件夹移到回收站" +
      (info.skipGroups ? "；另有 " + info.skipGroups + " 组「疑似重复」未全量校验, 会跳过" : "") + ".";
  }

  function markDeleted(path) {
    state.deleted[path] = true;
    var row = state.rows[path];
    if (!row) return;
    row.classList.add("deleted");
    row.classList.remove("keep");
    var radio = row.querySelector("input[type=radio]");
    if (radio) { radio.checked = false; radio.disabled = true; }
    var badge = row.querySelector(".badge");
    if (badge) { badge.className = "badge del"; badge.textContent = "已删除"; }
    var btn = row.querySelector("button.danger");
    if (btn) { btn.disabled = true; btn.title = "已经删掉了"; }
  }

  function deleteAllDupes() {
    if (state.deleting) return;
    var items = collectDoomed().items;
    if (!items.length) { showError("没有可删的成员."); return; }
    if (!state.resultJob) { showError("扫描任务已失效, 请重新扫描后再删."); return; }
    var shown = items.slice(0, 10).map(function (it) { return it.path; }).join("\n");
    if (items.length > 10) shown += "\n… 还有 " + (items.length - 10) + " 个";
    if (!window.confirm("把这 " + items.length + " 个文件夹移到回收站？\n每组里标「保留」的那一份不会动.\n\n" +
      shown + "\n\n它们都可以从回收站还原.")) return;

    state.deleting = true;
    refreshDeleteAll();
    postJSON("/api/delete-batch", {
      job_id: state.resultJob,
      items: items.map(function (it) { return { path: it.path, keep: it.keep }; })
    }, 300000).then(function (res) {
      state.deleting = false;
      var deleted = res.deleted || [], failed = res.failed || [];
      var doneSet = Object.create(null);
      deleted.forEach(function (p) { doneSet[p] = true; });
      items.forEach(function (it) { if (doneSet[it.path]) markDeleted(it.path); });
      showBanner(failed.length
        ? "已移到回收站 " + deleted.length + " 个；" + failed.length +
          " 个失败：" + failed.map(function (f) { return f.path + " (" + f.error + ")"; }).join("；")
        : "已把 " + deleted.length +
          " 个重复 mod 移到回收站 (上面的统计数字未更新, 需要的话重新扫描一次)",
        failed.length ? "err" : "");
      refreshDeleteAll();
    }).catch(function (err) {
      state.deleting = false;
      refreshDeleteAll();
      showError(err.message);
    });
  }

  function removeMember(g, m, btn) {
    var keep = state.keepByGroup[g.id] || "";
    if (!keep) { showError("请先在组内选一份要保留的."); return; }
    if (keep === m.path) { showError("要删的正是组内标为「保留」的那一份."); return; }
    if (!state.resultJob) { showError("扫描任务已失效, 请重新扫描后再删."); return; }
    if (!window.confirm("把这个文件夹移到回收站？\n\n" + m.path + "\n\n它可以从回收站还原.")) return;
    btn.disabled = true;
    postJSON("/api/delete", { job_id: state.resultJob, path: m.path, keep: keep }, 120000).then(function () {
      markDeleted(m.path);
      showBanner("已移到回收站：" + m.path + " (上面的统计数字未更新, 需要的话重新扫描一次)");
      refreshDeleteAll();
    }).catch(function (err) {
      btn.disabled = false;
      showError(err.message);
    });
  }

  // 空 mod 与提示/警告两块面板结构相同：标题行 + 清单 (给了 listCls 才套一层列表)
  function listPanel(wrapId, label, unit, list, listCls) {
    var wrap = $(wrapId);
    wrap.textContent = "";
    if (!list.length) return;
    var panel = el("div", "panel");
    panel.appendChild(el("div", "phase", label + "：" + list.length + " " + unit));
    var box = listCls ? panel.appendChild(el("ul", listCls)) : panel;
    list.forEach(function (item) {
      box.appendChild(listCls ? el("li", null, item) : el("div", "path", item));
    });
    wrap.appendChild(panel);
  }

  function renderEmptyMods(list) {
    listPanel("empty-wrap", "空 mod (natives/ 下一个文件都没有)", "个", list);
  }

  function renderWarnings(list) {
    listPanel("warn-wrap", "提示 / 警告", "条", list, "warn-list");
  }

  // ---- 导出 ------------------------------------------------------------
  function download(name, mime, text) {
    var blob = new Blob([text], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function stamp() {
    var d = new Date();
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "-" + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds());
  }

  function exportJSON() {
    if (!state.result) return;
    download("mod-dup-" + stamp() + ".json", "application/json;charset=utf-8",
      JSON.stringify(state.result, null, 2));
  }

  function csvCell(v) {
    var s = String(v == null ? "" : v);
    if (/[",\r\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function exportCSV() {
    if (!state.result) return;
    var rows = [["组号", "成员数", "单个mod字节", "该组可回收字节", "结构签名", "角色", "mod路径", "文件数", "字节"]];
    (state.result.groups || []).forEach(function (g) {
      var keep = state.keepByGroup[g.id] || "";
      var kept = keep || (g.members[0] && g.members[0].path);
      g.members.forEach(function (m) {
        // 以当前界面上的选择为准 (默认选择是第一个成员)
        var role = kept === m.path ? "保留" : "删除";
        if (state.deleted[m.path]) role = "已删除";
        rows.push([g.id, g.count, g.member_bytes, g.reclaimable_bytes, g.structure_sig,
          role, m.path, m.files, m.bytes]);
      });
    });
    var text = "\ufeff" + rows.map(function (r) { return r.map(csvCell).join(","); }).join("\r\n") + "\r\n";
    download("mod-dup-" + stamp() + ".csv", "text/csv;charset=utf-8", text);
  }

  // ---- 启动 ------------------------------------------------------------
  function init() {
    $("btn-scan").onclick = startScan;
    $("btn-cancel").onclick = cancelScan;
    $("btn-json").onclick = exportJSON;
    $("btn-csv").onclick = exportCSV;

    fillJobs(8);
    loadRoots();
    var saveTimer = null;
    $("roots").addEventListener("input", function () {
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(saveRoots, 300);
    });

    api("/api/capabilities").then(function (cap) {
      if (!cap) return;
      if (cap.default_jobs) fillJobs(cap.default_jobs);
      if (cap.browse) {
        var btn = $("btn-browse");
        btn.hidden = false;
        btn.onclick = function () {
          btn.disabled = true;
          api("/api/browse", null, BROWSE_TIMEOUT).then(function (res) {
            if (res && res.path) {
              var box = $("roots");
              box.value = box.value.trim() ? box.value.replace(/\s+$/, "") + "\n" + res.path : res.path;
              saveRoots();
            }
          }).catch(function (err) {
            showError(err.message);
          }).then(function () { btn.disabled = false; });
        };
      }
    }).catch(function () { /* 忽略：可选增强 */ });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
