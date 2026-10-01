#!/usr/bin/env node
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 32181;
const DEFAULT_UPSTREAM_BASE_URL = "http://127.0.0.1:32081/v1";
const DEFAULT_MODEL = "gpt-5.5";

const CHAT_ALLOWED_FIELDS = new Set([
  "model",
  "messages",
  "stream",
  "stream_options",
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
]);

function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index >= 0 && index + 1 < process.argv.length) {
    return process.argv[index + 1];
  }
  return fallback;
}

function readHermesEnv() {
  const local = process.env.LOCALAPPDATA || process.env.LocalAppData;
  if (!local) {
    return {};
  }
  const envPath = path.join(local, "hermes", ".env");
  if (!fs.existsSync(envPath)) {
    return {};
  }

  const values = {};
  const text = fs.readFileSync(envPath, "utf8").replace(/^\uFEFF/, "");
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) {
      continue;
    }
    const index = line.indexOf("=");
    const key = line.slice(0, index).trim().replace(/^\uFEFF/, "");
    let value = line.slice(index + 1).trim();
    if (
      (value.startsWith("\"") && value.endsWith("\"")) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

const hermesEnv = readHermesEnv();

function envValue(name, fallback = "") {
  return process.env[name] || hermesEnv[name] || fallback;
}

function upstreamBaseUrl() {
  return (process.env.COCKPIT_BASE_URL || DEFAULT_UPSTREAM_BASE_URL).replace(/\/+$/, "");
}

function upstreamApiKey() {
  return process.env.COCKPIT_API_KEY || process.env.OPENAI_API_KEY || hermesEnv.OPENAI_API_KEY || "";
}

function defaultModel() {
  return process.env.COCKPIT_DEFAULT_MODEL || envValue("OPENAI_MODEL", DEFAULT_MODEL);
}

function jsonResponse(res, status, payload) {
  const body = Buffer.from(JSON.stringify(payload), "utf8");
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": String(body.length),
    "access-control-allow-origin": "*",
  });
  res.end(body);
}

function textResponse(res, status, body) {
  const bytes = Buffer.from(body, "utf8");
  res.writeHead(status, {
    "content-type": "text/plain; charset=utf-8",
    "content-length": String(bytes.length),
    "access-control-allow-origin": "*",
  });
  res.end(bytes);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function flattenContentPart(part) {
  if (typeof part === "string") {
    return part;
  }
  if (!part || typeof part !== "object") {
    return "";
  }
  for (const key of ["text", "input_text", "output_text"]) {
    if (typeof part[key] === "string") {
      return part[key];
    }
  }
  if (typeof part.content === "string") {
    return part.content;
  }
  return "";
}

function normalizeMessage(message) {
  if (!message || typeof message !== "object") {
    return null;
  }
  const normalized = {...message};
  if (normalized.role === "developer") {
    normalized.role = "system";
  }
  if (Array.isArray(normalized.content)) {
    normalized.content = normalized.content.map(flattenContentPart).filter(Boolean).join("\n");
  } else if (normalized.content == null && !normalized.tool_calls && !normalized.function_call) {
    normalized.content = "";
  } else if (normalized.content != null && typeof normalized.content !== "string") {
    normalized.content = String(normalized.content);
  }
  return normalized;
}

function normalizeChatBody(body) {
  const normalized = {};
  for (const [key, value] of Object.entries(body || {})) {
    if (CHAT_ALLOWED_FIELDS.has(key)) {
      normalized[key] = value;
    }
  }

  normalized.model = String(normalized.model || defaultModel());

  if (Array.isArray(normalized.messages)) {
    normalized.messages = normalized.messages.map(normalizeMessage).filter(Boolean);
  } else {
    normalized.messages = [];
  }

  // Cockpit 0.25.6 accepts max_tokens but may 502 on max_completion_tokens.
  if (normalized.max_completion_tokens != null && normalized.max_tokens == null) {
    normalized.max_tokens = normalized.max_completion_tokens;
  }
  delete normalized.max_completion_tokens;

  if (normalized.stream_options && typeof normalized.stream_options !== "object") {
    delete normalized.stream_options;
  }

  return normalized;
}

function fallbackModels() {
  return {
    object: "list",
    data: [
      {
        id: defaultModel(),
        object: "model",
        created: 0,
        owned_by: "cockpit",
      },
    ],
  };
}

function upstreamHeaders(req) {
  const auth = upstreamApiKey()
    ? `Bearer ${upstreamApiKey()}`
    : req.headers.authorization || "";
  const headers = {
    authorization: auth,
    "content-type": "application/json",
    accept: "text/event-stream, application/json",
  };
  return Object.fromEntries(Object.entries(headers).filter(([, value]) => value));
}

function upstreamUrl(suffix) {
  return `${upstreamBaseUrl()}${suffix}`;
}

async function proxyModels(req, res) {
  try {
    const upstream = await fetch(upstreamUrl("/models"), {
      method: "GET",
      headers: upstreamHeaders(req),
    });
    const text = await upstream.text();
    if (!upstream.ok) {
      jsonResponse(res, 200, fallbackModels());
      return;
    }
    res.writeHead(upstream.status, {
      "content-type": upstream.headers.get("content-type") || "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
    });
    res.end(text);
  } catch {
    jsonResponse(res, 200, fallbackModels());
  }
}

function writeSseHeaders(res) {
  res.writeHead(200, {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    connection: "close",
    "x-accel-buffering": "no",
    "access-control-allow-origin": "*",
  });
}

async function relayStreaming(upstream, res) {
  writeSseHeaders(res);

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let sawDone = false;
  let tail = "";

  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) {
        break;
      }
      const text = decoder.decode(value, {stream: true});
      if (text.includes("data: [DONE]")) {
        sawDone = true;
      }
      tail = (tail + text).slice(-32);
      res.write(Buffer.from(text, "utf8"));
    }
    const rest = decoder.decode();
    if (rest) {
      if (rest.includes("data: [DONE]")) {
        sawDone = true;
      }
      tail = (tail + rest).slice(-32);
      res.write(Buffer.from(rest, "utf8"));
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // Already closed by upstream.
    }
  }

  if (!sawDone) {
    if (tail && !tail.endsWith("\n")) {
      res.write("\n");
    }
    res.write("data: [DONE]\n\n");
  }
  res.end();
}

