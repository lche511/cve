import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = os.environ.get("MOCK_LLM_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOCK_LLM_PORT", "18083"))
MODEL = os.environ.get("MOCK_LLM_MODEL", "hermes-mcp-mock")
RESULT_MB = int(os.environ.get("MCP_RESULT_MB", "8"))
FINAL_DELAY = float(os.environ.get("MOCK_LLM_AFTER_TOOL_DELAY", "30"))
TRIGGER = os.environ.get("MOCK_LLM_TRIGGER", "MCP_AMPLIFY_TRIGGER")
NORMAL_TASK_TERMS = (
    "diagnostic bundle",
    "mcp diagnostic resource",
    "connected mcp diagnostic",
    "complete payload",
)

_lock = threading.Lock()
_metrics = {
    "total_chat": 0,
    "tool_call_responses": 0,
    "after_tool_requests": 0,
    "max_body_bytes": 0,
    "max_tools": 0,
    "max_tool_schema_bytes": 0,
    "last_tool_name": None,
    "last_after_tool_body_bytes": 0,
    "final_delay_seconds": FINAL_DELAY,
}


def _record(**updates):
    with _lock:
        for key, value in updates.items():
            if key.startswith("max_"):
                _metrics[key] = max(_metrics.get(key, 0), value)
            else:
                _metrics[key] = value


def _snapshot():
    with _lock:
        return dict(_metrics)


def _contains_trigger(payload):
    for msg in payload.get("messages") or []:
        content = msg.get("content")
        if isinstance(content, str) and TRIGGER in content:
            return True
        if isinstance(content, str):
            lowered = content.lower()
            if "mcp" in lowered and any(term in lowered for term in NORMAL_TASK_TERMS):
                return True
    return False


def _has_tool_result(payload):
    return any((msg.get("role") == "tool") for msg in (payload.get("messages") or []))


def _tool_result_texts(payload):
    texts = []
    for msg in payload.get("messages") or []:
        if msg.get("role") != "tool":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.append(json.dumps(content, ensure_ascii=False))
    return texts


def _tool_names(tools):
    names = []
    for tool in tools or []:
        fn = (tool or {}).get("function") or {}
        name = fn.get("name")
        if name:
            names.append(name)
    return names


