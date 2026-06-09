# Cockpit SSE Proxy

Small local OpenAI-compatible proxy for Hermes -> cockpit.

Hermes often sends `stream=true` for agent turns. Some OpenAI-compatible
backends support normal chat completions and tool calling, but fail when the
same request is streamed. This proxy accepts the streaming request, calls the
upstream cockpit endpoint with `stream=false`, then wraps the full response as
OpenAI-style Server-Sent Events.

## Related GitHub References

- `BerriAI/litellm`: a full-featured OpenAI-compatible proxy. Useful if you
  want a mature gateway, routing, logging, auth, retries, and many providers.
- `simonx1/openai-o1-proxy`: a small proxy-style project showing how to expose
  an OpenAI-compatible surface for models/endpoints with special behavior.
- `NousResearch/hermes-agent` issue `#25629`: reports the same class of problem:
  `stream=false` with tools works, but `stream=true` with tools fails/hangs for
  some local/custom backends.

This project is intentionally much narrower than LiteLLM: it only implements
the routes Hermes needs for the cockpit workaround.

On this machine, `hermes` is wrapped by:

```text
C:\Users\jiang\AppData\Local\hermes\bin\hermes.cmd
```

Normally you do not need to start this proxy manually. Typing `hermes` or
`hermes --tui` starts the proxy automatically when `127.0.0.1:32181` is not
already listening.

The proxy also sanitizes Hermes chat-completions payloads before forwarding
them:

- Only standard Chat Completions fields are forwarded.
- `developer` messages are converted to `system` messages.
- content parts are flattened to text for simpler backends.
- `max_tokens` defaults to `4096` when tool definitions are present and larger
  Hermes output budgets are capped to that local compatibility limit.
- if a tool-heavy request still fails, the proxy retries with tool extras
  removed before falling back to text-only compatibility.

## Start

Preferred:

```powershell
hermes --tui
```

Manual proxy start, only for debugging:

```powershell
$env:COCKPIT_BASE_URL = "http://127.0.0.1:32081/v1"
$env:COCKPIT_API_KEY = "<your token>"
python tools\cockpit_sse_proxy\cockpit_sse_proxy.py --port 32181
```

If `OPENAI_API_KEY` is already set in the environment, `COCKPIT_API_KEY` can be
omitted.

Important on this machine: make sure localhost bypasses any global HTTP proxy:

```powershell
$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"
```

The proxy listens at:

```text
http://127.0.0.1:32181/v1
```

## Hermes Config

Point Hermes to the proxy, not directly to cockpit:

```yaml
model:
  default: "gpt-5.5"
  provider: "custom"
  base_url: "http://127.0.0.1:32181/v1"
  api_mode: "chat_completions"
```

Keep the real cockpit token in Hermes `.env` or your shell environment. Do not
put tokens in this repo.

## Verify

Non-streaming:

```powershell
$headers = @{ Authorization = "Bearer $env:COCKPIT_API_KEY"; "Content-Type" = "application/json" }
$body = @{ model = "gpt-5.5"; messages = @(@{ role = "user"; content = "Reply OK" }) } | ConvertTo-Json -Depth 10
Invoke-RestMethod http://127.0.0.1:32181/v1/chat/completions -Method Post -Headers $headers -Body $body
```

Streaming:

```powershell
$body = @{ model = "gpt-5.5"; stream = $true; messages = @(@{ role = "user"; content = "Reply OK" }) } | ConvertTo-Json -Depth 10
Invoke-WebRequest http://127.0.0.1:32181/v1/chat/completions -Method Post -Headers $headers -Body $body
```

Hermes one-shot:

```powershell
hermes -z "Reply with exactly OK."
```
