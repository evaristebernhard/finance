"""Runtime execution state shared by fast and sim-live CCUSDT paths.

This module is intentionally market/runtime local. It does not read research
panels, labels, PnL path files, or root scripts.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


EPS = 1e-12
STOPPING_RULE_HORIZONS_SEC = [1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0]


def _optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _safe_float(value: Any, default: float) -> float:
    out = _optional_float(value)
    return default if out is None else out


@dataclass(frozen=True)
class StoppingRuleParams:
    schema_id: str
    h: float
    d0: float
    rho: float
    q_exit: float
    emergency_decay: float = 999.0
    emergency_d: float = 6.0
    q_emergency_add: float = 0.75
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_stopping_rule_params(raw: dict[str, Any], *, source: str | None = None) -> StoppingRuleParams:
    return StoppingRuleParams(
        schema_id="ccusdt_stopping_rule_params_v1",
        h=_safe_float(raw.get("h"), 4.0),
        d0=_safe_float(raw.get("d0"), 2.0),
        rho=_safe_float(raw.get("rho"), 0.35),
        q_exit=_safe_float(raw.get("q_exit"), 2.0),
        emergency_decay=_safe_float(raw.get("emergency_decay"), 999.0),
        emergency_d=_safe_float(raw.get("emergency_d"), max(2.0 * _safe_float(raw.get("d0"), 2.0), 6.0)),
        q_emergency_add=_safe_float(raw.get("q_emergency_add"), 0.75),
        source=source,
    )


def load_stopping_rule_params_by_date(path: Path | None) -> dict[str, StoppingRuleParams]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    rows = raw.get("params_by_date", raw.get("parameters", raw)) if isinstance(raw, dict) else {}
    if not isinstance(rows, dict):
        raise ValueError("stopping rule params JSON must map date -> params")
    out: dict[str, StoppingRuleParams] = {}
    for day, value in rows.items():
        if not isinstance(value, dict):
            continue
        out[str(day)] = normalize_stopping_rule_params(value, source=f"{path}:{day}")
    return out


def load_stopping_rule_params_for_date(path: Path | None, day: str | None) -> StoppingRuleParams | None:
    if path is None or not day:
        return None
    return load_stopping_rule_params_by_date(path).get(str(day))


def stopping_rule_should_exit(
    *,
    high_bps: float,
    drawdown_bps: float,
    exit_cross_bps: float,
    recent_mid_alpha_5s_bps: float,
    params: StoppingRuleParams,
) -> bool:
    if (
        high_bps >= params.h
        and drawdown_bps >= max(params.d0, params.rho * max(high_bps, 0.0))
        and exit_cross_bps <= params.q_exit
    ):
        return True
    if params.emergency_decay < 900.0:
        return (
            high_bps >= params.h
            and drawdown_bps >= params.emergency_d
            and recent_mid_alpha_5s_bps <= -params.emergency_decay
            and exit_cross_bps <= params.q_exit + params.q_emergency_add
        )
    return False


def taker_net_and_exit_cross_bps(
    *,
    entry_side: str,
    entry_bid: float | None,
    entry_ask: float | None,
    current_bid: float | None,
    current_ask: float | None,
    current_mid: float | None,
) -> tuple[float | None, float | None]:
    if (
        entry_bid is None
        or entry_ask is None
        or current_bid is None
        or current_ask is None
        or current_mid is None
        or entry_bid <= 0.0
        or entry_ask <= 0.0
        or current_bid <= 0.0
        or current_ask <= 0.0
        or current_mid <= 0.0
    ):
        return None, None
    if entry_side == "buy":
        return (
            math.log(current_bid / entry_ask) * 10_000.0,
            math.log(current_mid / current_bid) * 10_000.0,
        )
    return (
        math.log(entry_bid / current_ask) * 10_000.0,
        math.log(current_ask / current_mid) * 10_000.0,
    )


@dataclass
class CapacityDecision:
    schema_id: str
    shadow_position_id: int
    requested_exposure: float
    actual_exposure: float
    clipped_exposure: float
    skipped: bool
    open_exposure_before: float
    open_exposure_after: float
    leverage_cap: float
    capacity_profile: str = "fifo_clip"
    capacity_source: str = "fifo_clip"
    idle_capacity_before: float | None = None
    core_displacement: float = 0.0
    reserve: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdmissionDecision:
    schema_id: str
    shadow_position_id: int
    admission_profile: str
    accepted: bool
    reason: str
    entry_spread_bps: float | None
    entry_cross_bps: float | None
    entry_cross_threshold_bps: float | None
    threshold_source: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EntrySpreadAdmissionGate:
    """Pre-capacity admission gate using only entry-time spread."""

    def __init__(
        self,
        *,
        profile: str = "none",
        entry_cross_threshold_bps: float | None = None,
        threshold_source: str | None = None,
    ) -> None:
        self.profile = str(profile or "none")
        self.entry_cross_threshold_bps = (
            None
            if entry_cross_threshold_bps is None
            else max(0.0, float(entry_cross_threshold_bps))
        )
        self.threshold_source = threshold_source
        if self.profile == "entry_spread_q70_v1" and self.entry_cross_threshold_bps is None:
            raise ValueError("entry_spread_q70_v1 requires entry_cross_threshold_bps")
        if self.profile not in {"none", "entry_spread_q70_v1"}:
            raise ValueError(f"unsupported admission_profile={self.profile}")

    def decide(self, shadow_signal: dict[str, Any]) -> AdmissionDecision:
        position_id = int(shadow_signal["shadow_position_id"])
        if self.profile == "none":
            return AdmissionDecision(
                schema_id="ccusdt_admission_decision_v1",
                shadow_position_id=position_id,
                admission_profile="none",
                accepted=True,
                reason="no_admission_gate",
                entry_spread_bps=_optional_float(shadow_signal.get("entry_spread_bps")),
                entry_cross_bps=None,
                entry_cross_threshold_bps=None,
                threshold_source=None,
            )
        spread = _optional_float(shadow_signal.get("entry_spread_bps"))
        if spread is None or spread < 0.0:
            accepted = False
            entry_cross = None
            reason = "missing_or_invalid_entry_spread"
        else:
            entry_cross = 0.5 * spread
            accepted = entry_cross <= float(self.entry_cross_threshold_bps)
            reason = "accepted_entry_cross_q70" if accepted else "rejected_entry_cross_gt_q70"
        return AdmissionDecision(
            schema_id="ccusdt_admission_decision_v1",
            shadow_position_id=position_id,
            admission_profile=self.profile,
            accepted=accepted,
            reason=reason,
            entry_spread_bps=spread,
            entry_cross_bps=entry_cross,
            entry_cross_threshold_bps=self.entry_cross_threshold_bps,
            threshold_source=self.threshold_source,
        )

    def profile_manifest(self) -> dict[str, Any]:
        return {
            "name": self.profile,
            "entry_cross_threshold_bps": self.entry_cross_threshold_bps,
            "threshold_source": self.threshold_source,
            "rule": (
                "accept if entry_spread_bps / 2 <= prior-date q70 entry_cross_bps"
                if self.profile == "entry_spread_q70_v1"
                else "no pre-capacity admission gate"
            ),
        }


def build_admission_gate(
    *,
    admission_profile: str = "none",
    entry_cross_threshold_bps: float | None = None,
    threshold_source: str | None = None,
) -> EntrySpreadAdmissionGate:
    return EntrySpreadAdmissionGate(
        profile=admission_profile,
        entry_cross_threshold_bps=entry_cross_threshold_bps,
        threshold_source=threshold_source,
    )


class CapacityLedger:
    """Online FIFO/arrival exposure clipper.

    The first version matches the fast research runner exactly:

    actual = min(requested, max(0, leverage_cap - open_exposure))
    """

    def __init__(self, leverage_cap: float = 3.0) -> None:
        self.leverage_cap = max(0.0, float(leverage_cap))
        self.open_exposure = 0.0
        self.actual_by_position: dict[int, float] = {}

    def decide(self, shadow_signal: dict[str, Any]) -> CapacityDecision:
        position_id = int(shadow_signal["shadow_position_id"])
        requested = max(0.0, float(shadow_signal.get("target_exposure") or 0.0))
        before = self.open_exposure
        free = max(0.0, self.leverage_cap - before)
        actual = min(requested, free)
        clipped = max(0.0, requested - actual)
        skipped = actual <= EPS and requested > 0.0
        after = before + actual
        self.open_exposure = after
        self.actual_by_position[position_id] = actual
        return CapacityDecision(
            schema_id="ccusdt_capacity_decision_v1",
            shadow_position_id=position_id,
            requested_exposure=requested,
            actual_exposure=actual,
            clipped_exposure=clipped,
            skipped=skipped,
            open_exposure_before=before,
            open_exposure_after=after,
            leverage_cap=self.leverage_cap,
            capacity_profile="fifo_clip",
            capacity_source="fifo_clip" if requested > EPS else "zero_request",
            idle_capacity_before=free,
            core_displacement=0.0,
            reserve=0.0,
        )

    def reject_decision(self, shadow_signal: dict[str, Any], *, capacity_source: str) -> CapacityDecision:
        position_id = int(shadow_signal["shadow_position_id"])
        requested = max(0.0, float(shadow_signal.get("target_exposure") or 0.0))
        before = self.open_exposure
        return CapacityDecision(
            schema_id="ccusdt_capacity_decision_v1",
            shadow_position_id=position_id,
            requested_exposure=requested,
            actual_exposure=0.0,
            clipped_exposure=requested,
            skipped=requested > EPS,
            open_exposure_before=before,
            open_exposure_after=before,
            leverage_cap=self.leverage_cap,
            capacity_profile=self.snapshot()["capacity_profile"],
            capacity_source=capacity_source,
            idle_capacity_before=max(0.0, self.leverage_cap - before),
            core_displacement=0.0,
            reserve=0.0,
        )

    def close(self, shadow_position_id: int) -> float:
        position_id = int(shadow_position_id)
        actual = float(self.actual_by_position.pop(position_id, 0.0))
        self.open_exposure = max(0.0, self.open_exposure - actual)
        return actual

    def actual_exposure(self, shadow_position_id: int) -> float:
        return float(self.actual_by_position.get(int(shadow_position_id), 0.0))

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_id": "ccusdt_capacity_ledger_state_v1",
            "capacity_profile": "fifo_clip",
            "leverage_cap": self.leverage_cap,
            "open_exposure": self.open_exposure,
            "open_positions": dict(self.actual_by_position),
        }


class CoreIdle01CapacityAllocator(CapacityLedger):
    """Online 3x allocator with a core bucket and an idle 01 sleeve.

    Core cells consume ordinary FIFO capacity. The 01 cell is admitted only from
    spare capacity after already-open positions and an optional reserve; it does
    not displace core exposure.
    """

    CORE_CELLS = {"00_none", "10_r5_only", "11_r5_frames"}
    IDLE_CELL = "01_frames_only"

    def __init__(
        self,
        leverage_cap: float = 3.0,
        *,
        idle01_gamma: float | None = None,
        reserve: float = 0.0,
    ) -> None:
        super().__init__(leverage_cap)
        self.idle01_gamma = None if idle01_gamma is None else max(0.0, float(idle01_gamma))
        self.reserve = max(0.0, float(reserve))

    def decide(self, shadow_signal: dict[str, Any]) -> CapacityDecision:
        position_id = int(shadow_signal["shadow_position_id"])
        cell = str(shadow_signal.get("cell") or "")
        requested = max(0.0, float(shadow_signal.get("target_exposure") or 0.0))
        if cell == self.IDLE_CELL and self.idle01_gamma is not None:
            requested = max(
                0.0,
                float(shadow_signal.get("weak_overlay_weight") or 0.0) * self.idle01_gamma,
            )
        before = self.open_exposure
        gross_free = max(0.0, self.leverage_cap - before)
        if cell == self.IDLE_CELL:
            capacity_source = "idle01"
            idle_capacity = max(0.0, gross_free - self.reserve)
            free = idle_capacity
            reserve = self.reserve
        elif cell in self.CORE_CELLS:
            capacity_source = "core"
            idle_capacity = gross_free
            free = gross_free
            reserve = 0.0
        else:
            capacity_source = "other"
            idle_capacity = gross_free
            free = gross_free
            reserve = 0.0
        actual = min(requested, free)
        clipped = max(0.0, requested - actual)
        skipped = actual <= EPS and requested > 0.0
        after = before + actual
        self.open_exposure = after
        self.actual_by_position[position_id] = actual
        if requested <= EPS:
            capacity_source = "zero_request"
        return CapacityDecision(
            schema_id="ccusdt_capacity_decision_v1",
            shadow_position_id=position_id,
            requested_exposure=requested,
            actual_exposure=actual,
            clipped_exposure=clipped,
            skipped=skipped,
            open_exposure_before=before,
            open_exposure_after=after,
            leverage_cap=self.leverage_cap,
            capacity_profile="core_idle01",
            capacity_source=capacity_source,
            idle_capacity_before=idle_capacity,
            core_displacement=0.0,
            reserve=reserve,
        )

    def snapshot(self) -> dict[str, Any]:
        out = super().snapshot()
        out.update(
            {
                "capacity_profile": "core_idle01",
                "idle01_gamma": self.idle01_gamma,
                "reserve": self.reserve,
                "core_cells": sorted(self.CORE_CELLS),
                "idle_cell": self.IDLE_CELL,
            }
        )
        return out


def build_capacity_allocator(
    *,
    capacity_profile: str = "fifo_clip",
    leverage_cap: float = 3.0,
    idle01_gamma: float | None = None,
    idle01_reserve: float = 0.0,
) -> CapacityLedger:
    if capacity_profile == "fifo_clip":
        return CapacityLedger(leverage_cap)
    if capacity_profile == "core_idle01":
        return CoreIdle01CapacityAllocator(
            leverage_cap,
            idle01_gamma=idle01_gamma,
            reserve=idle01_reserve,
        )
    raise ValueError(f"unsupported capacity_profile={capacity_profile}")


def stable_profile_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_profile_manifest(
    *,
    policy_profile: dict[str, Any],
    capacity_profile: dict[str, Any],
    exit_profile: dict[str, Any],
    fill_profile: dict[str, Any],
    latency_profile: dict[str, Any],
    transport_profile: dict[str, Any] | None = None,
    data_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
        "schema_id": "ccusdt_strategy_run_profiles_v1",
        "policy_profile": policy_profile,
        "capacity_profile": capacity_profile,
        "exit_profile": exit_profile,
        "fill_profile": fill_profile,
        "latency_profile": latency_profile,
        "transport_profile": transport_profile or {"name": "unspecified"},
        "data_profile": data_profile or {"name": "unspecified"},
    }
    manifest["profile_manifest_hash"] = stable_profile_hash(manifest)
    return manifest


@dataclass
class PositionLot:
    schema_id: str
    position_lot_id: str
    shadow_position_id: int
    side: str
    entry_qty: float
    remaining_qty: float
    avg_entry_price: float
    actual_exposure: float
    entry_intent_id: int | None
    entry_client_order_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PositionLotLedger:
    """Track shadow-position lots from real private ack/fill events."""

    def __init__(self) -> None:
        self.intent_to_client_order_id: dict[int, str] = {}
        self.pending_entry_decisions: dict[str, dict[str, Any]] = {}
        self.lots_by_position: dict[int, PositionLot] = {}

    def register_entry_order(
        self,
        client_order_id: str,
        shadow_signal: dict[str, Any],
        capacity_decision: dict[str, Any],
    ) -> None:
        self.pending_entry_decisions[client_order_id] = {
            "shadow_signal": shadow_signal,
            "capacity_decision": capacity_decision,
        }

    def on_order_ack(self, payload: dict[str, Any]) -> None:
        inner = payload.get("payload") or payload
        order = inner.get("order") or {}
        client_order_id = order.get("client_order_id")
        intent_id = inner.get("intent_id")
        if client_order_id and intent_id is not None:
            self.intent_to_client_order_id[int(intent_id)] = str(client_order_id)

    def on_fill(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        inner = payload.get("payload") or payload
        fill = inner.get("fill") or {}
        intent_id = inner.get("intent_id")
        if intent_id is None:
            return None
        client_order_id = self.intent_to_client_order_id.get(int(intent_id))
        if not client_order_id:
            return None
        if client_order_id.startswith("shadow-entry-"):
            return self._on_entry_fill(client_order_id, int(intent_id), fill)
        if client_order_id.startswith("shadow-exit-"):
            return self._on_exit_fill(client_order_id, int(intent_id), fill)
        return None

    def _on_entry_fill(
        self,
        client_order_id: str,
        intent_id: int,
        fill: dict[str, Any],
    ) -> dict[str, Any] | None:
        pending = self.pending_entry_decisions.get(client_order_id)
        if not pending:
            return None
        shadow = pending["shadow_signal"]
        capacity = pending["capacity_decision"]
        position_id = int(shadow["shadow_position_id"])
        qty = float(fill.get("qty") or 0.0)
        price = float(fill.get("price") or 0.0)
        if qty <= EPS or price <= 0.0:
            return None
        lot = PositionLot(
            schema_id="ccusdt_position_lot_v1",
            position_lot_id=f"shadow-lot-{position_id}",
            shadow_position_id=position_id,
            side=str(shadow.get("side") or fill.get("side") or ""),
            entry_qty=qty,
            remaining_qty=qty,
            avg_entry_price=price,
            actual_exposure=float(capacity.get("actual_exposure") or 0.0),
            entry_intent_id=intent_id,
            entry_client_order_id=client_order_id,
        )
        self.lots_by_position[position_id] = lot
        return {
            "event": "position_opened",
            "position_lot": lot.to_dict(),
            "capacity_decision": capacity,
        }

    def _on_exit_fill(
        self,
        client_order_id: str,
        intent_id: int,
        fill: dict[str, Any],
    ) -> dict[str, Any] | None:
        try:
            position_id = int(client_order_id.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return None
        lot = self.lots_by_position.get(position_id)
        if lot is None:
            return None
        qty = float(fill.get("qty") or 0.0)
        price = float(fill.get("price") or 0.0)
        closed_qty = min(lot.remaining_qty, max(0.0, qty))
        lot.remaining_qty = max(0.0, lot.remaining_qty - closed_qty)
        event = "position_closed" if lot.remaining_qty <= EPS else "position_partial_closed"
        out = {
            "event": event,
            "position_lot_id": lot.position_lot_id,
            "shadow_position_id": position_id,
            "exit_intent_id": intent_id,
            "exit_client_order_id": client_order_id,
            "closed_qty": closed_qty,
            "remaining_qty": lot.remaining_qty,
            "exit_price": price,
            "position_lot": lot.to_dict(),
        }
        if lot.remaining_qty <= EPS:
            self.lots_by_position.pop(position_id, None)
        return out

    def exit_order_qty(self, shadow_position_id: int) -> float:
        lot = self.lots_by_position.get(int(shadow_position_id))
        return 0.0 if lot is None else max(0.0, lot.remaining_qty)

    def open_lot(self, shadow_position_id: int) -> PositionLot | None:
        return self.lots_by_position.get(int(shadow_position_id))

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_id": "ccusdt_position_lot_ledger_state_v1",
            "open_lots": [lot.to_dict() for lot in self.lots_by_position.values()],
        }

    def compact_snapshot(self) -> dict[str, Any]:
        return {
            "schema_id": "ccusdt_position_lot_ledger_compact_v1",
            "open_lot_count": len(self.lots_by_position),
            "open_shadow_position_ids": sorted(self.lots_by_position),
        }
