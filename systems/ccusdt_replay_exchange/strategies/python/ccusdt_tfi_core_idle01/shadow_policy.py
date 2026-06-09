"""Runtime-safe shadow policy for the old CCUSDT four-cell TFI strategy.

This module is intentionally self-contained. It uses only online feature state
already reconstructed from exchange-visible quote/trade/private events.
"""

from __future__ import annotations

import math
import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

from online_features import ClosedOutcomeState


TRIGGER_ORDER = [
    "tfi_follow_flat",
    "tfi_short_flat",
    "tfi_long_flat",
    "tfi_short_stale25",
    "tfi_event_active",
]

BASE_WEIGHTS = {
    "tfi_follow_flat+tfi_long_flat": 0.5,
    "tfi_follow_flat+tfi_long_flat+tfi_event_active": 0.5,
    "tfi_follow_flat+tfi_short_flat": 0.5,
    "tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active": 2.0,
    "tfi_long_flat": 0.5,
}

GAMMA_PRESETS = {
    "core_q70": {
        "00_none": 1.25,
        "10_r5_only": 0.75,
        "01_frames_only": 0.0,
        "11_r5_frames": 0.75,
    },
    "full_anchor": {
        "00_none": 1.0,
        "10_r5_only": 0.75,
        "01_frames_only": 0.25,
        "11_r5_frames": 4.0,
    },
    "high_gamma_q70_capacity": {
        "00_none": 1.25,
        "10_r5_only": 2.0,
        "01_frames_only": 1.0,
        "11_r5_frames": 5.0,
    },
}


@dataclass
class ShadowEntry:
    shadow_position_id: int
    entry_seq: int | None
    entry_ts_us: int
    due_ts_us: int
    entry_mid: float
    direction: int
    trigger_classes: tuple[str, ...]
    membership_set: str
    cell: str
    base_weight: float
    weak_overlay_weight: float
    gamma: float
    target_exposure: float
    a_r5_raw: float | None
    a_r5_ready: bool
    b_frames_ge_q90: bool
    entry_spread_bps: float


