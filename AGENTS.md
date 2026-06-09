# AGENTS.md

This repo is currently organized around the CCUSDT replay exchange / TFI
strategy line. In every fresh Codex session, start here:

```text
docs/markets/ccusdt/START_HERE.md
```

Then read the system-local agent guide before touching the replay exchange:

```text
systems/ccusdt_replay_exchange/AGENTS.md
```

## Current Default Work Line

- Default active line: CCUSDT replay exchange, TFI strategy, fast-vs-strict
  backtesting, and read-only Monitor.
- Historical/background lines: CHOG, MON/USDC, BONK, and older CCUSDT v2
  execution research. Use them only when the user explicitly redirects.
- The old long root handoff was archived at:

```text
docs/handoff/archive/AGENTS-legacy-20260601.md
```

## Safety

- Do not print private RPC keys, env contents, OpenAI tokens, or browser
  session JSON.
- Do not modify or delete `data/`, `date/`, `runs/`, `.env*`, or `rpc.txt`
  unless the user explicitly asks.
- Do not revert or delete user changes in a dirty worktree.
- Do not run destructive Git commands.
- For CCUSDT runtime work, Runner must not read labels, Bot must not read
  `date/`, and Monitor must remain read-only.

## Quick Orientation

Use the CCUSDT start page to choose the right lane:

```text
docs/markets/ccusdt/START_HERE.md
```

Use the global docs index only when the user asks for another market or a
historical data-collection line:

```text
docs/README.md
```
