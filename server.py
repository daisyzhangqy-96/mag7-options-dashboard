"""本地服务：静态文件 + /refresh 接口（触发 generate.py）。"""
import json
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
PORT = 8765


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/refresh":
            self.send_error(404)
            return
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "generate.py")],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=180,
                encoding="utf-8",
                errors="replace",
            )
            ok = result.returncode == 0
            payload = {
                "ok": ok,
                "stderr": (result.stderr or "")[-800:] if not ok else "",
            }
            status = 200 if ok else 500
        except Exception as e:
            payload = {"ok": False, "error": str(e)}
            status = 500

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"serving at http://localhost:{PORT}/index.html")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
