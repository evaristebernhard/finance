#!/usr/bin/env python
"""Tiny OpenAI-compatible proxy for Hermes -> cockpit.

The proxy accepts OpenAI Chat Completions requests. When the client asks for
stream=true, the proxy calls the upstream cockpit endpoint with stream=false and
wraps the full JSON response as Server-Sent Events.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

CHAT_COMPLETIONS_ALLOWED_FIELDS = {
    "model",
    "messages",
    "temperature",
    "top_p",
    "n",
    "stop",
    "max_tokens",
    "max_completion_tokens",
    "presence_penalty",
    "frequency_penalty",
    "logit_bias",
    "user",
    "tools",
    "tool_choice",
    "functions",
    "function_call",
    "response_format",
    "seed",
    "parallel_tool_calls",
}

MESSAGE_ALLOWED_FIELDS = {
    "role",
    "content",
    "name",
    "tool_call_id",
    "tool_calls",
    "function_call",
}

TOOL_RETRY_DROP_FIELDS = {
    "parallel_tool_calls",
    "tool_choice",
    "function_call",
}

TEXT_FALLBACK_DROP_FIELDS = {
    "tools",
    "tool_choice",
    "functions",
    "function_call",
    "parallel_tool_calls",
}


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value is not None and value != "" else default


class ProxyConfig:
    def __init__(
        self,
        upstream_base_url: str,
        upstream_api_key: str,
        timeout: float,
        default_model: str,
        default_max_tokens: int,
        allow_text_fallback: bool,
        tool_description_limit: int,
        schema_description_limit: int,
    ):
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.upstream_api_key = upstream_api_key
        self.timeout = timeout
        self.default_model = default_model
        self.default_max_tokens = default_max_tokens
        self.allow_text_fallback = allow_text_fallback
        self.tool_description_limit = tool_description_limit
        self.schema_description_limit = schema_description_limit

    def upstream_url(self, path: str) -> str:
        if path.startswith("/v1/"):
            suffix = path[len("/v1") :]
        else:
            suffix = path
        return f"{self.upstream_base_url}{suffix}"


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("content-length") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON request body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("request body must be a JSON object")
    return parsed


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _as_bool(value: str) -> bool:
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _flatten_content_part(part: Any) -> str:
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return ""

    for key in ("text", "input_text", "output_text"):
        value = part.get(key)
        if isinstance(value, str):
            return value

    nested = part.get("content")
    if isinstance(nested, str):
        return nested
    return ""


def _truncate_text(value: Any, limit: int) -> Any:
    if not isinstance(value, str) or limit <= 0 or len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _sanitize_schema(value: Any, description_limit: int) -> Any:
    if isinstance(value, list):
        return [_sanitize_schema(item, description_limit) for item in value]
    if not isinstance(value, dict):
        return value

    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if key == "description":
            sanitized[key] = _truncate_text(item, description_limit)
        else:
            sanitized[key] = _sanitize_schema(item, description_limit)
    return sanitized


def _sanitize_tool(tool: Any, config: ProxyConfig) -> dict[str, Any] | None:
    if not isinstance(tool, dict):
        return None
    if tool.get("type") != "function":
        return tool

    function = tool.get("function")
    if not isinstance(function, dict) or not isinstance(function.get("name"), str):
        return None

    sanitized_function: dict[str, Any] = {"name": function["name"]}
    description = function.get("description")
    if isinstance(description, str):
        sanitized_function["description"] = _truncate_text(description, config.tool_description_limit)

    parameters = function.get("parameters")
    if isinstance(parameters, dict):
        sanitized_function["parameters"] = _sanitize_schema(parameters, config.schema_description_limit)

    if isinstance(function.get("strict"), bool):
        sanitized_function["strict"] = function["strict"]

    return {"type": "function", "function": sanitized_function}


def _sanitize_tools(tools: Any, config: ProxyConfig) -> list[dict[str, Any]] | None:
    if not isinstance(tools, list):
        return None
    sanitized = [_sanitize_tool(tool, config) for tool in tools]
    return [tool for tool in sanitized if tool is not None]


def _normalize_message(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None

    normalized = {key: value for key, value in message.items() if key in MESSAGE_ALLOWED_FIELDS}
    role = normalized.get("role")
    if role == "developer":
        normalized["role"] = "system"
    elif not isinstance(role, str):
        return None

    content = normalized.get("content")
    if isinstance(content, list):
        text = "\n".join(part for part in (_flatten_content_part(item) for item in content) if part)
        normalized["content"] = text
    elif content is None and ("tool_calls" in normalized or "function_call" in normalized):
        normalized.pop("content", None)
    elif content is None:
        normalized["content"] = ""
    elif not isinstance(content, str):
        normalized["content"] = str(content)

    return normalized


def _summarize_error_body(body: bytes) -> str:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        text = body.decode("utf-8", errors="replace").strip()
        return text[:400] if text else ""

    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message[:400]
        message = parsed.get("message")
        if isinstance(message, str):
            return message[:400]
    return json.dumps(parsed, ensure_ascii=False)[:400]


def _log_safe_failure(label: str, status: int, body: bytes, request_body: dict[str, Any]) -> None:
    keys = sorted(request_body.keys())
    tool_count = len(request_body.get("tools") or []) if isinstance(request_body.get("tools"), list) else 0
    msg_count = len(request_body.get("messages") or []) if isinstance(request_body.get("messages"), list) else 0
    sys.stderr.write(
        "[cockpit-sse-proxy] "
        f"{label} failed status={status} keys={keys} messages={msg_count} tools={tool_count} "
        f"error={_summarize_error_body(body)!r}\n"
    )


def _sanitize_chat_request(body: dict[str, Any], config: ProxyConfig) -> dict[str, Any]:
    sanitized = {key: value for key, value in body.items() if key in CHAT_COMPLETIONS_ALLOWED_FIELDS}

    sanitized["model"] = str(sanitized.get("model") or config.default_model)
    messages = sanitized.get("messages")
    if isinstance(messages, list):
        normalized_messages = [_normalize_message(item) for item in messages]
        sanitized["messages"] = [item for item in normalized_messages if item is not None]
    else:
        sanitized["messages"] = []

    sanitized["stream"] = False
    sanitized.pop("stream_options", None)

    if "max_completion_tokens" in sanitized and "max_tokens" not in sanitized:
        sanitized["max_tokens"] = sanitized.pop("max_completion_tokens")
    else:
        sanitized.pop("max_completion_tokens", None)

    has_tools = bool(sanitized.get("tools") or sanitized.get("functions"))
    if "tools" in sanitized:
        sanitized_tools = _sanitize_tools(sanitized.get("tools"), config)
        if sanitized_tools:
            sanitized["tools"] = sanitized_tools
        else:
            sanitized.pop("tools", None)

    if "max_tokens" in sanitized:
        requested_max_tokens = _safe_int(sanitized.get("max_tokens"), config.default_max_tokens)
        sanitized["max_tokens"] = min(requested_max_tokens, config.default_max_tokens)
    elif has_tools:
        sanitized["max_tokens"] = config.default_max_tokens

    if "parallel_tool_calls" in sanitized and not has_tools:
        sanitized.pop("parallel_tool_calls", None)

    return sanitized


def _retry_without_tool_extras(body: dict[str, Any]) -> dict[str, Any]:
    retried = dict(body)
    for key in TOOL_RETRY_DROP_FIELDS:
        retried.pop(key, None)
    return retried


def _text_only_fallback(body: dict[str, Any]) -> dict[str, Any]:
    fallback = dict(body)
    for key in TEXT_FALLBACK_DROP_FIELDS:
        fallback.pop(key, None)
    return fallback


def _copy_request_headers(handler: BaseHTTPRequestHandler, config: ProxyConfig) -> dict[str, str]:
    headers: dict[str, str] = {
        "content-type": "application/json",
        "accept": "application/json",
    }
    for key, value in handler.headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS or lower in {"host", "content-length", "authorization"}:
            continue
        headers[key] = value
    if config.upstream_api_key:
        headers["authorization"] = f"Bearer {config.upstream_api_key}"
    else:
        auth = handler.headers.get("authorization")
        if auth:
            headers["authorization"] = auth
    return headers


def _request_upstream(
    handler: BaseHTTPRequestHandler,
    config: ProxyConfig,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    payload = None if body is None else _json_bytes(body)
    req = urllib.request.Request(
        config.upstream_url(path),
        data=payload,
        headers=_copy_request_headers(handler, config),
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=config.timeout) as resp:
            data = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers, data
    except urllib.error.HTTPError as exc:
        data = exc.read()
        headers = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, headers, data


def _send_json(handler: BaseHTTPRequestHandler, status: int, data: Any) -> None:
    body = _json_bytes(data)
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.send_header("access-control-allow-origin", "*")
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


def _send_raw_json(handler: BaseHTTPRequestHandler, status: int, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.send_header("access-control-allow-origin", "*")
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


def _sse_write(handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
    line = b"data: " + _json_bytes(payload) + b"\n\n"
    handler.wfile.write(line)
    handler.wfile.flush()


def _make_chunk(
    *,
    chunk_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    index: int = 0,
) -> dict[str, Any]:
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": index,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def _iter_text_chunks(text: str, size: int = 240) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _stream_chat_completion(handler: BaseHTTPRequestHandler, upstream_body: bytes) -> None:
    try:
        completion = json.loads(upstream_body)
    except json.JSONDecodeError:
        _send_raw_json(handler, 502, upstream_body)
        return

    if not isinstance(completion, dict) or not completion.get("choices"):
        _send_json(handler, 502, {"error": {"message": "upstream response is not a chat completion"}})
        return

    choice = completion["choices"][0]
    message = choice.get("message") or {}
    model = str(completion.get("model") or "unknown")
    created = int(completion.get("created") or time.time())
    chunk_id = str(completion.get("id") or f"chatcmpl-proxy-{uuid4().hex}")
    finish_reason = choice.get("finish_reason") or "stop"

    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream; charset=utf-8")
    handler.send_header("cache-control", "no-cache, no-transform")
    handler.send_header("connection", "close")
    handler.send_header("x-accel-buffering", "no")
    handler.send_header("access-control-allow-origin", "*")
    handler.end_headers()

    _sse_write(handler, _make_chunk(chunk_id=chunk_id, created=created, model=model, delta={"role": "assistant"}))

    content = message.get("content")
    if isinstance(content, str):
        for part in _iter_text_chunks(content):
            _sse_write(handler, _make_chunk(chunk_id=chunk_id, created=created, model=model, delta={"content": part}))

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for index, call in enumerate(tool_calls):
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            delta = {
                "tool_calls": [
                    {
                        "index": index,
                        "id": call.get("id"),
                        "type": call.get("type") or "function",
                        "function": {
                            "name": function.get("name"),
                            "arguments": function.get("arguments") or "",
                        },
                    }
                ]
            }
            _sse_write(handler, _make_chunk(chunk_id=chunk_id, created=created, model=model, delta=delta))

    _sse_write(
        handler,
        _make_chunk(
            chunk_id=chunk_id,
            created=created,
            model=model,
            delta={},
            finish_reason=str(finish_reason),
        ),
    )

    usage = completion.get("usage")
    if usage is not None:
        _sse_write(
            handler,
            {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [],
                "usage": usage,
            },
        )

    handler.wfile.write(b"data: [DONE]\n\n")
    handler.wfile.flush()
    handler.close_connection = True


def _minimal_models_payload() -> dict[str, Any]:
    model = _env("COCKPIT_DEFAULT_MODEL", "gpt-5.5")
    return {"object": "list", "data": [{"id": model, "object": "model", "created": 0, "owned_by": "cockpit"}]}


class CockpitProxyHandler(BaseHTTPRequestHandler):
    server_version = "cockpit-sse-proxy/0.2"

    @property
    def config(self) -> ProxyConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-headers", "authorization, content-type")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in {"/health", "/v1/health"}:
            _send_json(self, 200, {"ok": True})
            return
        if self.path in {"/version", "/v1/version"}:
            _send_json(self, 200, {"version": "cockpit-sse-proxy-0.2"})
            return
        if self.path in {"/props", "/v1/props"}:
            _send_json(self, 200, {})
            return
        if self.path in {"/v1/models", "/api/v1/models"}:
            status, _, body = _request_upstream(self, self.config, "GET", "/v1/models")
            if 200 <= status < 300:
                _send_raw_json(self, status, body)
            else:
                _send_json(self, 200, _minimal_models_payload())
            return
        if self.path == "/api/tags":
            models = _minimal_models_payload()["data"]
            _send_json(self, 200, {"models": [{"name": m["id"], "model": m["id"]} for m in models]})
            return
        _send_json(self, 404, {"error": {"message": f"unknown route: {self.path}"}})

    def do_POST(self) -> None:
        if self.path == "/api/show":
            _send_json(self, 200, {"license": "", "modelfile": "", "parameters": "", "template": ""})
            return
        if self.path != "/v1/chat/completions":
            try:
                body = _read_json(self)
            except ValueError as exc:
                _send_json(self, 400, {"error": {"message": str(exc)}})
                return
            status, _, data = _request_upstream(self, self.config, "POST", self.path, body)
            _send_raw_json(self, status, data)
            return

        try:
            body = _read_json(self)
        except ValueError as exc:
            _send_json(self, 400, {"error": {"message": str(exc)}})
            return

        wants_stream = bool(body.get("stream"))
        upstream_body = _sanitize_chat_request(body, self.config)

        status, _, data = _request_upstream(self, self.config, "POST", "/v1/chat/completions", upstream_body)
        if not 200 <= status < 300:
            _log_safe_failure("primary chat completion", status, data, upstream_body)

            retry_body = _retry_without_tool_extras(upstream_body)
            if retry_body != upstream_body:
                status, _, data = _request_upstream(self, self.config, "POST", "/v1/chat/completions", retry_body)
                if not 200 <= status < 300:
                    _log_safe_failure("tool-extra retry", status, data, retry_body)
                else:
                    upstream_body = retry_body

        if (
            not 200 <= status < 300
            and self.config.allow_text_fallback
            and (upstream_body.get("tools") or upstream_body.get("functions"))
        ):
            fallback_body = _text_only_fallback(upstream_body)
            status, _, data = _request_upstream(self, self.config, "POST", "/v1/chat/completions", fallback_body)
            if not 200 <= status < 300:
                _log_safe_failure("text fallback", status, data, fallback_body)
            else:
                upstream_body = fallback_body

        if not 200 <= status < 300:
            _send_raw_json(self, status, data)
            return
        if wants_stream:
            _stream_chat_completion(self, data)
        else:
            _send_raw_json(self, status, data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes stream-to-nonstream proxy for cockpit")
    parser.add_argument("--host", default=_env("COCKPIT_PROXY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(_env("COCKPIT_PROXY_PORT", "32181")))
    parser.add_argument("--upstream", default=_env("COCKPIT_BASE_URL", "http://127.0.0.1:32081/v1"))
    parser.add_argument("--api-key", default=_env("COCKPIT_API_KEY", _env("OPENAI_API_KEY", "")))
    parser.add_argument("--timeout", type=float, default=float(_env("COCKPIT_PROXY_TIMEOUT", "300")))
    parser.add_argument("--default-model", default=_env("COCKPIT_DEFAULT_MODEL", "gpt-5.5"))
    parser.add_argument(
        "--default-max-tokens",
        type=int,
        default=_safe_int(_env("COCKPIT_PROXY_DEFAULT_MAX_TOKENS", "4096"), 4096),
    )
    parser.add_argument("--text-fallback", default=_env("COCKPIT_PROXY_TEXT_FALLBACK", "1"))
    parser.add_argument(
        "--tool-description-limit",
        type=int,
        default=_safe_int(_env("COCKPIT_PROXY_TOOL_DESCRIPTION_LIMIT", "2048"), 2048),
    )
    parser.add_argument(
        "--schema-description-limit",
        type=int,
        default=_safe_int(_env("COCKPIT_PROXY_SCHEMA_DESCRIPTION_LIMIT", "1024"), 1024),
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), CockpitProxyHandler)
    server.config = ProxyConfig(  # type: ignore[attr-defined]
        args.upstream,
        args.api_key,
        args.timeout,
        args.default_model,
        _safe_int(args.default_max_tokens, 4096),
        _as_bool(args.text_fallback),
        _safe_int(args.tool_description_limit, 2048),
        _safe_int(args.schema_description_limit, 1024),
    )
    print(f"cockpit-sse-proxy listening on http://{args.host}:{args.port}/v1")
    print(f"upstream: {args.upstream}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
