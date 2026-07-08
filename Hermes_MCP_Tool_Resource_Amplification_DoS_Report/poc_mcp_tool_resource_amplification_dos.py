import subprocess
import sys
from pathlib import Path


LAB = Path(__file__).resolve().parents[2]
PYTHON = LAB / ".venv" / "Scripts" / "python.exe"


def run_case(label, script):
    print(f"\n=== {label} ===")
    cmd = [str(PYTHON), str(LAB / "scripts" / script)]
    proc = subprocess.run(cmd, cwd=str(LAB), text=True, capture_output=True, timeout=240)
    for line in proc.stdout.splitlines():
        if (
            "start" in line
            or "registered=" in line
            or "missing_bound" in line
            or "agent_task_sample" in line
            or "baseline_normal_probe" in line
            or "normal_probe_during_attack" in line
            or "SERVICE_UNAVAILABLE" in line
            or "statuses=" in line
            or "returned_bytes=" in line
            or "recovery_probe#1" in line
            or "RESULT=" in line
        ):
            print(line)
    if proc.returncode != 0:
        print(proc.stderr)
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    run_case(
        "MCP discovery/schema amplification",
        "repro_mcp_discovery_schema_amplification.py",
    )
    run_case(
        "MCP resource/tool result amplification",
        "repro_mcp_tool_amplification.py",
    )
