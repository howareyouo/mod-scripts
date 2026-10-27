(function () {
  "use strict";

  var state = { job: null, timer: null, result: null, busy: false, browseOk: false };

  function $(id) { return document.getElementById(id); }

  function fmtBytes(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + " B";
    var units = ["KiB", "MiB", "GiB", "TiB"];
    var v = n / 1024, i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return v.toFixed(2) + " " + units[i];
  }

  function fmtSec(ms) { return (ms / 1000).toFixed(1) + "s"; }

  function api(path, options) {
    return fetch(path, options).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) {
          var msg = (body && body.error) || ("请求失败（HTTP " + r.status + "）");
          throw new Error(msg);
        }
        return body;
      });
    });
  }

  function postJSON(path, data) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {})
    });
  }

  function banner(text, kind) {
    var el = document.createElement("div");
    el.className = "notice" + (kind === "err" ? " err" : "");
    el.textContent = text;
    return el;
  }

  function clearBanners() { $("banners").textContent = ""; }

  function showError(text) {
    clearBanners();
    $("banners").appendChild(banner(text, "err"));
  }

  // ---- 扫描控制 --------------------------------------------------------
  function collectRoots() {
    return $("roots").value.split("\n").map(function (s) {
      return s.trim().replace(/^"(.*)"$/, "$1");
    }).filter(function (s) { return s.length > 0; });
  }

  function startScan() {
    if (state.busy) return;
    var roots = collectRoots();
    if (!roots.length) { showError("请输入至少一个 mod 集合目录（一行一个）。"); return; }
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
    $("progress-panel").hidden = false;
    $("btn-cancel").disabled = false;

    postJSON("/api/scan", {
      roots: roots,
      jobs: parseInt($("jobs").value, 10) || 8
    }).then(function (res) {
      state.job = res.job_id;
      poll();
    }).catch(function (err) {
      state.busy = false;
      $("btn-scan").disabled = false;
      $("btn-cancel").disabled = true;
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
    state.job = null;
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
    $("p-current").textContent = s.current_path || "";
  }

  function finish(status) {
    var cancelled = !!status.cancelled;
    if (status.error) showError(status.error);
    else if (cancelled) { clearBanners(); $("banners").appendChild(banner("扫描已取消：下面的结论可能不完整，未经内容校验的组显示为「疑似重复」。")); }
    loadResult();
  }

  function loadResult() {
    api("/api/result?job=" + encodeURIComponent(state.job || "")).then(function (res) {
      state.result = res;
      resetButtons();
      renderResult(res);
      $("btn-json").disabled = false;
      $("btn-csv").disabled = false;
      $("foot-hint").textContent = "导出不会写入任何 mod 目录。";
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

    var anySuspect = (res.groups || []).some(function (g) { return g.kind === "structure"; });
    if (anySuspect) {
      $("banners").appendChild(banner("结果包含「疑似重复」组：这些组只通过了结构 + 采样校验，内容未经全量校验。"));
    }

    var summary = document.createElement("div");
    summary.className = "panel";
    var line = document.createElement("div");
    line.className = "phase";
    line.textContent = "共 " + stats.mods + " 个 mod · " + (res.groups || []).length + " 组重复 · 可回收 " + fmtBytes(stats.reclaimable_bytes);
    summary.appendChild(line);
    var kv = document.createElement("div");
    kv.className = "kv";
    [
      ["natives 文件数", String(stats.files || 0)],
      ["natives 总字节", fmtBytes(stats.bytes)],
      ["重复 mod 数", String(stats.dup_mods || 0)],
      ["唯一 mod", String(stats.unique || 0)],
      ["空 mod（无 natives 文件）", String(stats.empty || 0)],
      ["耗时", fmtSec(stats.elapsed_ms || 0)]
    ].forEach(function (pair) {
      var d = document.createElement("div");
      d.textContent = pair[0] + "：";
      var b = document.createElement("b");
      b.textContent = pair[1];
      d.appendChild(b);
      kv.appendChild(d);
    });
    summary.appendChild(kv);
    var note = document.createElement("p");
    note.className = "hint";
    note.style.marginTop = "12px";
    note.textContent = "「文件数 / 大小 / 可回收空间」只统计 natives/ 下的文件；modinfo.ini、截图等不参与比较。组内默认保留第一个，其余仅标记为可删除候选，本工具不会删除任何文件。";
    summary.appendChild(note);
    wrap.appendChild(summary);

    (res.groups || []).forEach(function (g) { wrap.appendChild(renderGroup(g)); });

    if (!(res.groups || []).length) {
      var empty = document.createElement("div");
      empty.className = "panel empty";
      empty.textContent = (stats.mods ? "没有发现重复的 mod。" : "没有找到任何 mod：请确认目录下存在「自身含 natives 子目录」的 mod。");
      wrap.appendChild(empty);
    }

    renderEmptyMods(res.empty_mods || []);
    renderWarnings(res.warnings || []);
  }

  function renderGroup(g) {
    var box = document.createElement("div");
    box.className = "group";

    var head = document.createElement("div");
    head.className = "group-head";
    var no = document.createElement("span");
    no.className = "group-no";
    no.textContent = "组 " + g.id;
    head.appendChild(no);

    function tag(text, cls) {
      var s = document.createElement("span");
      s.className = "tag" + (cls ? " " + cls : "");
      s.textContent = text;
      head.appendChild(s);
    }
    tag(g.count + " 个成员");
    tag("单个 " + fmtBytes(g.member_bytes));
    tag("可回收 " + fmtBytes(g.reclaimable_bytes), "reclaim");
    tag("结构签名 " + String(g.structure_sig).slice(0, 8), "sig");
    if (g.kind === "structure") tag("疑似重复（未全量校验）");
    box.appendChild(head);

    g.members.forEach(function (m, i) {
      box.appendChild(renderMember(g, m, i));
    });
    return box;
  }

  function renderMember(g, m, index) {
    var row = document.createElement("div");
    row.className = "member" + (index === 0 ? " keep" : "");

    var radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "keep-" + g.id;
    radio.checked = index === 0;
    radio.title = "选为要保留的那一份";
    row.appendChild(radio);

    var badge = document.createElement("span");
    badge.className = "badge " + (index === 0 ? "keep" : "del");
    badge.textContent = index === 0 ? "保留" : "可删除候选";
    row.appendChild(badge);

    var mid = document.createElement("div");
    mid.style.flex = "1";
    var p = document.createElement("div");
    p.className = "path";
    p.textContent = m.path;
    mid.appendChild(p);
    var meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = m.mod_name + " · " + m.files + " 个文件 · " + fmtBytes(m.bytes);
    mid.appendChild(meta);
    row.appendChild(mid);

    var copy = document.createElement("button");
    copy.className = "small";
    copy.textContent = "复制路径";
    copy.onclick = function () {
      copyText(m.path, copy);
    };
    row.appendChild(copy);

    var open = document.createElement("button");
    open.className = "small";
    open.textContent = "在资源管理器打开";
    open.onclick = function () {
      postJSON("/api/reveal", { path: m.path }).catch(function (err) {
        showError(err.message);
      });
    };
    row.appendChild(open);

    function syncRow() {
      Array.prototype.forEach.call(row.parentNode.children, function (child, i) {
        if (!child.classList.contains("member")) return;
        var on = child.querySelector("input[type=radio]").checked;
        child.classList.toggle("keep", on);
        var b = child.querySelector(".badge");
        b.className = "badge " + (on ? "keep" : "del");
        b.textContent = on ? "保留" : "可删除候选";
      });
    }
    radio.addEventListener("change", syncRow);
    return row;
  }

  function copyText(text, btn) {
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "已复制";
      setTimeout(function () { btn.textContent = old; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () { fallback(); });
    } else {
      fallback();
    }
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { showError("复制失败，请手动选中路径。"); }
      document.body.removeChild(ta);
    }
  }

  function renderEmptyMods(list) {
    var wrap = $("empty-wrap");
    wrap.textContent = "";
    if (!list.length) return;
    var panel = document.createElement("div");
    panel.className = "panel";
    var h = document.createElement("div");
    h.className = "phase";
    h.textContent = "空 mod（natives/ 下一个文件都没有）：" + list.length + " 个";
    panel.appendChild(h);
    list.forEach(function (p) {
      var d = document.createElement("div");
      d.className = "path";
      d.textContent = p;
      panel.appendChild(d);
    });
    wrap.appendChild(panel);
  }

  function renderWarnings(list) {
    var wrap = $("warn-wrap");
    wrap.textContent = "";
    if (!list.length) return;
    var panel = document.createElement("div");
    panel.className = "panel";
    var h = document.createElement("div");
    h.className = "phase";
    h.textContent = "提示 / 警告：" + list.length + " 条";
    panel.appendChild(h);
    var ul = document.createElement("ul");
    ul.className = "warn-list";
    list.forEach(function (w) {
      var li = document.createElement("li");
      li.textContent = w;
      ul.appendChild(li);
    });
    panel.appendChild(ul);
    wrap.appendChild(panel);
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
      g.members.forEach(function (m, i) {
        rows.push([g.id, g.count, g.member_bytes, g.reclaimable_bytes, g.structure_sig,
          i === 0 ? "保留" : "可删除候选", m.path, m.files, m.bytes]);
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

    api("/api/capabilities").then(function (cap) {
      if (cap && cap.browse) {
        var btn = $("btn-browse");
        btn.hidden = false;
        btn.onclick = function () {
          btn.disabled = true;
          api("/api/browse").then(function (res) {
            if (res && res.path) {
              var box = $("roots");
              box.value = box.value.trim() ? box.value.replace(/\s+$/, "") + "\n" + res.path : res.path;
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
