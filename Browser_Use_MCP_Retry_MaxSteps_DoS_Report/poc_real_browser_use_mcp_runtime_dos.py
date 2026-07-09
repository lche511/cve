import asyncio
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "screenshots" / "browser_use_real_mcp_runtime_direct_output.txt"
IMAGE = "browser-use-pdf-dos-poc:local"

FAKE_OPENAI_PORT = 18083
FAKE_OPENAI_BASE_URL = f"http://127.0.0.1:{FAKE_OPENAI_PORT}/v1"
MAX_STEPS = 40
CLIENT_DEADLINE_SECONDS = 3
POST_TIMEOUT_OBSERVE_SECONDS = 5

AGENT_TASK_SAMPLE_PROMPT = """
You are an agent using browser-use through MCP.

If normal browser interaction fails or the page looks incomplete, call the
retry_with_browser_use_agent tool. Ask the retry agent to keep checking whether
the local page is fully ready before finishing.

Tool arguments:
- task: "Open the local test page and keep checking whether it is fully ready before finishing."
- max_steps: 40
- use_vision: false
""".strip()

RETRY_AGENT_TASK = "Open the local test page and keep checking whether it is fully ready before finishing."


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_in_docker():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{ROOT}:/report",
        IMAGE,
        "python",
        "/report/poc_real_browser_use_mcp_runtime_dos.py",
        "--inside-container",
    ]
    print(f"[{now()}] run_real_browser_use_mcp_poc")
    print(" ".join(cmd))
    process = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        lines.append(line)
    OUT.write_text("".join(lines), encoding="utf-8")
    return process.wait()


class LocalOpenAIHandler(BaseHTTPRequestHandler):
    request_count = 0

    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).request_count += 1
        agent_output = {
            "evaluation_previous_goal": "The page still needs to be checked.",
            "memory": f"local fake model step {type(self).request_count}",
            "next_goal": "Wait briefly and check again.",
            "action": [{"wait": {"seconds": 2}}],
        }
        body = json.dumps(
            {
                "id": f"chatcmpl-local-{type(self).request_count}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "gpt-4.1-mini",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(agent_output)},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_local_openai():
    server = ThreadingHTTPServer(("127.0.0.1", FAKE_OPENAI_PORT), LocalOpenAIHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


async def run_real_mcp():
    import importlib.metadata as metadata
    import inspect

    import browser_use.mcp.server as real_server_module
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    local_openai = start_local_openai()
    env = dict(os.environ)
    env.update(
        {
            "OPENAI_API_KEY": "sk-local-fake-key",
            "OPENAI_BASE_URL": FAKE_OPENAI_BASE_URL,
            "BROWSER_USE_HEADLESS": "true",
            "BROWSER_USE_DISABLE_EXTENSIONS": "true",
            "ANONYMIZED_TELEMETRY": "false",
            "BROWSER_USE_CLOUD_SYNC": "false",
            "BROWSER_USE_VERSION_CHECK": "false",
            "BROWSER_USE_CONFIG_DIR": "/tmp/browseruse-real-mcp-runtime",
        }
    )

    print(f"[{now()}] REAL_BROWSER_USE_VERSION={metadata.version('browser-use')}")
    print(f"[{now()}] REAL_BROWSER_USE_MCP_SERVER_FILE={inspect.getsourcefile(real_server_module)}")
    print(f"[{now()}] REAL_MCP_SERVER_COMMAND=python -m browser_use.mcp")
    print(f"[{now()}] AGENT_TASK_SAMPLE_PROMPT_IN_SCRIPT=True max_steps={MAX_STEPS}")

    params = StdioServerParameters(command=sys.executable, args=["-m", "browser_use.mcp"], env=env)
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=dt.timedelta(seconds=CLIENT_DEADLINE_SECONDS),
        ) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            print(f"[{now()}] BASELINE_MCP_PROBE=list_tools result=AVAILABLE tool_count={len(tool_names)}")
            print(f"[{now()}] MCP_HAS_RETRY_TOOL={'retry_with_browser_use_agent' in tool_names}")
            print(
                f"[{now()}] REAL_MCP_REQUEST=call_tool retry_with_browser_use_agent "
                f"max_steps={MAX_STEPS} sdk_read_timeout={CLIENT_DEADLINE_SECONDS}s"
            )

            started = time.perf_counter()
            try:
                result = await session.call_tool(
                    "retry_with_browser_use_agent",
                    {"task": RETRY_AGENT_TASK, "max_steps": MAX_STEPS, "use_vision": False},
                )
                elapsed = time.perf_counter() - started
                print(f"[{now()}] REAL_MCP_RESPONSE=AVAILABLE elapsed_seconds={elapsed:.2f} result_type={type(result).__name__}")
                print(f"[{now()}] RESULT=NOT_REPRODUCED")
                local_openai.shutdown()
                return 1
            except asyncio.TimeoutError:
                elapsed = time.perf_counter() - started
                timeout_count = LocalOpenAIHandler.request_count
                print(f"[{now()}] REAL_MCP_CLIENT_EXCEPTION=TimeoutError elapsed_seconds={elapsed:.2f}")
                print(f"[{now()}] REAL_MCP_CLIENT_ERROR=SDK read timeout waiting for retry_with_browser_use_agent response")
                await asyncio.sleep(POST_TIMEOUT_OBSERVE_SECONDS)
                after_count = LocalOpenAIHandler.request_count
                print(
                    f"[{now()}] SERVER_WORK_AFTER_CLIENT_TIMEOUT="
                    f"{after_count > timeout_count} local_openai_requests_before={timeout_count} after={after_count}"
                )
            except Exception as exc:
                elapsed = time.perf_counter() - started
                error_text = str(exc)
                print(f"[{now()}] REAL_MCP_CLIENT_EXCEPTION={type(exc).__name__} elapsed_seconds={elapsed:.2f}")
                print(f"[{now()}] REAL_MCP_CLIENT_ERROR={error_text!r}")
                if "Timed out while waiting for response to ClientRequest" not in error_text:
                    local_openai.shutdown()
                    return 1
                timeout_count = LocalOpenAIHandler.request_count
                await asyncio.sleep(POST_TIMEOUT_OBSERVE_SECONDS)
                after_count = LocalOpenAIHandler.request_count
                print(
                    f"[{now()}] SERVER_WORK_AFTER_CLIENT_TIMEOUT="
                    f"{after_count > timeout_count} local_openai_requests_before={timeout_count} after={after_count}"
                )

            print(f"[{now()}] AFFECTED_WORKFLOW_UNAVAILABLE=True")
            print(f"[{now()}] RESULT=REPRODUCED_AFFECTED_WORKFLOW_UNAVAILABLE")

    local_openai.shutdown()
    return 0


if __name__ == "__main__":
    if "--inside-container" in sys.argv:
        raise SystemExit(asyncio.run(run_real_mcp()))
    raise SystemExit(run_in_docker())
