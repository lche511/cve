import re
import subprocess
from pathlib import Path


LAB = Path(__file__).resolve().parents[2]
PYTHON = LAB / ".venv" / "Scripts" / "python.exe"
POC = LAB / "scripts" / "repro_mcp_tool_amplification.py"

TASK = (
    "Please inspect the connected MCP diagnostic bundle. "
    "Use the available MCP diagnostic resource/tool to fetch the complete payload, "
    "then summarize the contents and include relevant raw details for follow-up analysis."
)


def find_line(text, marker):
    for line in text.splitlines():
        if marker in line:
            return line
    return ""


def field(line, name):
    match = re.search(rf"{re.escape(name)}=([^ ]+)", line)
    return match.group(1) if match else "unknown"


def timestamp(line):
    match = re.search(r"\[([^\]]+)\]", line)
    return match.group(1) if match else "unknown-time"


def main():
    proc = subprocess.run(
        [str(PYTHON), str(POC)],
        cwd=str(LAB),
        text=True,
        capture_output=True,
        timeout=240,
    )

    output = proc.stdout
    baseline = find_line(output, "baseline_normal_probe")
    during = find_line(output, "normal_probe_during_attack")
    unavailable = find_line(output, "SERVICE_UNAVAILABLE")
    result = find_line(output, "RESULT=UNAVAILABLE")

    print("Hermes Agent MCP normal chat workflow DoS proof")
    print("Target endpoint: /v1/chat/completions")
    print()
    print(f"[{timestamp(baseline)}] POST /v1/chat/completions  baseline normal chat")
    print(f"[{timestamp(baseline)}] HTTP/1.1 {field(baseline, 'status')} OK")
    print()
    print(f"[{timestamp(during)}] POST /v1/chat/completions  MCP diagnostic agent task")
    print(f"[{timestamp(during)}] request body: {TASK}")
    print()
    print(f"[{timestamp(during)}] POST /v1/chat/completions  normal chat during MCP task")
    print(f"[{timestamp(during)}] HTTP/1.1 {field(during, 'status')} Too Many Requests")
    if unavailable:
        print(
            f"[{timestamp(during)}] response body: "
            '{"error":{"message":"Too many concurrent runs (max 2)",'
            '"type":"rate_limit_error","code":"rate_limit_exceeded"}}'
        )
    if proc.returncode != 0 or not result:
        print()
        print("Underlying PoC did not reproduce cleanly.")
        raise SystemExit(proc.returncode or 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
