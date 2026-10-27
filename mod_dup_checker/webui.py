"""HTTP 服务：托管 web/ 下的前端资源 + JSON 接口。"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import DEFAULT_JOBS, WEB_DIR
from .paths import long_path
from .scanner import REGISTRY
from .trash import recycle, recycle_many

# 批量删除一次最多提交多少个路径；正常规模远小于这个数，纯粹是防御性上限
MAX_BATCH_ITEMS = 5000
# 请求体上限（字节）：超过就分块丢弃，避免一个畸形请求把内存吃满
MAX_BODY_BYTES = 4 * 1024 * 1024
# 声明体量超过这个值的连接直接断开，不做排空（排空等于陪攻击者传完数据）
MAX_REJECT_BYTES = 64 * 1024 * 1024
DRAIN_CHUNK = 64 * 1024
# 单个连接的空闲超时；没有它，慢速连接会一直占着线程
REQUEST_TIMEOUT = 30
# 目录选择窗口最多等多久（用户可能开着窗口去泡咖啡）
BROWSE_TIMEOUT = 600

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

# 路径规范化（realpath 在 Windows 上要逐段 lstat）很贵，一批请求里同一路径会被问很多遍
_REAL_MEMO = {}
_REAL_MEMO_LIMIT = 100000


def _real(path):
    """规范化成可比较的真实路径：绝对、解开重解析点、大小写不敏感。"""
    cached = _REAL_MEMO.get(path)
    if cached is not None:
        return cached
    value = os.path.normcase(os.path.realpath(long_path(os.path.abspath(path))))
    if len(_REAL_MEMO) > _REAL_MEMO_LIMIT:
        _REAL_MEMO.clear()
    _REAL_MEMO[path] = value
    return value


def _under_roots(path, roots):
    """判断 path 是否严格位于某个扫描根目录之下（根目录本身不算）。"""
    target = _real(path)
    for root in roots:
        if target.startswith(_real(root) + os.sep):
            return True
    return False


class ApiError(Exception):
    """接口层的可展示错误：统一由 _dispatch 变成 {"error": ...}。"""

    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def web_path(url_path):
    """把 URL 路径映射到 web/ 下的真实文件；越界、非前端资源或不存在时返回 None。"""
    rel = url_path.lstrip("/") or "index.html"
    parts = rel.split("/")
    if any(p in ("", ".", "..") or "\\" in p or ":" in p for p in parts):
        return None
    base = os.path.realpath(WEB_DIR)
    target = os.path.realpath(os.path.join(base, *parts))
    if not target.startswith(base + os.sep):
        return None
    # 只托管已知的前端扩展名，备份文件之类的杂项一律 404
    if os.path.splitext(target)[1].lower() not in MIME_TYPES:
        return None
    return target if os.path.isfile(target) else None


# -- 删除候选判定 --------------------------------------------------------
def build_delete_index(job):
    """{规范化路径: (所在组, {规范化路径: 原始路径})}。

    一批删除只建一次；否则每个条目都要重扫全部组并对每个成员做 realpath，
    条目数一多就是次数爆炸。
    """
    index = {}
    for group in job.result().get("groups") or []:
        mapping = {}
        for member in group.get("members") or []:
            path = member.get("path")
            if isinstance(path, str):
                mapping[_real(path)] = path
        entry = (group, mapping)
        for key in mapping:
            index[key] = entry
    return index


def pick_deletable(job, target, keep, index=None):
    """确认 target 是本次扫描结果里的「删除候选」，返回要删除的实际路径。"""
    if index is None:
        index = build_delete_index(job)
    want = _real(target)
    entry = index.get(want)
    if entry is None:
        raise ValueError("该路径不在本次扫描结果的重复组里，已拒绝删除。")

    group, mapping = entry
    if group.get("kind") != "content":
        raise ValueError("该组只是「疑似重复」，内容未经全量校验，请人工核对后再删。")
    if len(mapping) < 2:
        raise ValueError("该组只剩一个成员，删掉就没有副本了。")
    keep_want = _real(keep) if keep else None
    if not keep_want or keep_want not in mapping:
        raise ValueError("请先在组内指定要保留的那一份。")
    if keep_want == want:
        raise ValueError("要删的正是组内标为「保留」的那一份。")

    hit = mapping[want]
    if not _under_roots(hit, job.roots):
        raise ValueError("路径不在本次扫描的目录范围内，已拒绝。")
    if not os.path.isdir(long_path(hit)):
        raise ValueError("路径已不存在，可能已被移动或删除。")
    return hit


# -- 目录选择窗口 --------------------------------------------------------
# tkinter 不是线程安全的：两个请求同时 new 一个 Tk root 会把进程带崩
_TK_LOCK = threading.Lock()


def tk_available():
    try:
        import tkinter  # noqa: F401
        from tkinter import filedialog  # noqa: F401
        return True
    except Exception:
        return False


def ask_directory():
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        return filedialog.askdirectory(title="选择 mod 集合目录") or ""
    finally:
        try:
            root.destroy()
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ModDupChecker/1.1"
    timeout = REQUEST_TIMEOUT

    ROUTES_GET = {
        "/api/capabilities": "_get_capabilities",
        "/api/browse": "_get_browse",
        "/api/status": "_get_status",
        "/api/result": "_get_result",
    }
    ROUTES_POST = {
        "/api/scan": "_post_scan",
        "/api/cancel": "_post_cancel",
        "/api/reveal": "_post_reveal",
        "/api/delete": "_post_delete",
        "/api/delete-batch": "_post_delete_batch",
    }

    def log_message(self, fmt, *args):  # 静音，保持控制台干净
        pass

    # -- 基础 ------------------------------------------------------------
    def _send(self, code, body, ctype):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command not in ("HEAD",):
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _drain(self, length):
        """分块丢弃请求体。读不干净就要求断开连接，绝不按声明长度一次性分配。"""
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, DRAIN_CHUNK))
            if not chunk:
                self.close_connection = True
                return False
            remaining -= len(chunk)
        return True

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > MAX_REJECT_BYTES:
            self.close_connection = True
            raise ApiError("请求体过大，已断开连接。", 413)
        if length > MAX_BODY_BYTES:
            # 排空后照样报 413：让客户端能把错误读完，而不是写到一半被 RST
            if not self._drain(length):
                raise ApiError("请求体过大，已断开连接。", 413)
            raise ApiError("请求体过大（上限 %d MiB）。" % (MAX_BODY_BYTES // (1024 * 1024)), 413)
        try:
            raw = self.rfile.read(length)
        except OSError:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _require_str(self, data, key, message):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ApiError(message)
        return value.strip()

    def _job(self, job_id=None):
        job = REGISTRY.get(job_id)
        if job is None:
            raise ApiError("找不到该扫描任务，请重新开始扫描。", 404)
        return job

    def _check_same_origin(self):
        """挡住任意网页对 127.0.0.1 的跨站写入。

        跨站发 application/json 本来要先过 CORS 预检，这里连 Origin 一起校验；
        Content-Type 非 json 的（表单类"简单请求"）直接拒绝。
        """
        origin = self.headers.get("Origin")
        if origin:
            host = (self.headers.get("Host") or "").lower()
            if origin.lower() not in ("http://" + host, "https://" + host):
                raise ApiError("拒绝跨站请求。", 403)
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype and ctype != "application/json":
            raise ApiError("Content-Type 必须是 application/json。", 415)

    # -- 路由 ------------------------------------------------------------
    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if method == "POST":
                self._check_same_origin()
            name = (self.ROUTES_POST if method == "POST" else self.ROUTES_GET).get(path)
            if name is not None:
                getattr(self, name)(parsed)
                return
            if method != "POST":
                asset = web_path(path)
                if asset is not None:
                    self._serve_file(asset)
                    return
            raise ApiError("未知接口：%s" % path, 404)
        except ApiError as exc:
            self._json({"error": str(exc)}, exc.code)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except socket.timeout:
            self.close_connection = True
        except Exception as exc:  # noqa: BLE001 - 单个请求出错不能带崩服务
            try:
                self._json({"error": "服务内部错误：%s" % exc}, 500)
            except Exception:
                pass

    def _serve_file(self, asset):
        try:
            with open(asset, "rb") as f:
                body = f.read()
        except OSError as exc:
            raise ApiError("读取前端文件失败：%s（%s）" % (asset, exc.strerror or exc), 500)
        ctype = MIME_TYPES.get(os.path.splitext(asset)[1].lower(), "application/octet-stream")
        self._send(200, body, ctype)

    # -- GET -------------------------------------------------------------
    def _get_capabilities(self, _parsed):
        self._json({"browse": tk_available(), "default_jobs": DEFAULT_JOBS})

    def _get_browse(self, _parsed):
        if not tk_available():
            raise ApiError("当前环境不可用（缺少 tkinter），请手动输入目录。", 501)
        if not _TK_LOCK.acquire(blocking=False):
            raise ApiError("已经有一个选择目录的窗口打开了，请先处理它。", 409)

        box = {}

        def work():
            try:
                box["path"] = ask_directory()
            except Exception as exc:  # noqa: BLE001
                box["error"] = str(exc)
            finally:
                _TK_LOCK.release()

        thread = threading.Thread(target=work, name="browse", daemon=True)
        thread.start()
        thread.join(BROWSE_TIMEOUT)
        if "error" in box:
            raise ApiError("打开选择目录窗口失败：%s" % box["error"], 500)
        if "path" not in box:
            raise ApiError("选择目录窗口已关闭或超时。", 504)
        self._json({"path": box["path"]})

    def _get_status(self, parsed):
        query = parse_qs(parsed.query)
        self._json(self._job((query.get("job") or [None])[0]).status())

    def _get_result(self, parsed):
        query = parse_qs(parsed.query)
        self._json(self._job((query.get("job") or [None])[0]).result())

    # -- POST ------------------------------------------------------------
    def _post_scan(self, _parsed):
        data = self._read_json()
        roots = data.get("roots")
        if not isinstance(roots, list):
            raise ApiError("roots 必须是字符串数组。")
        roots = [r for r in roots if isinstance(r, str) and r.strip()]
        if not roots:
            raise ApiError("请输入至少一个 mod 集合目录。")
        jobs = data.get("jobs")
        if not isinstance(jobs, int):
            jobs = None
        job = REGISTRY.start(roots, jobs)
        if job is None:
            raise ApiError("已有扫描任务在进行中，请先取消或等待完成。", 409)
        self._json({"job_id": job.id})

    def _post_cancel(self, _parsed):
        job = self._job(self._read_json().get("job_id"))
        if job.finished:
            raise ApiError("该任务已经结束。", 409)
        job.cancel()
        self._json({"ok": True})

    def _post_reveal(self, _parsed):
        target = self._require_str(self._read_json(), "path", "缺少 path 参数。")
        if not os.path.isabs(target):
            raise ApiError("path 必须是绝对路径。")
        if not os.path.exists(long_path(target)):
            raise ApiError("路径不存在：%s" % target, 404)
        try:
            if os.path.isdir(long_path(target)):
                os.startfile(target)  # noqa: S606 - 本地工具，打开资源管理器
            else:
                subprocess.Popen(["explorer", "/select," + target])
        except OSError as exc:
            raise ApiError("打开资源管理器失败：%s" % exc, 500)
        self._json({"ok": True})

    def _post_delete(self, _parsed):
        data = self._read_json()
        job = self._job(data.get("job_id"))
        target = self._require_str(data, "path", "缺少 path 参数。")
        keep = self._require_str(data, "keep", "缺少 keep 参数（组内要保留的那一份）。")
        try:
            doomed = pick_deletable(job, target, keep)
        except ValueError as exc:
            raise ApiError(str(exc))
        try:
            recycle(doomed)
        except OSError as exc:
            raise ApiError("移到回收站失败：%s" % exc, 500)
        self._json({"ok": True, "path": doomed})

    def _post_delete_batch(self, _parsed):
        data = self._read_json()
        job = self._job(data.get("job_id"))
        items = data.get("items")
        if not isinstance(items, list) or not items:
            raise ApiError("items 必须是非空数组。")
        if len(items) > MAX_BATCH_ITEMS:
            raise ApiError("一次最多删除 %d 个，请分批处理。" % MAX_BATCH_ITEMS)

        wanted, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                raise ApiError("items 里的每一项都必须是 {path, keep} 对象。")
            target = self._require_str(item, "path", "items 里缺少 path 参数。")
            keep = self._require_str(item, "keep", "items 里缺少 keep 参数（组内要保留的那一份）。")
            key = _real(target)
            if key in seen:
                continue
            seen.add(key)
            wanted.append((target, keep))

        # 先整批校验，任何一条不合法就直接拒绝，避免删到一半停下
        index = build_delete_index(job)
        plan = []
        for target, keep in wanted:
            try:
                plan.append((target, pick_deletable(job, target, keep, index)))
            except ValueError as exc:
                raise ApiError("%s（%s）" % (exc, target))

        target_of = {doomed: target for target, doomed in plan}
        deleted, failed = recycle_many([doomed for _target, doomed in plan])
        self._json({
            "ok": not failed,
            "deleted": [target_of.get(path, path) for path in deleted],
            "failed": [{"path": target_of.get(path, path), "error": msg} for path, msg in failed],
            "total": len(plan),
        })


class _Server(ThreadingHTTPServer):
    # Windows 上 SO_REUSEADDR 允许两个进程绑同一端口，会让「端口被占用」探测失效
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex(("127.0.0.1", port)) == 0


def serve(args):
    httpd = None
    port = args.port
    for candidate in range(args.port, args.port + 100):
        if port_in_use(candidate):
            continue
        try:
            httpd = _Server(("127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if httpd is None:
        print("无法在 127.0.0.1:%d 附近找到可用端口。" % args.port)
        return 1

    url = "http://127.0.0.1:%d/" % port
    print("mod 重复检测工具已启动：%s" % url, flush=True)
    print("仅比较 natives/ 下的文件；modinfo.ini、截图等不参与。", flush=True)
    print("按 Ctrl+C 退出。", flush=True)
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        httpd.server_close()
    return 0