def _tool_schema_bytes(tools):
    try:
        return len(json.dumps(tools, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 0


def _choose_mcp_tool(tools):
    names = _tool_names(tools)

    for name in names:
        if name.endswith("_read_resource") and "amplify" in name:
            return name, {"uri": f"amplify://payload/{RESULT_MB}"}
    for name in names:
        if name.endswith("_amplify_resource") or name.endswith("amplify_resource"):
            return name, {"size_mb": RESULT_MB, "marker": "A"}
    return None, {}


def _choose_from_search_results(tool_texts):
    for text in reversed(tool_texts):
        try:
            parsed = json.loads(text)
        except Exception:
            continue
        matches = parsed.get("matches") or []
        names = [m.get("name") for m in matches if isinstance(m, dict) and m.get("name")]
        for name in names:
            if name and name.endswith("_read_resource") and "amplify" in name:
                return name, {"uri": f"amplify://payload/{RESULT_MB}"}
        for name in names:
            if name and (name.endswith("_amplify_resource") or name.endswith("amplify_resource")):
                return name, {"size_mb": RESULT_MB, "marker": "A"}
        for name in names:
            if name and "amplify" in name:
                return name, {"payload": "trigger"}
    return None, {}


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesMcpMockLLM/0.1"

    def log_message(self, fmt, *args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        for event in events:
            self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _chat_payload(self, payload, message, finish_reason="stop"):
        return {
            "id": f"chatcmpl-mcp-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model") or MODEL,
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 64, "completion_tokens": 16, "total_tokens": 80},
        }

    def _stream_content(self, payload, content, finish_reason="stop"):
        base = {
            "id": f"chatcmpl-mcp-stream-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": payload.get("model") or MODEL,
        }
        return self._sse(
            [
                {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
                {**base, "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]},
                {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]},
            ]
        )

    def _stream_tool_call(self, payload, tool_name, args):
        base = {
            "id": f"chatcmpl-mcp-tool-stream-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": payload.get("model") or MODEL,
        }
        args_json = json.dumps(args)
        return self._sse(
            [
                {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_mcp_amplify_1",
                                        "type": "function",
                                        "function": {"name": tool_name, "arguments": ""},
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": args_json},
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ],
                },
                {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
            ]
        )

    def do_GET(self):
        if self.path in {"/v1/models", "/models"}:
            return self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})
        if self.path == "/metrics":
            return self._json(200, _snapshot())
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}

        if self.path not in {"/v1/chat/completions", "/chat/completions"}:
            return self._json(404, {"error": {"message": "unsupported path"}})

        tools = payload.get("tools") or []
        tool_names = _tool_names(tools)
        schema_bytes = _tool_schema_bytes(tools)
        with _lock:
            _metrics["total_chat"] += 1
            _metrics["max_body_bytes"] = max(_metrics["max_body_bytes"], len(raw))
            _metrics["max_tools"] = max(_metrics["max_tools"], len(tools))
            _metrics["max_tool_schema_bytes"] = max(_metrics["max_tool_schema_bytes"], schema_bytes)
            _metrics["last_tool_names_sample"] = tool_names[:12]

        tool_texts = _tool_result_texts(payload)
        large_tool_result = max((len(t.encode("utf-8")) for t in tool_texts), default=0) >= 1024 * 1024
        if large_tool_result:
            with _lock:
                _metrics["after_tool_requests"] += 1
                _metrics["last_after_tool_body_bytes"] = len(raw)
            print(
                f"[{time.strftime('%H:%M:%S')}] after_tool_request "
                f"body_bytes={len(raw)} schema_bytes={schema_bytes} delay={FINAL_DELAY}s",
                flush=True,
            )
            time.sleep(FINAL_DELAY)
            if payload.get("stream"):
                return self._stream_content(payload, "local MCP amplification task finished")
            return self._json(
                200,
                self._chat_payload(payload, {"role": "assistant", "content": "local MCP amplification task finished"}),
            )

        should_trigger = _contains_trigger(payload)
        tool_name, args = _choose_mcp_tool(tools)
        if should_trigger and tool_name:
            _record(last_tool_name=tool_name)
            with _lock:
                _metrics["tool_call_responses"] += 1
            print(
                f"[{time.strftime('%H:%M:%S')}] issuing_tool_call "
                f"name={tool_name} body_bytes={len(raw)} schema_bytes={schema_bytes} tools={len(tools)}",
                flush=True,
            )
            if payload.get("stream"):
                return self._stream_tool_call(payload, tool_name, args)
            return self._json(
                200,
                self._chat_payload(
                    payload,
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_mcp_amplify_1",
                                "type": "function",
                                "function": {"name": tool_name, "arguments": json.dumps(args)},
                            }
                        ],
                    },
                    finish_reason="tool_calls",
                ),
            )

        if should_trigger and _has_tool_result(payload) and "tool_call" in tool_names:
            target_name, target_args = _choose_from_search_results(tool_texts)
            if target_name:
                _record(last_tool_name=f"tool_call->{target_name}")
                with _lock:
                    _metrics["tool_call_responses"] += 1
                bridge_args = {"name": target_name, "arguments": target_args}
                print(
                    f"[{time.strftime('%H:%M:%S')}] issuing_tool_call "
                    f"name=tool_call target={target_name} body_bytes={len(raw)} schema_bytes={schema_bytes} tools={len(tools)}",
                    flush=True,
                )
                if payload.get("stream"):
                    return self._stream_tool_call(payload, "tool_call", bridge_args)
                return self._json(
                    200,
                    self._chat_payload(
                        payload,
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_tool_call_mcp_amplify_1",
                                    "type": "function",
                                    "function": {"name": "tool_call", "arguments": json.dumps(bridge_args)},
                                }
                            ],
                        },
                        finish_reason="tool_calls",
                    ),
                )

        if should_trigger and "tool_search" in tool_names:
            search_args = {"query": "mcp amplify resource read_resource amplify_resource", "limit": 10}
            _record(last_tool_name="tool_search")
            with _lock:
                _metrics["tool_call_responses"] += 1
            print(
                f"[{time.strftime('%H:%M:%S')}] issuing_tool_call "
                f"name=tool_search body_bytes={len(raw)} schema_bytes={schema_bytes} tools={len(tools)}",
                flush=True,
            )
            if payload.get("stream"):
                return self._stream_tool_call(payload, "tool_search", search_args)
            return self._json(
                200,
                self._chat_payload(
                    payload,
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_tool_search_mcp_amplify_1",
                                "type": "function",
                                "function": {"name": "tool_search", "arguments": json.dumps(search_args)},
                            }
                        ],
                    },
                    finish_reason="tool_calls",
                ),
            )

        if payload.get("stream"):
            return self._stream_content(payload, "normal local response")
        return self._json(
            200,
            self._chat_payload(payload, {"role": "assistant", "content": "normal local response"}),
        )


if __name__ == "__main__":
    print(f"mock_llm_mcp listening on http://{HOST}:{PORT}/v1 result_mb={RESULT_MB}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
