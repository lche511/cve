import json
import os
import sys
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP


RESULT_MB = int(os.environ.get("MCP_RESULT_MB", "8"))
SCHEMA_TOOL_COUNT = int(os.environ.get("MCP_SCHEMA_TOOL_COUNT", "32"))
SCHEMA_DESC_KB = int(os.environ.get("MCP_SCHEMA_DESC_KB", "16"))
METRICS_FILE = Path(os.environ.get("MCP_METRICS_FILE", "mcp_amplify_metrics.jsonl"))

mcp = FastMCP("amplify")


def _write_metric(event, **fields):
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event}
    record.update(fields)
    with METRICS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _payload(size_mb, marker="A"):
    size_mb = max(1, min(int(size_mb), 256))
    token = (marker or "A")[0]
    return token * (size_mb * 1024 * 1024)


@mcp.tool()
def amplify_resource(size_mb: int = RESULT_MB, marker: str = "A") -> str:
    """Return a caller-controlled large diagnostic text payload."""
    text = _payload(size_mb, marker)
    _write_metric("tool_call", tool="amplify_resource", result_bytes=len(text.encode("utf-8")))
    return text


@mcp.resource("amplify://payload/{size_mb}")
def read_amplified_payload(size_mb: int) -> str:
    """Return a large resource body for MCP resource-read testing."""
    text = _payload(size_mb, "R")
    _write_metric("resource_read", uri=f"amplify://payload/{size_mb}", result_bytes=len(text.encode("utf-8")))
    return text


def _register_schema_tools():
    desc = (
        "Diagnostic schema expansion fixture. This tool is intentionally verbose "
        "to demonstrate unbounded MCP tool-discovery/schema propagation. "
        + ("S" * (SCHEMA_DESC_KB * 1024))
    )

    def make_schema_probe(index: int):
        def schema_probe(payload: str = "ok") -> str:
            _write_metric("schema_probe_call", tool=f"schema_probe_{index}", payload_len=len(payload or ""))
            return f"schema_probe_{index}:ok"

        schema_probe.__name__ = f"schema_probe_{index}"
        schema_probe.__doc__ = desc
        return schema_probe

    for idx in range(SCHEMA_TOOL_COUNT):
        mcp.tool()(make_schema_probe(idx))


_register_schema_tools()


if __name__ == "__main__":
    _write_metric(
        "server_start",
        result_mb=RESULT_MB,
        schema_tool_count=SCHEMA_TOOL_COUNT,
        schema_desc_kb=SCHEMA_DESC_KB,
        argv=sys.argv,
    )
    mcp.run()
