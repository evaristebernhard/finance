"""Online TFI skeleton for the CCUSDT replay exchange stream.

The strategy intentionally reads only stdin NDJSON exchange-style events. It
does not import research scripts and does not read scored entries or labels.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from decision_frame import DecisionFrameBuilder
from execution_runtime import (
    CapacityLedger,
    EntrySpreadAdmissionGate,
    PositionLotLedger,
    STOPPING_RULE_HORIZONS_SEC,
    StoppingRuleParams,
    build_admission_gate,
    build_capacity_allocator,
    load_stopping_rule_params_for_date,
    stopping_rule_should_exit,
    taker_net_and_exit_cross_bps,
)
from online_features import OnlineFeatureState, OnlineTfiState
from shadow_policy import ShadowFourCellPolicy, add_shadow_args, build_shadow_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qty", type=float, default=10.0)
    parser.add_argument("--window-us", type=int, default=5_000_000)
    parser.add_argument("--closed-window", type=int, default=5)
    parser.add_argument("--tfi-threshold", type=float, default=0.8)
    parser.add_argument("--min-trades", type=int, default=3)
    parser.add_argument("--min-qty", type=float, default=0.0)
    parser.add_argument("--cooldown-us", type=int, default=30_000_000)
    parser.add_argument("--max-orders", type=int, default=1)
    parser.add_argument("--sparse-output", action="store_true")
    parser.add_argument("--heartbeat-interval-us", type=int, default=10_000_000)
    parser.add_argument("--decision-clock", choices=["quote", "panel"], default="quote")
    parser.add_argument("--decision-trade-window-us", type=int, default=2_000_000)
    parser.add_argument("--shadow-state-in", type=Path)
    parser.add_argument("--shadow-state-out", type=Path)
    parser.add_argument("--shadow-trade-entries", action="store_true")
    parser.add_argument("--shadow-trade-exits", action="store_true")
    parser.add_argument("--shadow-entry-notional", type=float, default=1.0)
    parser.add_argument("--shadow-leverage-cap", type=float, default=3.0)
    parser.add_argument("--shadow-capacity-profile", choices=["fifo_clip", "core_idle01"], default="fifo_clip")
    parser.add_argument("--shadow-idle01-gamma", type=float)
    parser.add_argument("--shadow-idle01-reserve", type=float, default=0.0)
    parser.add_argument(
        "--shadow-exit-profile",
        choices=["fixed60_taker", "peakguard_taker_v1", "stopping_rule_v1"],
        default="fixed60_taker",
    )
    parser.add_argument("--shadow-stopping-rule-params-json", type=Path)
    parser.add_argument(
        "--shadow-admission-profile",
        choices=["none", "entry_spread_q70_v1"],
        default="none",
    )
    parser.add_argument("--shadow-admission-entry-cross-threshold-bps", type=float)
    parser.add_argument("--shadow-admission-threshold-source", default="")
    parser.add_argument("--shadow-admission-thresholds-json", type=Path)
    parser.add_argument("--shadow-admission-date")
    add_shadow_args(parser)
    return parser.parse_args()


def heartbeat(
    observed_seq: int | None,
    reason: str = "heartbeat",
    feature_snapshot: dict | None = None,
    shadow_signal: dict | None = None,
) -> dict:
    out: dict = {"type": "heartbeat", "reason": reason}
    if observed_seq is not None:
        out["observed_seq"] = observed_seq
    if feature_snapshot is not None:
        out["feature_snapshot"] = feature_snapshot
    if shadow_signal is not None:
        out["shadow_signal"] = shadow_signal
    return out


def hold(observed_seq: int | None, reason: str, feature_snapshot: dict | None = None) -> dict:
    out: dict = {"type": "hold", "reason": reason}
    if observed_seq is not None:
        out["observed_seq"] = observed_seq
    if feature_snapshot is not None:
        out["feature_snapshot"] = feature_snapshot
    return out


def is_actionable_response(response: dict | None) -> bool:
    if response is None:
        return False
    return response.get("type") in {"submit_order", "submit_orders", "cancel_order"}


def attach_barrier_consumed(
    response: dict,
    event: dict,
    consumed_count: int,
    total_count: int,
    schema_id: str = "batched_public_barrier_v1",
) -> dict:
    observed_seq = event.get("observed_seq", event.get("seq"))
    local_ts_us = event.get("local_ts_us")
    if observed_seq is not None:
        response.setdefault("observed_seq", int(observed_seq))
        response["consumed_seq"] = int(observed_seq)
    if local_ts_us is not None:
        response.setdefault("observed_local_ts_us", int(local_ts_us))
        response["consumed_local_ts_us"] = int(local_ts_us)
    response["transport_barrier"] = {
        "schema_id": schema_id,
        "consumed_event_count": consumed_count,
        "remaining_event_count": max(0, total_count - consumed_count),
    }
    return response


def submit_order(
    observed_seq: int,
    observed_local_ts_us: int,
    side: str,
    qty: float,
    client_order_id: str,
    reason: str,
    feature_snapshot: dict,
    shadow_signal: dict | None = None,
) -> dict:
    out = {
        "type": "submit_order",
        "observed_seq": observed_seq,
        "observed_local_ts_us": observed_local_ts_us,
        "side": side,
        "kind": "market",
        "qty": qty,
        "tif": "ioc",
        "reduce_only": False,
        "client_order_id": client_order_id,
        "reason": reason,
        "feature_snapshot": feature_snapshot,
    }
    if shadow_signal is not None:
        out["shadow_signal"] = shadow_signal
    return out


def submit_orders(
    observed_seq: int,
    observed_local_ts_us: int,
    orders: list[dict],
    reason: str,
    feature_snapshot: dict,
    shadow_signal: dict | None = None,
) -> dict:
    out = {
        "type": "submit_orders",
        "observed_seq": observed_seq,
        "observed_local_ts_us": observed_local_ts_us,
        "orders": orders,
        "reason": reason,
        "feature_snapshot": feature_snapshot,
    }
    if shadow_signal is not None:
        out["shadow_signal"] = shadow_signal
    return out


def order_request(
    *,
    side: str,
    qty: float,
    client_order_id: str,
    reduce_only: bool = False,
) -> dict:
    return {
        "side": side,
        "kind": "market",
        "qty": qty,
        "tif": "ioc",
        "reduce_only": reduce_only,
        "client_order_id": client_order_id,
    }


def optional_float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def frame_bid_ask_mid(frame: dict) -> tuple[float | None, float | None, float | None]:
    quote = frame.get("_execution_quote") or {}
    bid = optional_float(
        quote.get("bid")
        or frame.get("best_bid_price")
        or frame.get("bid_px")
        or frame.get("bid")
    )
    ask = optional_float(
        quote.get("ask")
        or frame.get("best_ask_price")
        or frame.get("ask_px")
        or frame.get("ask")
    )
    mid = optional_float(quote.get("mid") or frame.get("mid_price") or frame.get("mid"))
    if mid is None and bid is not None and ask is not None:
        mid = 0.5 * (bid + ask)
    return bid, ask, mid


def attach_execution_quote(frame: dict, payload: dict) -> dict:
    audit = payload.get("audit") or {}
    quote = audit.get("execution_quote") or audit.get("quote") or {}
    if not isinstance(quote, dict) or not quote:
        return frame
    out = dict(frame)
    out["_execution_quote"] = quote
    return out


def read_admission_threshold_for_bot(args: argparse.Namespace) -> tuple[float | None, str | None]:
    if not args.shadow_admission_thresholds_json:
        return args.shadow_admission_entry_cross_threshold_bps, args.shadow_admission_threshold_source or None
    if not args.shadow_admission_date:
        raise ValueError("--shadow-admission-date is required with --shadow-admission-thresholds-json")
    with args.shadow_admission_thresholds_json.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    rows = raw.get("thresholds", raw) if isinstance(raw, dict) else {}
    row = rows.get(args.shadow_admission_date) if isinstance(rows, dict) else None
    if isinstance(row, dict):
        threshold = optional_float(
            row.get("entry_cross_threshold_bps")
            if "entry_cross_threshold_bps" in row
            else row.get("threshold_bps")
        )
        source = row.get("threshold_source") or row.get("source")
    else:
        threshold = optional_float(row)
        source = None
    if threshold is None:
        raise ValueError(f"missing admission threshold for {args.shadow_admission_date}")
    return threshold, str(source or f"{args.shadow_admission_thresholds_json.name}:{args.shadow_admission_date}")


def build_strategy_admission_gate(args: argparse.Namespace) -> EntrySpreadAdmissionGate:
    threshold, source = read_admission_threshold_for_bot(args)
    return build_admission_gate(
        admission_profile=args.shadow_admission_profile,
        entry_cross_threshold_bps=threshold,
        threshold_source=source,
    )


class PeakguardPosition:
    def __init__(
        self,
        shadow_signal: dict,
        entry_mid: float,
        *,
        entry_bid: float | None = None,
        entry_ask: float | None = None,
        stopping_params: StoppingRuleParams | None = None,
    ) -> None:
        self.position_id = int(shadow_signal["shadow_position_id"])
        self.entry_seq = shadow_signal.get("observed_seq")
        self.entry_ts_us = int(shadow_signal.get("entry_ts_us") or shadow_signal.get("local_ts_us") or 0)
        self.due_ts_us = int(shadow_signal.get("entry_due_ts_us") or (self.entry_ts_us + 60_000_000))
        self.entry_mid = float(entry_mid)
        self.entry_bid = entry_bid
        self.entry_ask = entry_ask
        self.direction = int(shadow_signal.get("direction") or 0)
        self.side = str(shadow_signal.get("side") or "")
        self.cell = str(shadow_signal.get("cell") or "")
        self.membership_set = str(shadow_signal.get("membership_set") or "")
        self.trigger_classes = list(shadow_signal.get("trigger_classes") or [])
        self.base_weight = shadow_signal.get("base_weight")
        self.weak_overlay_weight = shadow_signal.get("weak_overlay_weight")
        self.gamma = shadow_signal.get("gamma")
        self.target_exposure = shadow_signal.get("target_exposure")
        self.entry_spread_bps = shadow_signal.get("entry_spread_bps")
        self.stopping_params = stopping_params
        self.h_bps = -math.inf
        self.peak_sec = math.nan
        self.last_evaluated_horizon_index = -1
        self.mid_history: list[tuple[int, float]] = []

    def update(self, frame: dict, observed_seq: int | None, exit_profile: str) -> dict | None:
        if self.direction == 0 or self.entry_mid <= 0.0:
            return None
        local_ts_us = int(frame.get("local_ts_us") or frame.get("local_timestamp") or 0)
        if local_ts_us <= self.entry_ts_us or local_ts_us >= self.due_ts_us:
            return None
        bid, ask, mid = frame_bid_ask_mid(frame)
        if mid is None or mid <= 0.0:
            return None
        hold_sec = (local_ts_us - self.entry_ts_us) / 1_000_000.0
        ret = self.direction * math.log(mid / self.entry_mid) * 10_000.0
        self.mid_history.append((local_ts_us, mid))
        if exit_profile == "stopping_rule_v1":
            return self._stopping_rule_update(
                frame=frame,
                observed_seq=observed_seq,
                local_ts_us=local_ts_us,
                hold_sec=hold_sec,
                ret=ret,
                mid=mid,
                bid=bid,
                ask=ask,
            )
        if self.cell != "11_r5_frames":
            return None
        if ret > self.h_bps + 1e-12:
            self.h_bps = ret
            self.peak_sec = hold_sec
        drawdown = self.h_bps - ret
        if self.h_bps < 4.0:
            return None
        if self.h_bps < 8.0 and self.peak_sec < 1.5:
            return None
        threshold = max(2.0, 0.35 * self.h_bps)
        if drawdown < threshold:
            return None
        return {
            "shadow_position_id": self.position_id,
            "entry_seq": self.entry_seq,
            "close_seq": observed_seq,
            "entry_ts_us": self.entry_ts_us,
            "due_ts_us": self.due_ts_us,
            "close_ts_us": local_ts_us,
            "held_us": local_ts_us - self.entry_ts_us,
            "exit_lag_us": local_ts_us - self.due_ts_us,
            "entry_mid": self.entry_mid,
            "close_mid": mid,
            "direction": self.direction,
            "side": self.side,
            "direction_label": "long" if self.direction > 0 else "short",
            "pnl_bps": ret,
            "trigger_classes": self.trigger_classes,
            "membership_set": self.membership_set,
            "cell": self.cell,
            "base_weight": self.base_weight,
            "weak_overlay_weight": self.weak_overlay_weight,
            "gamma": self.gamma,
            "target_exposure": self.target_exposure,
            "entry_spread_bps": self.entry_spread_bps,
            "exit_reason": "release_drawdown",
            "exit_profile": "peakguard_taker_v1",
            "H_exit": self.h_bps,
            "D_exit": drawdown,
            "tau_H_exit": self.peak_sec,
            "exit_threshold": threshold,
        }

    def _stopping_rule_update(
        self,
        *,
        frame: dict,
        observed_seq: int | None,
        local_ts_us: int,
        hold_sec: float,
        ret: float,
        mid: float,
        bid: float | None,
        ask: float | None,
    ) -> dict | None:
        if self.stopping_params is None:
            return None
        elapsed_count = 0
        while (
            elapsed_count < len(STOPPING_RULE_HORIZONS_SEC)
            and hold_sec + 1e-9 >= STOPPING_RULE_HORIZONS_SEC[elapsed_count]
        ):
            elapsed_count += 1
        current_index = elapsed_count - 1
        if current_index < 0 or current_index <= self.last_evaluated_horizon_index:
            return None
        self.last_evaluated_horizon_index = current_index
        current_horizon = STOPPING_RULE_HORIZONS_SEC[current_index]
        taker_net, exit_cross = taker_net_and_exit_cross_bps(
            entry_side=self.side,
            entry_bid=self.entry_bid,
            entry_ask=self.entry_ask,
            current_bid=bid,
            current_ask=ask,
            current_mid=mid,
        )
        if taker_net is None or exit_cross is None:
            return None
        if taker_net > self.h_bps + 1e-12:
            self.h_bps = taker_net
            self.peak_sec = hold_sec
        drawdown = self.h_bps - taker_net
        recent_mid_alpha = self._recent_mid_alpha_5s(local_ts_us, mid)
        if not stopping_rule_should_exit(
            high_bps=self.h_bps,
            drawdown_bps=drawdown,
            exit_cross_bps=exit_cross,
            recent_mid_alpha_5s_bps=recent_mid_alpha,
            params=self.stopping_params,
        ):
            return None
        return {
            "shadow_position_id": self.position_id,
            "entry_seq": self.entry_seq,
            "close_seq": observed_seq,
            "entry_ts_us": self.entry_ts_us,
            "due_ts_us": self.due_ts_us,
            "close_ts_us": local_ts_us,
            "held_us": local_ts_us - self.entry_ts_us,
            "exit_lag_us": local_ts_us - self.due_ts_us,
            "entry_mid": self.entry_mid,
            "close_mid": mid,
            "direction": self.direction,
            "side": self.side,
            "direction_label": "long" if self.direction > 0 else "short",
            "pnl_bps": ret,
            "trigger_classes": self.trigger_classes,
            "membership_set": self.membership_set,
            "cell": self.cell,
            "base_weight": self.base_weight,
            "weak_overlay_weight": self.weak_overlay_weight,
            "gamma": self.gamma,
            "target_exposure": self.target_exposure,
            "entry_spread_bps": self.entry_spread_bps,
            "exit_reason": "stopping_rule",
            "exit_profile": "stopping_rule_v1",
            "exit_grid_sec": current_horizon,
            "H_exit": self.h_bps,
            "D_exit": drawdown,
            "tau_H_exit": self.peak_sec,
            "exit_threshold": max(self.stopping_params.d0, self.stopping_params.rho * max(self.h_bps, 0.0)),
            "exit_cross_bps": exit_cross,
            "policy_taker_net_bps": taker_net,
            "recent_mid_alpha_5s_bps": recent_mid_alpha,
            "stopping_rule_params": self.stopping_params.to_dict(),
        }

    def _recent_mid_alpha_5s(self, local_ts_us: int, mid: float) -> float:
        target = local_ts_us - 5_000_000
        previous_mid = self.mid_history[0][1] if self.mid_history else mid
        for ts, value in self.mid_history:
            if ts <= target:
                previous_mid = value
            else:
                break
        if previous_mid <= 0.0 or mid <= 0.0:
            return 0.0
        return self.direction * math.log(mid / previous_mid) * 10_000.0


class PeakguardExitManager:
    def __init__(
        self,
        enabled: bool,
        *,
        exit_profile: str = "fixed60_taker",
        stopping_params: StoppingRuleParams | None = None,
    ) -> None:
        self.enabled = enabled
        self.exit_profile = exit_profile
        self.stopping_params = stopping_params
        self.positions: dict[int, PeakguardPosition] = {}

    def register_entry(self, shadow_signal: dict, frame: dict | None, mid: float | None) -> None:
        if not self.enabled or mid is None or mid <= 0.0:
            return
        try:
            position_id = int(shadow_signal["shadow_position_id"])
        except (KeyError, TypeError, ValueError):
            return
        if float(shadow_signal.get("actual_exposure") or 0.0) <= 0.0:
            return
        bid, ask, frame_mid = frame_bid_ask_mid(frame or {})
        self.positions[position_id] = PeakguardPosition(
            shadow_signal,
            float(frame_mid or mid),
            entry_bid=bid,
            entry_ask=ask,
            stopping_params=self.stopping_params,
        )

    def unregister(self, position_id: int) -> None:
        self.positions.pop(int(position_id), None)

    def on_frame(self, frame: dict, observed_seq: int | None) -> dict | None:
        if not self.enabled or not self.positions:
            return None
        closed_now: list[dict] = []
        for position_id, position in list(self.positions.items()):
            close = position.update(frame, observed_seq, self.exit_profile)
            if close is not None:
                closed_now.append(close)
                self.positions.pop(position_id, None)
        if not closed_now:
            return None
        local_ts_us = int(frame.get("local_ts_us") or frame.get("local_timestamp") or 0)
        return {
            "schema_id": "ccusdt_shadow_four_cell_signal_v1",
            "runtime_safe": True,
            "event_kind": "shadow_lifecycle_close",
            "policy": "old_tfi_four_cell_shadow_v1",
            "observed_seq": observed_seq,
            "local_ts_us": local_ts_us,
            "closed_now": closed_now,
            "closed_outcomes": None,
            "pending_shadow_entries": None,
            "exit_profile": self.exit_profile,
        }


def runtime_profiles(args: argparse.Namespace) -> dict:
    return {
        "schema_id": "ccusdt_strategy_run_profiles_v1",
        "policy_profile": {
            "name": "old_tfi_four_cell_shadow_v1" if args.shadow_four_cell else "online_tfi_skeleton_v1",
            "decision_clock": args.decision_clock,
            "gamma_preset": args.shadow_gamma_preset,
            "gamma01_override": args.shadow_gamma01_override,
            "frames_threshold": args.shadow_frames_threshold,
            "overlay_threshold": args.shadow_overlay_threshold,
            "r5_threshold": args.shadow_r5_threshold,
            "bucket_us": args.shadow_bucket_us,
            "fixed_exit_us": args.shadow_fixed_exit_us,
        },
        "capacity_profile": {
            "name": args.shadow_capacity_profile,
            "leverage_cap": args.shadow_leverage_cap,
            "idle01_gamma": args.shadow_idle01_gamma,
            "idle01_reserve": args.shadow_idle01_reserve,
            "admission_profile": args.shadow_admission_profile,
            "admission_entry_cross_threshold_bps": args.shadow_admission_entry_cross_threshold_bps,
            "admission_threshold_source": args.shadow_admission_threshold_source or None,
            "admission_thresholds_json": (
                str(args.shadow_admission_thresholds_json)
                if args.shadow_admission_thresholds_json
                else None
            ),
            "admission_date": args.shadow_admission_date,
            "core_cells": ["00_none", "10_r5_only", "11_r5_frames"],
            "idle_cell": "01_frames_only" if args.shadow_capacity_profile == "core_idle01" else None,
        },
        "exit_profile": {
            "name": args.shadow_exit_profile,
            "fixed_exit_us": args.shadow_fixed_exit_us,
            "manager_path_policy": (
                "pm_11_drawdown_h4_peakguard"
                if args.shadow_exit_profile == "peakguard_taker_v1"
                else None
            ),
            "stopping_rule_params_json": (
                str(args.shadow_stopping_rule_params_json)
                if args.shadow_stopping_rule_params_json
                else None
            ),
        },
        "fill_profile": {
            "name": "top_of_book_taker_ioc_v1",
            "fee_bps": 0.0,
        },
        "latency_profile": {
            "name": "runner_configured_latency",
        },
    }


def apply_capacity_decision(
    shadow_signal: dict,
    capacity_ledger: CapacityLedger,
    admission_gate: EntrySpreadAdmissionGate,
) -> dict:
    admission = admission_gate.decide(shadow_signal).to_dict()
    shadow_signal["admission_decision"] = admission
    if admission["accepted"]:
        decision = capacity_ledger.decide(shadow_signal).to_dict()
    else:
        decision = capacity_ledger.reject_decision(shadow_signal, capacity_source="admission_reject").to_dict()
    shadow_signal["capacity_decision"] = decision
    shadow_signal["admission_profile"] = admission.get("admission_profile")
    shadow_signal["admission_accepted"] = admission.get("accepted")
    shadow_signal["admission_reason"] = admission.get("reason")
    shadow_signal["entry_cross_bps"] = admission.get("entry_cross_bps")
    shadow_signal["admission_entry_cross_threshold_bps"] = admission.get("entry_cross_threshold_bps")
    shadow_signal["admission_threshold_source"] = admission.get("threshold_source")
    shadow_signal["requested_exposure"] = decision["requested_exposure"]
    shadow_signal["actual_exposure"] = decision["actual_exposure"]
    shadow_signal["clipped_exposure"] = decision["clipped_exposure"]
    shadow_signal["skipped"] = decision["skipped"]
    shadow_signal["open_exposure_before"] = decision["open_exposure_before"]
    shadow_signal["open_exposure_after"] = decision["open_exposure_after"]
    shadow_signal["leverage_cap"] = decision["leverage_cap"]
    shadow_signal["capacity_profile"] = decision.get("capacity_profile")
    shadow_signal["capacity_source"] = decision.get("capacity_source")
    shadow_signal["idle_capacity_before"] = decision.get("idle_capacity_before")
    shadow_signal["core_displacement"] = decision.get("core_displacement")
    shadow_signal["capacity_reserve"] = decision.get("reserve")
    return decision


def build_shadow_order_response(
    args: argparse.Namespace,
    observed_seq: int | None,
    local_ts_us: int,
    shadow_signal: dict,
    feature_snapshot: dict,
    mid: float | None,
    capacity_ledger: CapacityLedger,
    lot_ledger: PositionLotLedger,
    admission_gate: EntrySpreadAdmissionGate,
    exit_manager: PeakguardExitManager | None = None,
) -> dict | None:
    if observed_seq is None:
        return None

    orders: list[dict] = []
    closed_now = shadow_signal.get("closed_now") or []
    for close in closed_now:
        position_id = close.get("shadow_position_id")
        if position_id is None:
            continue
        if exit_manager is not None:
            exit_manager.unregister(int(position_id))
        released = capacity_ledger.close(int(position_id))
        close["actual_exposure"] = released
        close["capacity_released_exposure"] = released
        lot = lot_ledger.open_lot(int(position_id))
        if lot is not None:
            close["position_lot"] = lot.to_dict()
        if not args.shadow_trade_exits:
            continue
        qty = lot_ledger.exit_order_qty(int(position_id))
        if released <= 0.0 or qty <= 0.0:
            continue
        direction = int(close.get("direction") or 0)
        if direction == 0:
            continue
        orders.append(
            order_request(
                side="sell" if direction > 0 else "buy",
                qty=qty,
                client_order_id=f"shadow-exit-{position_id}",
                # The current paper exchange is net-position based, while this
                # strategy manages independent shadow lots. Lot-level qty control
                # is the reduce guard here; exchange reduce_only would reject
                # valid hedged-lot closes when net position is near flat.
                reduce_only=False,
            )
        )

    if shadow_signal.get("event_kind") == "shadow_entry":
        decision = apply_capacity_decision(shadow_signal, capacity_ledger, admission_gate)
        actual_exposure = float(decision["actual_exposure"])
        if exit_manager is not None:
            exit_manager.register_entry(
                shadow_signal,
                feature_snapshot.get("decision_frame") if isinstance(feature_snapshot, dict) else None,
                mid,
            )
        if args.shadow_trade_entries and mid is not None and mid > 0.0 and actual_exposure > 0.0:
            position_id = shadow_signal.get("shadow_position_id")
            qty = actual_exposure * max(0.0, float(args.shadow_entry_notional)) / float(mid)
            if qty > 0.0:
                client_order_id = f"shadow-entry-{position_id}"
                lot_ledger.register_entry_order(client_order_id, shadow_signal, decision)
                orders.append(
                    order_request(
                        side=str(shadow_signal.get("side") or ""),
                        qty=qty,
                        client_order_id=client_order_id,
                    )
                )

    feature_snapshot["shadow_signal"] = shadow_signal
    feature_snapshot["run_profiles"] = runtime_profiles(args)
    feature_snapshot["capacity_ledger"] = capacity_ledger.snapshot()
    feature_snapshot["position_lot_ledger"] = lot_ledger.compact_snapshot()
    if not orders:
        if shadow_signal.get("event_kind") == "shadow_entry" or closed_now:
            return heartbeat(
                int(observed_seq),
                "capacity_decision",
                feature_snapshot,
                shadow_signal,
            )
        return None
    return submit_orders(
        observed_seq=int(observed_seq),
        observed_local_ts_us=local_ts_us,
        orders=orders,
        reason=f"shadow_four_cell_capacity_orders count={len(orders)}",
        feature_snapshot=feature_snapshot,
        shadow_signal=shadow_signal,
    )


def maybe_shadow_entry_order(
    args: argparse.Namespace,
    observed_seq: int | None,
    local_ts_us: int,
    shadow_signal: dict,
    feature_snapshot: dict,
    mid: float | None,
) -> dict | None:
    if not args.shadow_trade_entries:
        return None
    if shadow_signal.get("event_kind") != "shadow_entry":
        return None
    if observed_seq is None or mid is None or mid <= 0.0:
        return None
    target_exposure = float(shadow_signal.get("target_exposure") or 0.0)
    if target_exposure <= 0.0:
        return None
    notional = target_exposure * max(0.0, float(args.shadow_entry_notional))
    qty = notional / mid
    if qty <= 0.0:
        return None
    position_id = shadow_signal.get("shadow_position_id")
    return submit_order(
        observed_seq=int(observed_seq),
        observed_local_ts_us=local_ts_us,
        side=str(shadow_signal.get("side") or ""),
        qty=qty,
        client_order_id=f"shadow-entry-{position_id}",
        reason=(
            "shadow_four_cell_entry_taker_ioc "
            f"position_id={position_id} cell={shadow_signal.get('cell')}"
        ),
        feature_snapshot=feature_snapshot,
        shadow_signal=shadow_signal,
    )


def maybe_shadow_exit_orders(
    args: argparse.Namespace,
    observed_seq: int | None,
    local_ts_us: int,
    shadow_signal: dict,
    feature_snapshot: dict,
) -> dict | None:
    if not args.shadow_trade_exits:
        return None
    if shadow_signal.get("event_kind") != "shadow_lifecycle_close":
        return None
    if observed_seq is None:
        return None
    orders = []
    for close in shadow_signal.get("closed_now") or []:
        target_exposure = float(close.get("target_exposure") or 0.0)
        close_mid = float(close.get("close_mid") or 0.0)
        if target_exposure <= 0.0 or close_mid <= 0.0:
            continue
        direction = int(close.get("direction") or 0)
        if direction == 0:
            continue
        position_id = close.get("shadow_position_id")
        orders.append(
            {
                "side": "sell" if direction > 0 else "buy",
                "kind": "market",
                "qty": target_exposure * max(0.0, float(args.shadow_entry_notional)) / close_mid,
                "tif": "ioc",
                "reduce_only": False,
                "client_order_id": f"shadow-exit-{position_id}",
            }
        )
    if not orders:
        return None
    return submit_orders(
        observed_seq=int(observed_seq),
        observed_local_ts_us=local_ts_us,
        orders=orders,
        reason=f"shadow_four_cell_fixed60_exit_batch count={len(orders)}",
        feature_snapshot=feature_snapshot,
        shadow_signal=shadow_signal,
    )


def checkpoint(
    state: OnlineFeatureState,
    observed_seq: int | None,
    local_ts_us: int | None,
    checkpoint_type: str,
) -> dict:
    return state.snapshot(observed_seq, local_ts_us, checkpoint_type)


def json_safe(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value


def maybe_heartbeat(
    observed_seq: int | None,
    local_ts_us: int,
    state: OnlineFeatureState,
    args: argparse.Namespace,
) -> dict | None:
    if not args.sparse_output:
        return heartbeat(
            observed_seq,
            "heartbeat",
            checkpoint(state, observed_seq, local_ts_us, "heartbeat_dense"),
        )
    if (
        state.last_heartbeat_local_ts_us is None
        or local_ts_us - state.last_heartbeat_local_ts_us >= args.heartbeat_interval_us
    ):
        state.last_heartbeat_local_ts_us = local_ts_us
        return heartbeat(
            observed_seq,
            "heartbeat_interval",
            checkpoint(state, observed_seq, local_ts_us, "heartbeat_interval"),
        )
    return None


def maybe_peakguard_exit_response(
    *,
    args: argparse.Namespace,
    observed_seq: int | None,
    local_ts_us: int,
    frame: dict,
    state: OnlineFeatureState,
    capacity_ledger: CapacityLedger | None,
    lot_ledger: PositionLotLedger | None,
    admission_gate: EntrySpreadAdmissionGate | None,
    exit_manager: PeakguardExitManager | None,
) -> dict | None:
    if (
        args.shadow_exit_profile not in {"peakguard_taker_v1", "stopping_rule_v1"}
        or exit_manager is None
        or capacity_ledger is None
        or lot_ledger is None
        or admission_gate is None
    ):
        return None
    shadow_signal = exit_manager.on_frame(frame, observed_seq)
    if shadow_signal is None:
        return None
    checkpoint_name = (
        "shadow_stopping_rule_lifecycle_close"
        if args.shadow_exit_profile == "stopping_rule_v1"
        else "shadow_peakguard_lifecycle_close"
    )
    snap = checkpoint(state, observed_seq, local_ts_us, checkpoint_name)
    snap["decision_frame"] = frame
    snap["shadow_signal"] = shadow_signal
    return build_shadow_order_response(
        args,
        observed_seq,
        local_ts_us,
        shadow_signal,
        snap,
        frame.get("mid_price") or frame.get("mid"),
        capacity_ledger,
        lot_ledger,
        admission_gate,
        exit_manager,
    )


def maybe_decide(
    message: dict,
    state: OnlineFeatureState,
    args: argparse.Namespace,
    shadow_policy: ShadowFourCellPolicy | None = None,
    decision_builder: DecisionFrameBuilder | None = None,
    capacity_ledger: CapacityLedger | None = None,
    lot_ledger: PositionLotLedger | None = None,
    admission_gate: EntrySpreadAdmissionGate | None = None,
    exit_manager: PeakguardExitManager | None = None,
) -> dict | None:
    message_type = message.get("type")
    observed_seq = message.get("observed_seq", message.get("seq"))
    local_ts_us = int(message.get("local_ts_us") or 0)
    payload = message.get("payload") or {}
    state.observe_envelope(message)

    if message_type == "market_trade":
        trade = payload.get("trade") or {}
        state.add_trade(
            local_ts_us=int(trade.get("local_ts_us") or local_ts_us),
            side=str(trade.get("side") or ""),
            qty=float(trade.get("qty") or 0.0),
            price=float(trade.get("price") or 0.0),
        )
        if decision_builder is not None:
            decision_builder.observe_trade(trade, fallback_local_ts_us=local_ts_us)
    elif message_type == "market_quote":
        state.update_quote(payload.get("quote") or {})
    elif message_type in {"account_snapshot", "order_reject", "fill"}:
        state.update_private(message_type, payload)
        if message_type == "fill":
            execution_event = lot_ledger.on_fill(payload) if lot_ledger is not None else None
            snap = checkpoint(state, observed_seq, local_ts_us, "fill")
            if execution_event is not None:
                snap["execution_event"] = execution_event
                snap["position_lot_ledger"] = (
                    lot_ledger.compact_snapshot() if lot_ledger is not None else None
                )
            return heartbeat(
                observed_seq,
                "private_fill_seen",
                snap,
            )
        if not args.sparse_output:
            return heartbeat(
                observed_seq,
                f"private_{message_type}_seen",
                checkpoint(state, observed_seq, local_ts_us, f"private_{message_type}"),
            )
        return None
    elif message_type in {"session_start", "session_end", "order_ack"}:
        if message_type == "order_ack" and lot_ledger is not None:
            lot_ledger.on_order_ack(payload)
        if not args.sparse_output:
            return heartbeat(
                observed_seq,
                f"{message_type}_seen",
                checkpoint(state, observed_seq, local_ts_us, message_type),
            )
        return None
    elif message_type == "market_l2_update":
        state.update_l2(payload)
        if args.decision_clock == "panel" and decision_builder is not None:
            frame = decision_builder.build_from_l2_payload(
                payload,
                observed_seq=observed_seq,
                fallback_local_ts_us=local_ts_us,
            )
            if frame is not None:
                peakguard_response = maybe_peakguard_exit_response(
                    args=args,
                    observed_seq=observed_seq,
                    local_ts_us=local_ts_us,
                    frame=frame,
                    state=state,
                    capacity_ledger=capacity_ledger,
                    lot_ledger=lot_ledger,
                    admission_gate=admission_gate,
                    exit_manager=exit_manager,
                )
                if peakguard_response is not None:
                    return peakguard_response
            if frame is not None and shadow_policy is not None:
                shadow_signal = shadow_policy.on_decision_frame(frame, observed_seq)
                if shadow_signal is not None:
                    event_kind = shadow_signal.get("event_kind", "shadow_entry")
                    checkpoint_type = (
                        "shadow_four_cell_panel_trigger"
                        if event_kind == "shadow_entry"
                        else "shadow_panel_lifecycle_close"
                    )
                    reason = checkpoint_type
                    snap = checkpoint(state, observed_seq, local_ts_us, checkpoint_type)
                    snap["decision_frame"] = frame
                    if event_kind == "shadow_entry":
                        snap["four_cell_inputs"].update(
                            {
                                "a_r5_gt_1": shadow_signal["a_r5_gt_1"],
                                "r5": shadow_signal["a_r5_raw"],
                                "r5_ready": shadow_signal["a_r5_ready"],
                                "b_threshold": shadow_signal["b_threshold"],
                                "b_frames_ge_threshold": shadow_signal["b_frames_ge_q90"],
                                "cell": shadow_signal["cell"],
                            }
                        )
                    snap["shadow_signal"] = shadow_signal
                    if capacity_ledger is not None and lot_ledger is not None and admission_gate is not None:
                        order_response = build_shadow_order_response(
                            args,
                            observed_seq,
                            local_ts_us,
                            shadow_signal,
                            snap,
                            frame.get("mid_price") or frame.get("mid"),
                            capacity_ledger,
                            lot_ledger,
                            admission_gate,
                            exit_manager,
                        )
                        if order_response is not None:
                            return order_response
                    return heartbeat(observed_seq, reason, snap, shadow_signal)
            return maybe_heartbeat(observed_seq, local_ts_us, state, args)
        return maybe_heartbeat(observed_seq, local_ts_us, state, args)
    elif message_type == "market_decision_frame":
        frame = payload.get("decision_frame") or payload.get("frame") or payload
        frame = attach_execution_quote(frame, payload)
        peakguard_response = maybe_peakguard_exit_response(
            args=args,
            observed_seq=observed_seq,
            local_ts_us=local_ts_us,
            frame=frame,
            state=state,
            capacity_ledger=capacity_ledger,
            lot_ledger=lot_ledger,
            admission_gate=admission_gate,
            exit_manager=exit_manager,
        )
        if peakguard_response is not None:
            return peakguard_response
        if shadow_policy is not None:
            shadow_signal = shadow_policy.on_decision_frame(frame, observed_seq)
            if shadow_signal is not None:
                event_kind = shadow_signal.get("event_kind", "shadow_entry")
                checkpoint_type = (
                    "shadow_four_cell_panel_trigger"
                    if event_kind == "shadow_entry"
                    else "shadow_panel_lifecycle_close"
                )
                snap = checkpoint(state, observed_seq, local_ts_us, checkpoint_type)
                snap["decision_frame"] = frame
                if event_kind == "shadow_entry":
                    snap["four_cell_inputs"].update(
                        {
                            "a_r5_gt_1": shadow_signal["a_r5_gt_1"],
                            "r5": shadow_signal["a_r5_raw"],
                            "r5_ready": shadow_signal["a_r5_ready"],
                            "b_threshold": shadow_signal["b_threshold"],
                            "b_frames_ge_threshold": shadow_signal["b_frames_ge_q90"],
                            "cell": shadow_signal["cell"],
                        }
                    )
                snap["shadow_signal"] = shadow_signal
                if capacity_ledger is not None and lot_ledger is not None and admission_gate is not None:
                    order_response = build_shadow_order_response(
                        args,
                        observed_seq,
                        local_ts_us,
                        shadow_signal,
                        snap,
                        frame.get("mid_price") or frame.get("mid"),
                        capacity_ledger,
                        lot_ledger,
                        admission_gate,
                        exit_manager,
                    )
                    if order_response is not None:
                        return order_response
                return heartbeat(observed_seq, checkpoint_type, snap, shadow_signal)
        return maybe_heartbeat(observed_seq, local_ts_us, state, args)
    elif message_type != "market_quote":
        if not args.sparse_output:
            return heartbeat(
                observed_seq,
                f"ignored_{message_type}",
                checkpoint(state, observed_seq, local_ts_us, f"ignored_{message_type}"),
            )
        return None

    state.trim(local_ts_us)
    if args.decision_clock == "panel":
        return maybe_heartbeat(observed_seq, local_ts_us, state, args)
    if shadow_policy is not None:
        shadow_signal = shadow_policy.on_quote(state, observed_seq, local_ts_us)
        if shadow_signal is not None:
            event_kind = shadow_signal.get("event_kind", "shadow_entry")
            checkpoint_type = (
                "shadow_four_cell_trigger" if event_kind == "shadow_entry" else "shadow_lifecycle_close"
            )
            reason = (
                "shadow_four_cell_trigger" if event_kind == "shadow_entry" else "shadow_lifecycle_close"
            )
            snap = checkpoint(state, observed_seq, local_ts_us, checkpoint_type)
            if event_kind == "shadow_entry":
                snap["four_cell_inputs"].update(
                    {
                        "a_r5_gt_1": shadow_signal["a_r5_gt_1"],
                        "r5": shadow_signal["a_r5_raw"],
                        "r5_ready": shadow_signal["a_r5_ready"],
                        "b_threshold": shadow_signal["b_threshold"],
                        "b_frames_ge_threshold": shadow_signal["b_frames_ge_q90"],
                        "cell": shadow_signal["cell"],
                    }
                )
            snap["shadow_signal"] = shadow_signal
            if capacity_ledger is not None and lot_ledger is not None and admission_gate is not None:
                order_response = build_shadow_order_response(
                    args,
                    observed_seq,
                    local_ts_us,
                    shadow_signal,
                    snap,
                    state.last_mid,
                    capacity_ledger,
                    lot_ledger,
                    admission_gate,
                    exit_manager,
                )
                if order_response is not None:
                    return order_response
            return heartbeat(
                observed_seq,
                reason,
                snap,
                shadow_signal,
            )

    current_tfi = state.tfi()
    flat = abs(state.position_qty) < 1e-9
    enough_cooldown = (
        state.last_order_local_ts_us is None
        or local_ts_us - state.last_order_local_ts_us >= args.cooldown_us
    )
    can_send = (
        observed_seq is not None
        and state.pending_client_order_id is None
        and flat
        and state.orders_sent < args.max_orders
        and enough_cooldown
        and len(state.trades) >= args.min_trades
        and state.abs_qty >= args.min_qty
        and abs(current_tfi) >= args.tfi_threshold
    )
    if not can_send:
        if args.sparse_output:
            return maybe_heartbeat(observed_seq, local_ts_us, state, args)
        return hold(
            observed_seq,
            f"tfi_wait {state.feature_reason()} flat={flat}",
            checkpoint(state, observed_seq, local_ts_us, "hold"),
        )

    side = "buy" if current_tfi > 0 else "sell"
    client_order_id = f"online-tfi-{observed_seq}-{state.orders_sent + 1}"
    state.pending_client_order_id = client_order_id
    state.orders_sent += 1
    state.last_order_local_ts_us = local_ts_us
    return submit_order(
        observed_seq=int(observed_seq),
        observed_local_ts_us=local_ts_us,
        side=side,
        qty=args.qty,
        client_order_id=client_order_id,
        reason=f"online_tfi_threshold {state.feature_reason()}",
        feature_snapshot=checkpoint(state, observed_seq, local_ts_us, "order_intent"),
    )


def main() -> None:
    args = parse_args()
    if (
        args.shadow_capacity_profile == "core_idle01"
        and args.shadow_idle01_gamma is not None
        and args.shadow_gamma01_override is None
    ):
        args.shadow_gamma01_override = args.shadow_idle01_gamma
    state = OnlineFeatureState(window_us=args.window_us, closed_window=args.closed_window)
    shadow_policy = build_shadow_policy(args)
    if shadow_policy is not None and args.shadow_state_in and args.shadow_state_in.exists():
        with args.shadow_state_in.open("r", encoding="utf-8") as handle:
            shadow_policy.load_state(json.load(handle))
    decision_builder = (
        DecisionFrameBuilder(trade_window_us=args.decision_trade_window_us)
        if args.decision_clock == "panel"
        else None
    )
    capacity_ledger = build_capacity_allocator(
        capacity_profile=args.shadow_capacity_profile,
        leverage_cap=args.shadow_leverage_cap,
        idle01_gamma=args.shadow_idle01_gamma,
        idle01_reserve=args.shadow_idle01_reserve,
    )
    lot_ledger = PositionLotLedger()
    admission_gate = build_strategy_admission_gate(args)
    stopping_params = load_stopping_rule_params_for_date(
        args.shadow_stopping_rule_params_json,
        args.shadow_admission_date,
    )
    exit_manager = PeakguardExitManager(
        enabled=args.shadow_exit_profile in {"peakguard_taker_v1", "stopping_rule_v1"},
        exit_profile=args.shadow_exit_profile,
        stopping_params=stopping_params,
    )
    try:
        for raw_line in sys.stdin:
            try:
                message = json.loads(raw_line)
                if message.get("type") == "market_batch":
                    payload = message.get("payload") or {}
                    events = payload.get("events") or []
                    barrier_mode = payload.get("schema_id") in {
                        "batched_public_barrier_v1",
                        "panel_sparse_v1",
                        "panel_sparse_fast_clock_v1",
                    }
                    barrier_stopped = False
                    for idx, event in enumerate(events):
                        try:
                            response = maybe_decide(
                                event,
                                state,
                                args,
                                shadow_policy,
                                decision_builder,
                                capacity_ledger,
                                lot_ledger,
                                admission_gate,
                                exit_manager,
                            )
                        except Exception as exc:
                            print(f"strategy_error: {exc}", file=sys.stderr, flush=True)
                            response = heartbeat(None, "strategy_error")
                        if response is not None:
                            if barrier_mode and is_actionable_response(response):
                                response = attach_barrier_consumed(
                                    response,
                                    event,
                                    idx + 1,
                                    len(events),
                                    str(payload.get("schema_id") or "batched_public_barrier_v1"),
                                )
                            print(
                                json.dumps(json_safe(response), separators=(",", ":"), allow_nan=False),
                                flush=True,
                            )
                            if barrier_mode and is_actionable_response(response):
                                barrier_stopped = True
                                break
                    if barrier_mode and not barrier_stopped:
                        last_event = events[-1] if events else message
                        batch_done = {
                            "type": "batch_done",
                            "reason": f"{payload.get('schema_id')}_consumed",
                        }
                        attach_barrier_consumed(
                            batch_done,
                            last_event,
                            len(events),
                            len(events),
                            str(payload.get("schema_id") or "batched_public_barrier_v1"),
                        )
                        print(
                            json.dumps(json_safe(batch_done), separators=(",", ":"), allow_nan=False),
                            flush=True,
                        )
                    continue
                response = maybe_decide(
                    message,
                    state,
                    args,
                    shadow_policy,
                    decision_builder,
                    capacity_ledger,
                    lot_ledger,
                    admission_gate,
                    exit_manager,
                )
            except Exception as exc:  # Keep stdout protocol alive; diagnostics go to stderr.
                print(f"strategy_error: {exc}", file=sys.stderr, flush=True)
                response = heartbeat(None, "strategy_error")
            if response is not None:
                print(json.dumps(json_safe(response), separators=(",", ":"), allow_nan=False), flush=True)
    finally:
        if shadow_policy is not None and args.shadow_state_out:
            args.shadow_state_out.parent.mkdir(parents=True, exist_ok=True)
            with args.shadow_state_out.open("w", encoding="utf-8") as handle:
                json.dump(shadow_policy.export_state(), handle, indent=2)


if __name__ == "__main__":
    main()
