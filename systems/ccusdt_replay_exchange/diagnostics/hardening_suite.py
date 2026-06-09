#!/usr/bin/env python
"""Run CCUSDT replay exchange hardening diagnostics.

The suite builds the local CLI, runs bounded-memory pressure checks, validates
determinism, audits compact logs, and checks Python online features against a
same-stream reference implementation.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


BASE_PORT = 9101


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--date", default="2026-05-18")
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-prefix", default="hardening")
    parser.add_argument("--skip-full-l2", action="store_true")
    parser.add_argument("--l2-batch-size", type=int, default=1000)
    parser.add_argument("--feature-l2-max-rows", type=int, default=5000)
    return parser.parse_args()


class MemorySampler:
    def __init__(self, pid: int, interval_s: float = 0.05) -> None:
        self.pid = pid
        self.interval_s = interval_s
        self.peak_bytes = 0
        self.samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            rss = process_rss_bytes(self.pid)
            if rss is not None:
                self.peak_bytes = max(self.peak_bytes, rss)
                self.samples += 1
            time.sleep(self.interval_s)


def process_rss_bytes(pid: int) -> int | None:
    if sys.platform == "win32":
        return windows_working_set_bytes(pid)
    status = Path(f"/proc/{pid}/status")
    if status.exists():
        for line in status.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) * 1024
    return None


def windows_working_set_bytes(pid: int) -> int | None:
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    process_query_limited_information = 0x1000
    process_vm_read = 0x0010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information | process_vm_read, False, pid)
    if not handle:
        return None
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            return None
        return int(counters.WorkingSetSize)
    finally:
        kernel32.CloseHandle(handle)


def exe_path(repo_root: Path) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return repo_root / "systems" / "ccusdt_replay_exchange" / "engine" / "target" / "debug" / f"ccusdt_replay_cli{suffix}"


def run_command(
    command: list[str],
    cwd: Path,
    timeout_s: int | None = None,
    sample_memory: bool = False,
) -> dict[str, Any]:
    start = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    sampler = MemorySampler(process.pid) if sample_memory else None
    if sampler:
        sampler.start()
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
    finally:
        if sampler:
            sampler.stop()
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if process.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "command": command,
                    "returncode": process.returncode,
                    "stdout_tail": stdout[-4000:],
                    "stderr_tail": stderr[-4000:],
                },
                indent=2,
            )
        )
    return {
        "stdout": stdout,
        "stderr": stderr,
        "elapsed_wall_ms": elapsed_ms,
        "peak_rss_mb": round((sampler.peak_bytes if sampler else 0) / (1024 * 1024), 3)
        if sampler and sampler.samples
        else None,
        "memory_samples": sampler.samples if sampler else 0,
    }


def parse_last_json(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return None
    start = text.rfind("\n{")
    if start >= 0:
        text = text[start + 1 :]
    return json.loads(text)


def run_cli_json(command: list[str], repo_root: Path, sample_memory: bool = True) -> dict[str, Any]:
    result = run_command(command, repo_root, sample_memory=sample_memory)
    parsed = parse_last_json(result["stdout"])
    return {
        "summary": parsed,
        "elapsed_wall_ms": result["elapsed_wall_ms"],
        "peak_rss_mb": result["peak_rss_mb"],
        "memory_samples": result["memory_samples"],
        "events_per_sec": round(
            (parsed.get("events_seen", 0) if isinstance(parsed, dict) else 0)
            / max(result["elapsed_wall_ms"] / 1000.0, 1e-9),
            3,
        ),
    }


def audit_run(repo_root: Path, run_dir: str, allow_empty_orders: bool) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "systems/ccusdt_replay_exchange/diagnostics/audit_event_log.py",
        "--run-dir",
        run_dir,
    ]
    if allow_empty_orders:
        cmd.append("--allow-empty-orders")
    result = run_command(cmd, repo_root)
    return parse_last_json(result["stdout"])


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    ignored = {
        "run_id",
        "run_dir",
        "public_addr",
        "private_addr",
        "order_addr",
        "state_addr",
    }
    return {key: value for key, value in summary.items() if key not in ignored}


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    build_cmd = [
        "cargo",
        "build",
        "--manifest-path",
        "systems/ccusdt_replay_exchange/engine/Cargo.toml",
        "-p",
        "ccusdt_replay_cli",
    ]
    build = run_command(build_cmd, repo_root)

    cli = exe_path(repo_root)
    if not cli.exists():
        raise SystemExit(f"built CLI not found: {cli}")

    def server_cmd(run_id: str, port_offset: int, include_l2: bool = False) -> list[str]:
        base = BASE_PORT + port_offset
        command = [
            str(cli),
            "run",
            "server",
            "--canonical-date",
            args.date,
            "--run-id",
            run_id,
            "--max-events",
            "10000000",
            "--public-addr",
            f"127.0.0.1:{base}",
            "--private-addr",
            f"127.0.0.1:{base + 1}",
            "--order-addr",
            f"127.0.0.1:{base + 2}",
            "--state-addr",
            f"127.0.0.1:{base + 3}",
            "--startup-wait-ms",
            "0",
            "--event-sleep-us",
            "0",
        ]
        if include_l2:
            command.extend(["--include-l2", "--l2-batch-size", str(args.l2_batch_size)])
        return command

    qt_a = run_cli_json(
        server_cmd(f"{args.run_prefix}_qt_a_{timestamp}", 0, include_l2=False),
        repo_root,
    )
    qt_b = run_cli_json(
        server_cmd(f"{args.run_prefix}_qt_b_{timestamp}", 10, include_l2=False),
        repo_root,
    )
    qt_a["audit"] = audit_run(repo_root, qt_a["summary"]["run_dir"], allow_empty_orders=True)
    qt_b["audit"] = audit_run(repo_root, qt_b["summary"]["run_dir"], allow_empty_orders=True)
    deterministic = normalize_summary(qt_a["summary"]) == normalize_summary(qt_b["summary"])

    l2_result: dict[str, Any] | None = None
    if not args.skip_full_l2:
        l2_result = run_cli_json(
            server_cmd(f"{args.run_prefix}_full_l2_{timestamp}", 20, include_l2=True),
            repo_root,
        )
        l2_result["audit"] = audit_run(repo_root, l2_result["summary"]["run_dir"], allow_empty_orders=True)

    order_smoke_cmd = [
        str(cli),
        "run",
        "sparse-python",
        "--canonical-date",
        args.date,
        "--run-id",
        f"{args.run_prefix}_order_chain_{timestamp}",
        "--max-events",
        "1200",
        "--latency-us",
        "50000",
        "--strategy-arg=--tfi-threshold",
        "--strategy-arg=0.05",
        "--strategy-arg=--min-trades",
        "--strategy-arg=1",
        "--strategy-arg=--min-qty",
        "--strategy-arg=0",
        "--strategy-arg=--max-orders",
        "--strategy-arg=1",
        "--strategy-arg=--qty",
        "--strategy-arg=10",
    ]
    order_smoke = run_cli_json(order_smoke_cmd, repo_root)
    order_smoke["audit"] = audit_run(repo_root, order_smoke["summary"]["run_dir"], allow_empty_orders=False)

    feature_qt = run_command(
        [
            sys.executable,
            "systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py",
            "--repo-root",
            ".",
            "--date",
            args.date,
        ],
        repo_root,
    )
    feature_l2 = run_command(
        [
            sys.executable,
            "systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py",
            "--repo-root",
            ".",
            "--date",
            args.date,
            "--include-l2",
            "--l2-batch-size",
            str(args.l2_batch_size),
            "--l2-max-rows",
            str(args.feature_l2_max_rows),
        ],
        repo_root,
    )
    feature_run_checkpoints = run_command(
        [
            sys.executable,
            "systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py",
            "--repo-root",
            ".",
            "--date",
            args.date,
            "--max-events",
            "1200",
            "--sample-every",
            "100",
            "--run-dir",
            order_smoke["summary"]["run_dir"],
        ],
        repo_root,
    )

    result = {
        "ok": True,
        "timestamp": timestamp,
        "date": args.date,
        "build_elapsed_wall_ms": build["elapsed_wall_ms"],
        "quote_trade_full_day_a": qt_a,
        "quote_trade_full_day_b": qt_b,
        "determinism": {
            "ok": deterministic,
            "normalized_summary_keys": sorted(normalize_summary(qt_a["summary"]).keys()),
        },
        "full_day_l2": l2_result,
        "order_chain_smoke": order_smoke,
        "feature_state_quote_trade": parse_last_json(feature_qt["stdout"]),
        "feature_state_l2_sample": parse_last_json(feature_l2["stdout"]),
        "feature_state_run_checkpoints": parse_last_json(feature_run_checkpoints["stdout"]),
    }

    checks = [
        deterministic,
        qt_a["audit"]["ok"],
        qt_b["audit"]["ok"],
        order_smoke["audit"]["ok"],
        result["feature_state_quote_trade"]["ok"],
        result["feature_state_l2_sample"]["ok"],
        result["feature_state_run_checkpoints"]["ok"],
    ]
    if l2_result is not None:
        checks.append(l2_result["audit"]["ok"])
        checks.append(l2_result["summary"]["l2_batches_seen"] > 0)
    result["ok"] = all(checks)

    out_dir = repo_root / "systems" / "ccusdt_replay_exchange" / "runs" / "hardening_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_prefix}_{timestamp}.json"
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    result["report_path"] = str(out_path.relative_to(repo_root)).replace("\\", "/")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