async function forwardChat(req, res, requestBody) {
  const body = normalizeChatBody(requestBody);
  const wantsStream = body.stream === true;
  const upstream = await fetch(upstreamUrl("/chat/completions"), {
    method: "POST",
    headers: upstreamHeaders(req),
    body: JSON.stringify(body),
  });

  if (!upstream.ok) {
    const text = await upstream.text();
    jsonResponse(res, upstream.status || 502, {
      error: {
        code: "upstream_error",
        message: text || `Cockpit upstream returned HTTP ${upstream.status}`,
        type: "invalid_request_error",
      },
    });
    return;
  }

  if (wantsStream) {
    await relayStreaming(upstream, res);
    return;
  }

  const text = await upstream.text();
  res.writeHead(upstream.status, {
    "content-type": upstream.headers.get("content-type") || "application/json; charset=utf-8",
    "access-control-allow-origin": "*",
  });
  res.end(text);
}

async function handleRequest(req, res) {
  const url = new URL(req.url || "/", "http://127.0.0.1");

  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "authorization, content-type",
      "access-control-allow-methods": "GET, POST, OPTIONS",
    });
    res.end();
    return;
  }

  if (req.method === "GET" && ["/health", "/v1/health"].includes(url.pathname)) {
    jsonResponse(res, 200, {
      ok: true,
      upstream_base_url: upstreamBaseUrl(),
      shim: "cockpit-stream-shim",
    });
    return;
  }

  if (req.method === "GET" && ["/version", "/v1/version"].includes(url.pathname)) {
    jsonResponse(res, 200, {version: "cockpit-stream-shim-1.0.0"});
    return;
  }

  if (req.method === "GET" && ["/v1/models", "/api/v1/models"].includes(url.pathname)) {
    await proxyModels(req, res);
    return;
  }

  if (req.method === "POST" && url.pathname === "/v1/chat/completions") {
    let parsed;
    try {
      const raw = await readBody(req);
      parsed = raw.length ? JSON.parse(raw.toString("utf8")) : {};
    } catch (error) {
      jsonResponse(res, 400, {
        error: {
          message: `invalid JSON request body: ${error.message}`,
          type: "invalid_request_error",
        },
      });
      return;
    }

    try {
      await forwardChat(req, res, parsed);
    } catch (error) {
      jsonResponse(res, 502, {
        error: {
          code: "shim_error",
          message: error.message || String(error),
          type: "invalid_request_error",
        },
      });
    }
    return;
  }

  textResponse(res, 404, `unknown route: ${url.pathname}`);
}

const host = argValue("--host", process.env.COCKPIT_SHIM_HOST || DEFAULT_HOST);
const port = Number(argValue("--port", process.env.COCKPIT_SHIM_PORT || DEFAULT_PORT));

const server = http.createServer((req, res) => {
  handleRequest(req, res).catch((error) => {
    if (!res.headersSent) {
      jsonResponse(res, 500, {error: {message: error.message || String(error)}});
    } else {
      res.destroy(error);
    }
  });
});

server.listen(port, host, () => {
  console.error(
    `[cockpit-stream-shim] listening on http://${host}:${port}/v1 -> ${upstreamBaseUrl()}`
  );
});
