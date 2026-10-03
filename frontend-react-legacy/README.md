# Legacy React comparison workbench

This folder restores the archived React UI from `archive/legacy_web_workbench/frontend`.
It is intentionally kept separate from the native Slint application so the two
information architectures can be compared side by side.

The old UI is backed here by a server-side adapter in `lib/runner.ts` that reads the
same Runner artifact used by the native comparison build. It is for visual and
interaction comparison only:

- it preserves the old chart / book / factor / research layout;
- it reads the same `events.ndjson` price/book stream as the native build;
- its order ticket is explicitly toy-fill semantics;
- it does not claim to read the current Runner causal artifacts;
- it does not replace the native Replay Workbench.

Run it from the repository root:

```bash
cd frontend-react-legacy
npm run dev
```

Open <http://127.0.0.1:3002>.
