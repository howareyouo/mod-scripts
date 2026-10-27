"""HTTP 服务：托管 mod_dup_checker/ 下的前端资源 + JSON 接口。"""

from __future__ import annotations

import json
import os
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import DEFAULT_JOBS, WEB_DIR
from .paths import long_path
from .scanner import REGISTRY

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


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


def read_web_text(real_path):
    with open(real_path, "r", encoding="utf-8") as f:
        return f.read()


def render_page(html):
    """把线程数下拉框的选项填进 HTML 占位符。"""
    options = []
    for n in (1, 2, 4, 6, 8, 12, 16, 24, 32):
        sel = " selected" if n == DEFAULT_JOBS else ""
        options.append('<option value="%d"%s>%d</option>' % (n, sel, n))
    return html.replace("__JOBS_OPTIONS__", "".join(options))


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
    server_version = "ModDupChecker/1.0"

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
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # -- GET -------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            index = os.path.join(WEB_DIR, "index.html")
            try:
                html = read_web_text(index)
            except OSError as exc:
                self._send(500, ("缺少前端文件：%s（%s）" % (index, exc.strerror or exc)).encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            self._send(200, render_page(html).encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        asset = web_path(path)
        if asset is not None:
            try:
                with open(asset, "rb") as f:
                    body = f.read()
            except OSError as exc:
                self._json({"error": "读取前端文件失败：%s（%s）" % (asset, exc.strerror or exc)}, 500)
                return
            ctype = MIME_TYPES.get(os.path.splitext(asset)[1].lower(), "application/octet-stream")
            self._send(200, body, ctype)
            return
        if path == "/api/capabilities":
            self._json({"browse": tk_available(), "default_jobs": DEFAULT_JOBS})
            return
        if path == "/api/browse":
            if not tk_available():
                self._json({"error": "当前环境不可用（缺少 tkinter），请手动输入目录。"}, 501)
                return
            box = {}

            def work():
                try:
                    box["path"] = ask_directory()
                except Exception as exc:  # noqa: BLE001
                    box["error"] = str(exc)

            thread = threading.Thread(target=work, name="browse", daemon=True)
            thread.start()
            thread.join(600)
            if "error" in box:
                self._json({"error": "打开选择目录窗口失败：%s" % box["error"]}, 500)
            elif "path" not in box:
                self._json({"error": "选择目录窗口已关闭或超时。"}, 504)
            else:
                self._json({"path": box["path"]})
            return
        if path == "/api/status":
            job = REGISTRY.get((query.get("job") or [None])[0])
            if job is None:
                self._json({"error": "找不到该扫描任务，请重新开始扫描。"}, 404)
                return
            self._json(job.status())
            return
        if path == "/api/result":
            job = REGISTRY.get((query.get("job") or [None])[0])
            if job is None:
                self._json({"error": "找不到该扫描任务，请重新开始扫描。"}, 404)
                return
            self._json(job.result())
            return

        self._json({"error": "未知接口：%s" % path}, 404)

    # -- POST ------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_json()

        if path == "/api/scan":
            roots = data.get("roots")
            if not isinstance(roots, list):
                self._json({"error": "roots 必须是字符串数组。"}, 400)
                return
            roots = [r for r in roots if isinstance(r, str) and r.strip()]
            if not roots:
                self._json({"error": "请输入至少一个 mod 集合目录。"}, 400)
                return
            jobs = data.get("jobs")
            if jobs is not None and not isinstance(jobs, int):
                jobs = None
            job = REGISTRY.start(roots, jobs)
            if job is None:
                self._json({"error": "已有扫描任务在进行中，请先取消或等待完成。"}, 409)
                return
            self._json({"job_id": job.id})
            return

        if path == "/api/cancel":
            job_id = data.get("job_id")
            job = REGISTRY.get(job_id)
            if job is None:
                self._json({"error": "找不到该扫描任务。"}, 404)
                return
            if job.finished:
                self._json({"ok": False, "error": "该任务已经结束。"}, 200)
                return
            job.cancel()
            self._json({"ok": True})
            return

        if path == "/api/reveal":
            target = data.get("path")
            if not isinstance(target, str) or not target.strip():
                self._json({"error": "缺少 path 参数。"}, 400)
                return
            target = target.strip()
            if not os.path.exists(long_path(target)):
                self._json({"error": "路径不存在：%s" % target}, 404)
                return
            try:
                if os.path.isdir(long_path(target)):
                    os.startfile(target)  # noqa: S606 - 本地工具，打开资源管理器
                else:
                    import subprocess
                    subprocess.Popen('explorer /select,"%s"' % target, shell=False)
            except Exception as exc:  # noqa: BLE001
                self._json({"error": "打开资源管理器失败：%s" % exc}, 500)
                return
            self._json({"ok": True})
            return

        self._json({"error": "未知接口：%s" % path}, 404)


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