class ShadowFourCellPolicy:
    def __init__(
        self,
        *,
        frames_threshold: float = 31.0,
        overlay_threshold: float = 59.80000000000018,
        r5_threshold: float = 1.0,
        bucket_us: int = 60_000_000,
        fixed_exit_us: int = 60_000_000,
        gamma_preset: str = "core_q70",
        gamma_overrides: dict[str, float] | None = None,
        max_triggers: int = 0,
        seed_closed_bps: tuple[float, ...] = (),
    ) -> None:
        if gamma_preset not in GAMMA_PRESETS:
            raise ValueError(f"unknown shadow gamma preset {gamma_preset}")
        self.frames_threshold = float(frames_threshold)
        self.overlay_threshold = float(overlay_threshold)
        self.r5_threshold = float(r5_threshold)
        self.bucket_us = int(bucket_us)
        self.fixed_exit_us = int(fixed_exit_us)
        self.gamma_preset = gamma_preset
        self.gamma_overrides = {
            str(key): float(value)
            for key, value in (gamma_overrides or {}).items()
            if key in GAMMA_PRESETS[gamma_preset]
        }
        self.gamma = dict(GAMMA_PRESETS[gamma_preset])
        self.gamma.update(self.gamma_overrides)
        self.max_triggers = max(0, int(max_triggers))

        self.day_start_ts_us: int | None = None
        self.selected_bucket_by_trigger: dict[str, int] = {}
        self.pending_entries: deque[ShadowEntry] = deque()
        self.closed = ClosedOutcomeState(5)
        for pnl_bps in seed_closed_bps[-5:]:
            self.closed.add(pnl_bps)
        self.shadow_triggers = 0
        self.next_shadow_position_id = 1

    def start_new_day(self) -> None:
        """Reset day-local trigger buckets while preserving online R5 state."""
        self.day_start_ts_us = None
        self.selected_bucket_by_trigger.clear()

    def policy_params(self) -> dict[str, Any]:
        return {
            "frames_threshold": self.frames_threshold,
            "overlay_threshold": self.overlay_threshold,
            "r5_threshold": self.r5_threshold,
            "bucket_us": self.bucket_us,
            "fixed_exit_us": self.fixed_exit_us,
            "gamma_preset": self.gamma_preset,
            "gamma_overrides": self.gamma_overrides,
            "gamma": self.gamma,
            "max_triggers": self.max_triggers,
        }

    def policy_params_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.policy_params(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def export_state(
        self,
        *,
        last_seen_ts_us: int | None = None,
        last_seen_date: str | None = None,
    ) -> dict[str, Any]:
        """Persist Bot-owned shadow lifecycle state without research labels."""
        return {
            "schema_id": "ccusdt_shadow_four_cell_state_v1",
            "runtime_safe": True,
            "policy": "old_tfi_four_cell_shadow_v1",
            "policy_params": self.policy_params(),
            "policy_params_hash": self.policy_params_hash(),
            "fixed_exit_us": self.fixed_exit_us,
            "gamma_preset": self.gamma_preset,
            "last_seen_ts_us": last_seen_ts_us,
            "last_seen_date": last_seen_date,
            "closed_bps": list(self.closed.outcomes_bps),
            "pending_entries": [asdict(entry) for entry in self.pending_entries],
            "shadow_triggers": self.shadow_triggers,
            "next_shadow_position_id": self.next_shadow_position_id,
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore Bot-owned state produced by export_state."""
        self.closed = ClosedOutcomeState(5)
        for pnl_bps in list(state.get("closed_bps") or [])[-5:]:
            try:
                self.closed.add(float(pnl_bps))
            except (TypeError, ValueError):
                continue
        self.pending_entries.clear()
        for raw in state.get("pending_entries") or []:
            if not isinstance(raw, dict):
                continue
            try:
                self.pending_entries.append(
                    ShadowEntry(
                        shadow_position_id=int(raw["shadow_position_id"]),
                        entry_seq=(
                            None
                            if raw.get("entry_seq") is None
                            else int(raw.get("entry_seq"))
                        ),
                        entry_ts_us=int(raw["entry_ts_us"]),
                        due_ts_us=int(raw["due_ts_us"]),
                        entry_mid=float(raw["entry_mid"]),
                        direction=int(raw["direction"]),
                        trigger_classes=tuple(raw.get("trigger_classes") or ()),
                        membership_set=str(raw.get("membership_set") or ""),
                        cell=str(raw.get("cell") or ""),
                        base_weight=float(raw.get("base_weight") or 0.0),
                        weak_overlay_weight=float(raw.get("weak_overlay_weight") or 0.0),
                        gamma=float(raw.get("gamma") or 0.0),
                        target_exposure=float(raw.get("target_exposure") or 0.0),
                        a_r5_raw=_optional_float(raw.get("a_r5_raw")),
                        a_r5_ready=bool(raw.get("a_r5_ready")),
                        b_frames_ge_q90=bool(raw.get("b_frames_ge_q90")),
                        entry_spread_bps=float(raw.get("entry_spread_bps") or 0.0),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        self.shadow_triggers = int(state.get("shadow_triggers") or self.shadow_triggers)
        self.next_shadow_position_id = int(
            state.get("next_shadow_position_id") or self.next_shadow_position_id
        )

    def on_quote(self, state: Any, observed_seq: int | None, local_ts_us: int) -> dict[str, Any] | None:
        closed_now = self._close_matured_at_mid(observed_seq, local_ts_us, state.last_mid)
        if observed_seq is None or state.last_mid is None or state.last_mid <= 0.0:
            return None
        if self.max_triggers and self.shadow_triggers >= self.max_triggers:
            return self._close_signal(observed_seq, local_ts_us, closed_now) if closed_now else None
        if self.day_start_ts_us is None:
            self.day_start_ts_us = local_ts_us
        bucket = (local_ts_us - self.day_start_ts_us) // max(1, self.bucket_us)

        active = self._active_trigger_directions_from_values(
            tfi=state.tfi(),
            trade_count=len(state.trades),
            frames_since_mid_change=state.frames_since_mid_change,
            past_event_25_bps=state.past_event_25_bps,
        )
        selected: list[str] = []
        direction = 0
        for trigger in TRIGGER_ORDER:
            trigger_direction = active.get(trigger, 0)
            if trigger_direction == 0:
                continue
            if self.selected_bucket_by_trigger.get(trigger) == bucket:
                continue
            self.selected_bucket_by_trigger[trigger] = bucket
            selected.append(trigger)
            direction = trigger_direction

        if not selected or direction == 0:
            return self._close_signal(observed_seq, local_ts_us, closed_now) if closed_now else None

        membership_set = "+".join(selected)
        base_weight = BASE_WEIGHTS.get(membership_set, 0.0)
        if base_weight <= 0.0:
            return self._close_signal(observed_seq, local_ts_us, closed_now) if closed_now else None

        closed = self.closed.snapshot()
        r5 = closed["r5"]
        a_r5 = bool(r5 is not None and r5 >= self.r5_threshold)
        b_frames = bool(state.frames_since_mid_change >= self.frames_threshold)
        cell = self._cell(a_r5, b_frames)
        overlay_boost = 0.5 if state.frames_since_mid_change >= self.overlay_threshold else 0.0
        weak_overlay_weight = base_weight + overlay_boost
        gamma = self.gamma[cell]
        target_exposure = weak_overlay_weight * gamma
        shadow_position_id = self.next_shadow_position_id
        self.next_shadow_position_id += 1
        self.shadow_triggers += 1
        due_ts_us = local_ts_us + self.fixed_exit_us
        self.pending_entries.append(
            ShadowEntry(
                shadow_position_id=shadow_position_id,
                entry_seq=observed_seq,
                entry_ts_us=local_ts_us,
                due_ts_us=due_ts_us,
                entry_mid=float(state.last_mid),
                direction=int(direction),
                trigger_classes=tuple(selected),
                membership_set=membership_set,
                cell=cell,
                base_weight=base_weight,
                weak_overlay_weight=weak_overlay_weight,
                gamma=gamma,
                target_exposure=target_exposure,
                a_r5_raw=r5,
                a_r5_ready=bool(closed["r5_ready"]),
                b_frames_ge_q90=b_frames,
                entry_spread_bps=float(state.spread_bps),
            )
        )

        return {
            "schema_id": "ccusdt_shadow_four_cell_signal_v1",
            "runtime_safe": True,
            "event_kind": "shadow_entry",
            "policy": "old_tfi_four_cell_shadow_v1",
            "observed_seq": observed_seq,
            "local_ts_us": local_ts_us,
            "shadow_position_id": shadow_position_id,
            "entry_ts_us": local_ts_us,
            "entry_due_ts_us": due_ts_us,
            "fixed_exit_us": self.fixed_exit_us,
            "bucket_us": self.bucket_us,
            "bucket": bucket,
            "trigger_classes": selected,
            "membership_set": membership_set,
            "direction": direction,
            "side": "buy" if direction > 0 else "sell",
            "direction_label": "long" if direction > 0 else "short",
            "feature_value": state.tfi(),
            "trade_window_count": len(state.trades),
            "trade_buy_qty": state.buy_qty,
            "trade_sell_qty": state.sell_qty,
            "abs_qty": state.abs_qty,
            "past_event_25_bps": state.past_event_25_bps,
            "frames_since_mid_change": state.frames_since_mid_change,
            "entry_spread_bps": state.spread_bps,
            "a_r5_gt_1": a_r5,
            "a_r5_raw": r5,
            "a_r5_ready": closed["r5_ready"],
            "b_frames_ge_q90": b_frames,
            "b_threshold": self.frames_threshold,
            "cell": cell,
            "base_weight": base_weight,
            "overlay_threshold": self.overlay_threshold,
            "overlay_boost": overlay_boost,
            "weak_overlay_weight": weak_overlay_weight,
            "gamma_preset": self.gamma_preset,
            "gamma": gamma,
            "target_exposure": target_exposure,
            "shadow_trigger_index": self.shadow_triggers,
            "pending_shadow_entries": len(self.pending_entries),
            "closed_now": closed_now,
            "closed_outcomes": closed,
        }

    def on_decision_frame(self, frame: dict[str, Any], observed_seq: int | None = None) -> dict[str, Any] | None:
        local_ts_us = int(frame.get("local_ts_us") or frame.get("local_timestamp") or 0)
        mid = _optional_float(frame.get("mid_price", frame.get("mid")))
        closed_now = self._close_matured_at_mid(observed_seq, local_ts_us, mid)
        if observed_seq is None or mid is None or mid <= 0.0:
            return None
        if self.max_triggers and self.shadow_triggers >= self.max_triggers:
            return self._close_signal(observed_seq, local_ts_us, closed_now) if closed_now else None

        if frame.get("fwd_time_60s_bucket") is not None:
            bucket = int(float(frame["fwd_time_60s_bucket"]))
        else:
            if self.day_start_ts_us is None:
                self.day_start_ts_us = local_ts_us
            bucket = (local_ts_us - self.day_start_ts_us) // max(1, self.bucket_us)

        tfi = _optional_float(frame.get("trade_flow_imbalance"))
        trade_count = int(float(frame.get("trade_window_count") or 0))
        frames_since_mid_change = _optional_float(frame.get("frames_since_mid_change"))
        past_event_25_bps = _optional_float(frame.get("past_event_25_bps"))
        active = self._active_trigger_directions_from_values(
            tfi=tfi,
            trade_count=trade_count,
            frames_since_mid_change=frames_since_mid_change,
            past_event_25_bps=past_event_25_bps,
        )
        selected: list[str] = []
        direction = 0
        for trigger in TRIGGER_ORDER:
            trigger_direction = active.get(trigger, 0)
            if trigger_direction == 0:
                continue
            if self.selected_bucket_by_trigger.get(trigger) == bucket:
                continue
            self.selected_bucket_by_trigger[trigger] = bucket
            selected.append(trigger)
            direction = trigger_direction

        if not selected or direction == 0:
            return self._close_signal(observed_seq, local_ts_us, closed_now) if closed_now else None

        membership_set = "+".join(selected)
        base_weight = BASE_WEIGHTS.get(membership_set, 0.0)
        if base_weight <= 0.0:
            return self._close_signal(observed_seq, local_ts_us, closed_now) if closed_now else None

        closed = self.closed.snapshot()
        r5 = closed["r5"]
        a_r5 = bool(r5 is not None and r5 >= self.r5_threshold)
        frames_value = frames_since_mid_change if frames_since_mid_change is not None else -math.inf
        b_frames = bool(frames_value >= self.frames_threshold)
        cell = self._cell(a_r5, b_frames)
        overlay_boost = 0.5 if frames_value >= self.overlay_threshold else 0.0
        weak_overlay_weight = base_weight + overlay_boost
        gamma = self.gamma[cell]
        target_exposure = weak_overlay_weight * gamma
        shadow_position_id = self.next_shadow_position_id
        self.next_shadow_position_id += 1
        self.shadow_triggers += 1
        due_ts_us = local_ts_us + self.fixed_exit_us
        spread_bps = _optional_float(frame.get("spread_bps")) or 0.0
        self.pending_entries.append(
            ShadowEntry(
                shadow_position_id=shadow_position_id,
                entry_seq=observed_seq,
                entry_ts_us=local_ts_us,
                due_ts_us=due_ts_us,
                entry_mid=float(mid),
                direction=int(direction),
                trigger_classes=tuple(selected),
                membership_set=membership_set,
                cell=cell,
                base_weight=base_weight,
                weak_overlay_weight=weak_overlay_weight,
                gamma=gamma,
                target_exposure=target_exposure,
                a_r5_raw=r5,
                a_r5_ready=bool(closed["r5_ready"]),
                b_frames_ge_q90=b_frames,
                entry_spread_bps=float(spread_bps),
            )
        )
        return {
            "schema_id": "ccusdt_shadow_four_cell_signal_v1",
            "runtime_safe": True,
            "event_kind": "shadow_entry",
            "policy": "old_tfi_four_cell_shadow_v1",
            "decision_clock": "panel",
            "observed_seq": observed_seq,
            "local_ts_us": local_ts_us,
            "shadow_position_id": shadow_position_id,
            "entry_ts_us": local_ts_us,
            "entry_due_ts_us": due_ts_us,
            "fixed_exit_us": self.fixed_exit_us,
            "bucket_us": self.bucket_us,
            "bucket": bucket,
            "trigger_classes": selected,
            "membership_set": membership_set,
            "direction": direction,
            "side": "buy" if direction > 0 else "sell",
            "direction_label": "long" if direction > 0 else "short",
            "feature_value": tfi,
            "trade_window_count": trade_count,
            "trade_buy_qty": _optional_float(frame.get("trade_buy_amount")),
            "trade_sell_qty": _optional_float(frame.get("trade_sell_amount")),
            "past_event_25_bps": past_event_25_bps,
            "frames_since_mid_change": frames_since_mid_change,
            "entry_spread_bps": spread_bps,
            "entry_event_index": frame.get("event_index"),
            "a_r5_gt_1": a_r5,
            "a_r5_raw": r5,
            "a_r5_ready": closed["r5_ready"],
            "b_frames_ge_q90": b_frames,
            "b_threshold": self.frames_threshold,
            "cell": cell,
            "base_weight": base_weight,
            "overlay_threshold": self.overlay_threshold,
            "overlay_boost": overlay_boost,
            "weak_overlay_weight": weak_overlay_weight,
            "gamma_preset": self.gamma_preset,
            "gamma": gamma,
            "target_exposure": target_exposure,
            "shadow_trigger_index": self.shadow_triggers,
            "pending_shadow_entries": len(self.pending_entries),
            "closed_now": closed_now,
            "closed_outcomes": closed,
        }

    def _close_matured_at_mid(
        self,
        observed_seq: int | None,
        local_ts_us: int,
        mid: float | None,
    ) -> list[dict[str, Any]]:
        if mid is None or mid <= 0.0:
            return []
        closed_now: list[dict[str, Any]] = []
        # R5 availability is strict: entry_ts + 60s must be < current entry_ts.
        while self.pending_entries and self.pending_entries[0].due_ts_us < local_ts_us:
            entry = self.pending_entries.popleft()
            pnl_bps = entry.direction * math.log(mid / entry.entry_mid) * 10_000.0
            self.closed.add(pnl_bps)
            closed_now.append(
                {
                    "shadow_position_id": entry.shadow_position_id,
                    "entry_seq": entry.entry_seq,
                    "close_seq": observed_seq,
                    "entry_ts_us": entry.entry_ts_us,
                    "due_ts_us": entry.due_ts_us,
                    "close_ts_us": local_ts_us,
                    "held_us": local_ts_us - entry.entry_ts_us,
                    "exit_lag_us": local_ts_us - entry.due_ts_us,
                    "entry_mid": entry.entry_mid,
                    "close_mid": mid,
                    "direction": entry.direction,
                    "side": "buy" if entry.direction > 0 else "sell",
                    "direction_label": "long" if entry.direction > 0 else "short",
                    "pnl_bps": pnl_bps,
                    "trigger_classes": list(entry.trigger_classes),
                    "membership_set": entry.membership_set,
                    "cell": entry.cell,
                    "base_weight": entry.base_weight,
                    "weak_overlay_weight": entry.weak_overlay_weight,
                    "gamma": entry.gamma,
                    "target_exposure": entry.target_exposure,
                    "a_r5_raw_at_entry": entry.a_r5_raw,
                    "a_r5_ready_at_entry": entry.a_r5_ready,
                    "b_frames_ge_q90_at_entry": entry.b_frames_ge_q90,
                    "entry_spread_bps": entry.entry_spread_bps,
                }
            )
        return closed_now

    def _close_signal(
        self,
        observed_seq: int,
        local_ts_us: int,
        closed_now: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema_id": "ccusdt_shadow_four_cell_signal_v1",
            "runtime_safe": True,
            "event_kind": "shadow_lifecycle_close",
            "policy": "old_tfi_four_cell_shadow_v1",
            "observed_seq": observed_seq,
            "local_ts_us": local_ts_us,
            "closed_now": closed_now,
            "closed_outcomes": self.closed.snapshot(),
            "pending_shadow_entries": len(self.pending_entries),
        }

    def _active_trigger_directions_from_values(
        self,
        *,
        tfi: float | None,
        trade_count: int,
        frames_since_mid_change: float | None,
        past_event_25_bps: float | None,
    ) -> dict[str, int]:
        if tfi is None or not math.isfinite(tfi):
            return {}
        high = tfi >= 1.0 - 1e-12
        low = tfi <= -1.0 + 1e-12
        if not high and not low:
            return {}
        direction = 1 if high else -1
        trade_present = trade_count > 0
        past25 = past_event_25_bps
        flat = past25 is not None and abs(past25) <= 0.5
        stale25 = frames_since_mid_change is not None and frames_since_mid_change >= 25
        active: dict[str, int] = {}
        if flat:
            active["tfi_follow_flat"] = direction
            if low:
                active["tfi_short_flat"] = -1
            if high:
                active["tfi_long_flat"] = 1
        if low and stale25:
            active["tfi_short_stale25"] = -1
        if trade_present and stale25:
            active["tfi_event_active"] = direction
        return active

    @staticmethod
    def _cell(a_r5: bool, b_frames: bool) -> str:
        if a_r5 and b_frames:
            return "11_r5_frames"
        if a_r5:
            return "10_r5_only"
        if b_frames:
            return "01_frames_only"
        return "00_none"


def add_shadow_args(parser: Any) -> None:
    parser.add_argument("--shadow-four-cell", action="store_true")
    parser.add_argument("--shadow-frames-threshold", type=float, default=31.0)
    parser.add_argument("--shadow-overlay-threshold", type=float, default=59.80000000000018)
    parser.add_argument("--shadow-r5-threshold", type=float, default=1.0)
    parser.add_argument("--shadow-bucket-us", type=int, default=60_000_000)
    parser.add_argument("--shadow-fixed-exit-us", type=int, default=60_000_000)
    parser.add_argument("--shadow-gamma-preset", choices=sorted(GAMMA_PRESETS), default="core_q70")
    parser.add_argument("--shadow-gamma01-override", type=float)
    parser.add_argument("--shadow-max-triggers", type=int, default=0)
    parser.add_argument("--shadow-seed-closed-bps", default="")


def build_shadow_policy(args: Any) -> ShadowFourCellPolicy | None:
    if not getattr(args, "shadow_four_cell", False):
        return None
    return ShadowFourCellPolicy(
        frames_threshold=getattr(args, "shadow_frames_threshold", 31.0),
        overlay_threshold=getattr(args, "shadow_overlay_threshold", 59.80000000000018),
        r5_threshold=getattr(args, "shadow_r5_threshold", 1.0),
        bucket_us=getattr(args, "shadow_bucket_us", 60_000_000),
        fixed_exit_us=getattr(args, "shadow_fixed_exit_us", 60_000_000),
        gamma_preset=getattr(args, "shadow_gamma_preset", "core_q70"),
        gamma_overrides=gamma_overrides_from_args(args),
        max_triggers=getattr(args, "shadow_max_triggers", 0),
        seed_closed_bps=parse_seed_closed_bps(getattr(args, "shadow_seed_closed_bps", "")),
    )


def gamma_overrides_from_args(args: Any) -> dict[str, float]:
    gamma01 = getattr(args, "shadow_gamma01_override", None)
    if gamma01 is None:
        return {}
    return {"01_frames_only": max(0.0, float(gamma01))}


def parse_seed_closed_bps(raw: Any) -> tuple[float, ...]:
    values: list[float] = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = float(part)
        except ValueError:
            continue
        if math.isfinite(value):
            values.append(value)
    return tuple(values[-5:])


def _optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) or math.isinf(out) else None
