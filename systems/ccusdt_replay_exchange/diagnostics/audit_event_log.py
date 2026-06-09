#!/usr/bin/env python
"""Validate compact CCUSDT replay exchange event logs.

This is a run-after diagnostic. It reads only a run directory produced by the
runner and checks whether compact order chains are causally replayable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


CHAIN_ORDER = [
    "order_intent",
    "order_scheduled",
    "order_arrived",
    "order_ack",
    "fill",
]

DECISION_EVENT_TYPES = {
    "capacity_decision",
    "order_intent",
    "order_scheduled",
}

EXECUTION_EVENT_TYPES = {
    "order_arrived",
    "order_ack",
    "order_reject",
    "risk_reject",
    "fill",
    "position_opened",
    "position_closed",
    "position_partial_closed",
}

PORTFOLIO_EVENT_TYPES = {
    "portfolio_state_on_change",
}

BASE_UNSTABLE_FIELDS = {
    "event_id",
    "_line_no",
    "run_id",
    "wall_ts_ms",
    "bridge_wall_latency_us",
    "bridge_wall_latency_ms",
}

WALL_DRAIN_FIELDS = {
    "drain_stream_seq",
    "arrival_stream_lag",
    "target_miss_us",
    "trigger_exchange_ts_us",
    "trigger_local_ts_us",
}

DECISION_UNSTABLE_FIELDS = BASE_UNSTABLE_FIELDS | WALL_DRAIN_FIELDS | {
    "replay_seq",
    "replay_ts",
    "seq",
    "quote_seq",
}

EXECUTION_UNSTABLE_FIELDS = BASE_UNSTABLE_FIELDS | WALL_DRAIN_FIELDS

PORTFOLIO_UNSTABLE_FIELDS = BASE_UNSTABLE_FIELDS | WALL_DRAIN_FIELDS

TRANSPORT_EQUIV_UNSTABLE_FIELDS = BASE_UNSTABLE_FIELDS | WALL_DRAIN_FIELDS | {
    "replay_seq",
    "replay_ts",
    "seq",
    "quote_seq",
    "arrival_seq",
    "effective_arrival_stream_seq",
    "drain_stream_seq",
    "arrival_stream_seq_override",
    "arrival_stream_lag_count",
    "feature_snapshot",
    "public_stream_mode",
    "public_batch_size",
    "public_batches_sent",
    "public_batch_max_span_us",
}

TRANSPORT_EQUIV_FLOAT_ROUND_DIGITS = 8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--allow-empty-orders", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"bad JSON at events.ndjson:{line_no}: {exc}") from exc
            event["_line_no"] = line_no
            events.append(event)
    return events


def payload(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("payload") or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def inner_payload(event: dict[str, Any]) -> dict[str, Any]:
    raw = payload(event)
    nested = raw.get("payload")
    return nested if isinstance(nested, dict) else raw


def intent_id(event: dict[str, Any]) -> int | None:
    raw = payload(event)
    nested = inner_payload(event)
    intent = raw.get("intent")
    candidates = [
        raw.get("intent_id"),
        nested.get("intent_id"),
        intent.get("intent_id") if isinstance(intent, dict) else None,
    ]
    for value in candidates:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def strip_unstable(
    value: Any,
    unstable_fields: set[str],
    *,
    float_round_digits: int | None = None,
) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_unstable(
                val,
                unstable_fields,
                float_round_digits=float_round_digits,
            )
            for key, val in sorted(value.items())
            if key not in unstable_fields
        }
    if isinstance(value, list):
        return [
            strip_unstable(
                item,
                unstable_fields,
                float_round_digits=float_round_digits,
            )
            for item in value
        ]
    if float_round_digits is not None and isinstance(value, float):
        if not math.isfinite(value):
            return value
        rounded = round(value, float_round_digits)
        return 0.0 if rounded == 0 else rounded
    return value


def stable_hash(
    items: Any,
    unstable_fields: set[str] | None = None,
    *,
    float_round_digits: int | None = None,
) -> str:
    payload = json.dumps(
        strip_unstable(
            items,
            unstable_fields or BASE_UNSTABLE_FIELDS,
            float_round_digits=float_round_digits,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def events_of_type(events: list[dict[str, Any]], event_types: set[str]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("event_type") in event_types]


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def validate_chain(intent: int, events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    types = [event.get("event_type") for event in events]
    order_positions = [CHAIN_ORDER.index(t) for t in types if t in CHAIN_ORDER]
    if order_positions != sorted(order_positions):
        errors.append(f"intent {intent}: chain order is not monotonic: {types}")

    by_type = {event.get("event_type"): event for event in events}
    for required in ("order_intent", "order_scheduled", "order_arrived"):
        if required not in by_type:
            errors.append(f"intent {intent}: missing {required}")

    if "order_ack" not in by_type and "order_reject" not in by_type and "risk_reject" not in by_type:
        errors.append(f"intent {intent}: missing terminal ack/reject")

    if "fill" in by_type and "order_ack" not in by_type:
        errors.append(f"intent {intent}: fill without order_ack")

    scheduled = payload(by_type["order_scheduled"]) if "order_scheduled" in by_type else {}
    arrived = payload(by_type["order_arrived"]) if "order_arrived" in by_type else {}
    if scheduled and arrived:
        target = scheduled.get("arrival_local_ts_us")
        observed = scheduled.get("observed_local_ts_us")
        actual_arrival = arrived.get("arrival_local_ts_us")
        effective = scheduled.get("effective_latency_us")
        if not finite_number(target) or not finite_number(observed):
            errors.append(f"intent {intent}: scheduled timestamps are not finite")
        elif int(target) < int(observed):
            errors.append(f"intent {intent}: arrival target before observed time")
        if finite_number(actual_arrival) and finite_number(target) and int(actual_arrival) < int(target):
            errors.append(f"intent {intent}: arrived before target latency")
        if finite_number(effective) and int(effective) < 0:
            errors.append(f"intent {intent}: negative effective latency")

    fill = inner_payload(by_type["fill"]) if "fill" in by_type else {}
    if fill:
        if not finite_number(fill.get("fill_price")):
            errors.append(f"intent {intent}: fill_price missing or non-finite")
        if not finite_number(fill.get("latency_slippage_bps")):
            errors.append(f"intent {intent}: latency_slippage_bps missing or non-finite")
        depth = fill.get("depth_sweep")
        if depth:
            for key in ("vwap", "filled_qty", "remaining_qty", "requested_qty", "levels_consumed"):
                if not finite_number(depth.get(key)):
                    errors.append(f"intent {intent}: depth_sweep.{key} missing or non-finite")
            if "reason" not in depth:
                errors.append(f"intent {intent}: depth_sweep.reason missing")
            if "partial_fill" not in depth:
                errors.append(f"intent {intent}: depth_sweep.partial_fill missing")

    return errors


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir
    events_path = run_dir / "events.ndjson"
    summary_path = run_dir / "summary.json"
    if not events_path.exists():
        raise SystemExit(f"missing {events_path}")
    if not summary_path.exists():
        raise SystemExit(f"missing {summary_path}")

    events = read_events(events_path)
    summary = read_json(summary_path)
    profile_path = run_dir / "profile_manifest.json"
    profile = read_json(profile_path) if profile_path.exists() else {}
    errors: list[str] = []

    if not events:
        errors.append("event log is empty")
    else:
        for expected, event in enumerate(events, 1):
            if event.get("event_id") != expected:
                errors.append(f"event_id gap at line {event.get('_line_no')}: expected {expected}, got {event.get('event_id')}")
        if events[0].get("event_type") != "run_start":
            errors.append("first compact event is not run_start")
        if events[-1].get("event_type") != "run_end":
            errors.append("last compact event is not run_end")

    expected_event_count = summary.get("event_count")
    if expected_event_count is not None and int(expected_event_count) != len(events):
        errors.append(f"summary event_count={expected_event_count} but log has {len(events)} events")

    chains: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        iid = intent_id(event)
        if iid is None:
            continue
        chains.setdefault(iid, []).append(event)

    if not chains and not args.allow_empty_orders:
        errors.append("no order chains found")

    for iid, chain_events in sorted(chains.items()):
        errors.extend(validate_chain(iid, chain_events))

    fill_events = [event for event in events if event.get("event_type") == "fill"]
    fills_created = summary.get("fills_created")
    if fills_created is not None and int(fills_created) != len(fill_events):
        errors.append(f"summary fills_created={fills_created} but log has {len(fill_events)} fill events")

    latency_profile = profile.get("latency_profile") if isinstance(profile, dict) else {}
    require_zero_lag = (
        isinstance(latency_profile, dict)
        and latency_profile.get("name") == "deterministic_replay_v1"
        and latency_profile.get("arrival_mode") == "timer"
        and int(latency_profile.get("latency_us") or 0) == 0
    )
    arrived_events = [event for event in events if event.get("event_type") == "order_arrived"]
    arrival_quote_lag_count = 0
    arrival_stream_lag_count = 0
    private_seq_mismatch_count = 0
    for event in arrived_events:
        raw = payload(event)
        quote_lag = raw.get("arrival_quote_lag")
        if quote_lag is None:
            arrival_quote = raw.get("arrival_quote") or {}
            observed_quote = raw.get("observed_quote") or {}
            quote_lag = int(arrival_quote.get("seq") or 0) - int(observed_quote.get("seq") or 0)
        stream_lag = raw.get("arrival_stream_lag") or 0
        if int(quote_lag) != 0:
            arrival_quote_lag_count += 1
            if require_zero_lag:
                errors.append(
                    f"intent {intent_id(event)}: deterministic zero-latency arrival_quote_lag={quote_lag}"
                )
        if int(stream_lag) != 0:
            arrival_stream_lag_count += 1

    private_seq_event_types = {"order_arrived", "order_ack", "order_reject", "fill"}
    for event in events:
        if event.get("event_type") not in private_seq_event_types:
            continue
        raw = payload(event)
        nested = inner_payload(event)
        effective_seq = nested.get("effective_arrival_stream_seq") or raw.get(
            "effective_arrival_stream_seq"
        )
        arrival_seq = nested.get("arrival_seq") or raw.get("arrival_seq")
        envelope_seq = raw.get("seq")
        if effective_seq is None or arrival_seq is None:
            continue
        seq_values = [int(effective_seq), int(arrival_seq)]
        if envelope_seq is not None:
            seq_values.append(int(envelope_seq))
        if len(set(seq_values)) != 1:
            private_seq_mismatch_count += 1
            if require_zero_lag:
                errors.append(
                    f"intent {intent_id(event)}: deterministic private seq mismatch {seq_values}"
                )

    decision_events = events_of_type(events, DECISION_EVENT_TYPES)
    execution_events = events_of_type(events, EXECUTION_EVENT_TYPES)
    portfolio_events = events_of_type(events, PORTFOLIO_EVENT_TYPES)
    decision_hash = stable_hash(decision_events, DECISION_UNSTABLE_FIELDS)
    execution_hash = stable_hash(execution_events, EXECUTION_UNSTABLE_FIELDS)
    portfolio_hash = stable_hash(portfolio_events, PORTFOLIO_UNSTABLE_FIELDS)
    transport_decision_hash = stable_hash(
        decision_events,
        TRANSPORT_EQUIV_UNSTABLE_FIELDS,
        float_round_digits=TRANSPORT_EQUIV_FLOAT_ROUND_DIGITS,
    )
    transport_execution_hash = stable_hash(
        execution_events,
        TRANSPORT_EQUIV_UNSTABLE_FIELDS,
        float_round_digits=TRANSPORT_EQUIV_FLOAT_ROUND_DIGITS,
    )
    transport_portfolio_hash = stable_hash(
        portfolio_events,
        TRANSPORT_EQUIV_UNSTABLE_FIELDS,
        float_round_digits=TRANSPORT_EQUIV_FLOAT_ROUND_DIGITS,
    )
    summary_account_hash = stable_hash(
        summary.get("final_account") or {},
        BASE_UNSTABLE_FIELDS,
    )
    transport_summary_account_hash = stable_hash(
        summary.get("final_account") or {},
        BASE_UNSTABLE_FIELDS,
        float_round_digits=TRANSPORT_EQUIV_FLOAT_ROUND_DIGITS,
    )

    result = {
        "ok": not errors,
        "run_dir": str(run_dir).replace("\\", "/"),
        "event_count": len(events),
        "profile_manifest_hash": profile.get("profile_manifest_hash") if isinstance(profile, dict) else None,
        "arrival_quote_lag_count": arrival_quote_lag_count,
        "arrival_stream_lag_count": arrival_stream_lag_count,
        "private_seq_mismatch_count": private_seq_mismatch_count,
        "decision_hash": decision_hash,
        "execution_hash": execution_hash,
        "portfolio_hash": portfolio_hash,
        "transport_decision_hash": transport_decision_hash,
        "transport_execution_hash": transport_execution_hash,
        "transport_float_round_digits": TRANSPORT_EQUIV_FLOAT_ROUND_DIGITS,
        "transport_portfolio_hash": transport_portfolio_hash,
        "summary_account_hash": summary_account_hash,
        "transport_summary_account_hash": transport_summary_account_hash,
        "deterministic_event_hash": stable_hash(
            decision_events + execution_events + portfolio_events,
            DECISION_UNSTABLE_FIELDS | EXECUTION_UNSTABLE_FIELDS | PORTFOLIO_UNSTABLE_FIELDS,
        ),
        "fill_chain_hash": stable_hash(fill_events, EXECUTION_UNSTABLE_FIELDS),
        "chains": {
            str(iid): [event.get("event_type") for event in chain_events]
            for iid, chain_events in sorted(chains.items())
        },
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
