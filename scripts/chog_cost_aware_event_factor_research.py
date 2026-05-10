from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
import warnings

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import ElasticNet, LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

try:  # Optional nonlinear hints. The script still runs without these packages.
    from lightgbm import LGBMRegressor
except Exception:  # pragma: no cover - optional dependency
    LGBMRegressor = None

try:
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover - optional dependency
    XGBRegressor = None


ROOT = Path("data/chog/v1")
DATE_DIR = Path("date")
DOCS_DIR = Path("docs")
RUN_TAG = "20260509"

EVENT_FEATURES = ROOT / "derived" / "memecoin_event_features"

LABELS_CSV = DATE_DIR / f"chog_event_cost_labels_{RUN_TAG}.csv"
FACTOR_SCORES_CSV = DATE_DIR / f"chog_first_principles_factor_scores_{RUN_TAG}.csv"
ML_SUMMARY_CSV = DATE_DIR / f"chog_cost_aware_ml_summary_{RUN_TAG}.csv"
REPORT_MD = DOCS_DIR / f"chog_cost_aware_first_principles_factor_research_{RUN_TAG}.md"

HORIZONS: dict[str, pd.Timedelta] = {
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "3h": pd.Timedelta(hours=3),
    "6h": pd.Timedelta(hours=6),
}
SLIPPAGE_BPS_PER_SIDE = [0, 50, 100, 200]
POOL_FEE_ONE_WAY = 0.01
ROUND_TRIP_POOL_FEE = POOL_FEE_ONE_WAY * 2.0
MIN_HISTORY_FOR_PERCENTILE = 100
MIN_FACTOR_ROWS = 120
MIN_ML_ROWS = 350
TOP_FEATURES_PER_FOLD = 28
RANDOM_STATE = 42


@dataclass(frozen=True)
class MainPool:
    address: str
    dex_id: str
    quote_symbol: str
    events: int
    chog_volume: float
    volume_share: float
    event_share: float


@dataclass(frozen=True)
class FactorSpec:
    name: str
    family: str
    role: str
    description: str
    binary: bool = False


def read_parquet_parts(path: Path) -> pd.DataFrame:
    parts = sorted(path.rglob("*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no parquet parts found under {path}")
    return pd.concat([pd.read_parquet(part) for part in parts], ignore_index=True)


def pct(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value) * 100:.{digits}f}%"


def raw_num(value: float | int | None, digits: int = 4) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}f}"


def num(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    value = float(value)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"{sign}{value / 1_000_000_000:.{digits}f}B"
    if value >= 1_000_000:
        return f"{sign}{value / 1_000_000:.{digits}f}M"
    if value >= 1_000:
        return f"{sign}{value / 1_000:.{digits}f}k"
    return f"{sign}{value:.{digits}f}"


def short_hex(value: str, chars: int = 6) -> str:
    if not isinstance(value, str) or len(value) <= 2 * chars + 2:
        return str(value)
    return f"{value[: chars + 2]}...{value[-chars:]}"


def markdown_table(rows: Iterable[dict[str, object]], columns: list[tuple[str, str]]) -> str:
    rows = list(rows)
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(title for title, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(key, "")) for _, key in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def safe_divide(numer: pd.Series, denom: pd.Series) -> pd.Series:
    return (numer / denom.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def expanding_percentile(values: pd.Series, min_history: int = MIN_HISTORY_FOR_PERCENTILE) -> pd.Series:
    history: list[float] = []
    out: list[float] = []
    for value in values.astype(float):
        if len(history) >= min_history and np.isfinite(value):
            lo = bisect_left(history, float(value))
            hi = bisect_right(history, float(value))
            out.append(float((lo + hi) / (2.0 * len(history))))
        else:
            out.append(np.nan)
        if np.isfinite(value):
            insort(history, float(value))
    return pd.Series(out, index=values.index, dtype=float)


def choose_main_pool(events: pd.DataFrame) -> MainPool:
    summary = (
        events.groupby(["dex_id", "pool_address", "quote_symbol"], dropna=False)
        .agg(
            events=("transaction_hash", "size"),
            chog_volume=("chog_amount", "sum"),
        )
        .reset_index()
        .sort_values(["chog_volume", "events"], ascending=False)
    )
    row = summary.iloc[0]
    return MainPool(
        address=str(row["pool_address"]),
        dex_id=str(row["dex_id"]),
        quote_symbol=str(row["quote_symbol"]),
        events=int(row["events"]),
        chog_volume=float(row["chog_volume"]),
        volume_share=float(row["chog_volume"] / summary["chog_volume"].sum()),
        event_share=float(row["events"] / summary["events"].sum()),
    )


def prepare_events(raw_events: pd.DataFrame) -> tuple[pd.DataFrame, MainPool]:
    events = raw_events.copy()
    events["block_dt"] = pd.to_datetime(events["block_datetime_utc"], utc=True)
    events = events.sort_values(
        ["block_dt", "block_number", "transaction_index", "log_index", "transaction_hash"]
    ).reset_index(drop=True)
    events["event_id"] = np.arange(len(events), dtype=np.int64)
    events["is_buy"] = events["direction"].eq("buy_chog")
    events["is_sell"] = events["direction"].eq("sell_chog")
    events["effective_gas_gwei"] = events["effective_gas_price"].astype(float) / 1e9
    events["base_fee_gwei"] = events["base_fee_per_gas"].astype(float) / 1e9
    events["priority_fee_gwei"] = events["priority_fee_per_gas_proxy"].astype(float) / 1e9
    events["gas_cost_quote"] = (
        events["gas_used"].astype(float) * events["effective_gas_price"].astype(float) / 1e18
    )
    events["log_chog_amount"] = np.log1p(events["chog_amount"].clip(lower=0.0))
    events["log_quote_amount"] = np.log1p(events["quote_amount"].clip(lower=0.0))

    main_pool = choose_main_pool(events)
    events["is_main_pool"] = events["pool_address"].eq(main_pool.address)
    events["main_pool_event"] = events["is_main_pool"].astype(float)
    events["non_main_event"] = (~events["is_main_pool"]).astype(float)
    events["buy_count_event"] = events["is_buy"].astype(float)
    events["sell_count_event"] = events["is_sell"].astype(float)
    events["main_buy_count_event"] = (events["is_main_pool"] & events["is_buy"]).astype(float)
    events["main_sell_count_event"] = (events["is_main_pool"] & events["is_sell"]).astype(float)
    events["main_chog_volume_event"] = events["chog_amount"].where(events["is_main_pool"], 0.0)
    events["main_quote_volume_event"] = events["quote_amount"].where(events["is_main_pool"], 0.0)
    events["non_main_chog_volume_event"] = events["chog_amount"].where(~events["is_main_pool"], 0.0)
    events["non_main_quote_volume_event"] = events["quote_amount"].where(~events["is_main_pool"], 0.0)
    events["main_net_flow_event"] = events["signed_chog_flow"].where(events["is_main_pool"], 0.0)
    events["non_main_net_flow_event"] = events["signed_chog_flow"].where(~events["is_main_pool"], 0.0)
    events["main_sell_flow_event"] = events["chog_amount"].where(
        events["is_main_pool"] & events["is_sell"], 0.0
    )

    events["trade_size_percentile_past"] = expanding_percentile(events["chog_amount"])
    events["gas_regime_percentile_past"] = expanding_percentile(events["effective_gas_gwei"])
    for threshold in [50, 90, 95, 99]:
        q = threshold / 100.0
        events[f"is_trade_p{threshold}_past"] = events["trade_size_percentile_past"].ge(q)
    events["is_small_trade_p50_past"] = events["trade_size_percentile_past"].le(0.50)

    events["large_buy_p90_event"] = (events["is_trade_p90_past"] & events["is_buy"]).astype(float)
    events["large_sell_p90_event"] = (events["is_trade_p90_past"] & events["is_sell"]).astype(float)
    events["large_buy_flow_event"] = events["chog_amount"].where(
        events["is_trade_p90_past"] & events["is_buy"], 0.0
    )
    events["large_sell_flow_event"] = events["chog_amount"].where(
        events["is_trade_p90_past"] & events["is_sell"], 0.0
    )
    events["large_volume_event"] = events["chog_amount"].where(events["is_trade_p90_past"], 0.0)
    events["small_buy_event"] = (events["is_small_trade_p50_past"] & events["is_buy"]).astype(float)
    events["small_sell_event"] = (events["is_small_trade_p50_past"] & events["is_sell"]).astype(float)
    events["small_volume_event"] = events["chog_amount"].where(events["is_small_trade_p50_past"], 0.0)
    return events, main_pool


def rolling_by_time(events: pd.DataFrame, column: str, window: str, op: str = "sum") -> pd.Series:
    series = events.set_index("block_dt")[column].astype(float)
    rolled = series.rolling(window, closed="left")
    if op == "sum":
        result = rolled.sum()
    elif op == "count":
        result = rolled.count()
    elif op == "median":
        result = rolled.median()
    elif op == "mean":
        result = rolled.mean()
    else:
        raise ValueError(f"unsupported rolling op: {op}")
    return pd.Series(result.to_numpy(), index=events.index, dtype=float)


def add_asof_main_prices(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    main_prices = events.loc[
        events["is_main_pool"] & events["price_quote_per_chog"].gt(0),
        ["block_dt", "price_quote_per_chog"],
    ].sort_values("block_dt")
    base = events[["block_dt"]].copy()
    prev = pd.merge_asof(
        base,
        main_prices.rename(columns={"price_quote_per_chog": "prev_main_price"}),
        on="block_dt",
        direction="backward",
        allow_exact_matches=False,
    )
    events["prev_main_price"] = prev["prev_main_price"].to_numpy()
    for label, delta in [("5m", "5min"), ("15m", "15min"), ("1h", "1h")]:
        query = base.copy()
        query["query_dt"] = query["block_dt"] - pd.Timedelta(delta)
        merged = pd.merge_asof(
            query.sort_values("query_dt"),
            main_prices.rename(columns={"block_dt": "query_dt", "price_quote_per_chog": "past_price"}),
            on="query_dt",
            direction="backward",
            allow_exact_matches=True,
        ).sort_index()
        past = merged["past_price"].to_numpy()
        events[f"main_price_return_past_{label}"] = (
            events["prev_main_price"].astype(float).to_numpy() / past - 1.0
        )
    events["current_price_impact_vs_prev_main"] = np.where(
        events["is_main_pool"] & events["prev_main_price"].gt(0),
        events["price_quote_per_chog"] / events["prev_main_price"] - 1.0,
        np.nan,
    )
    return events


def build_feature_frame(events: pd.DataFrame) -> pd.DataFrame:
    events = add_asof_main_prices(events)
    for label, window in [("5m", "5min"), ("15m", "15min"), ("1h", "1h")]:
        minutes = pd.Timedelta(window).total_seconds() / 60.0
        events[f"all_event_count_{label}"] = rolling_by_time(events, "event_id", window, "count")
        events[f"main_event_count_{label}"] = rolling_by_time(events, "main_pool_event", window)
        events[f"non_main_event_count_{label}"] = rolling_by_time(events, "non_main_event", window)
        events[f"main_buy_count_{label}"] = rolling_by_time(events, "main_buy_count_event", window)
        events[f"main_sell_count_{label}"] = rolling_by_time(events, "main_sell_count_event", window)
        events[f"main_chog_volume_{label}"] = rolling_by_time(events, "main_chog_volume_event", window)
        events[f"main_quote_volume_{label}"] = rolling_by_time(events, "main_quote_volume_event", window)
        events[f"non_main_chog_volume_{label}"] = rolling_by_time(
            events, "non_main_chog_volume_event", window
        )
        events[f"main_net_flow_{label}"] = rolling_by_time(events, "main_net_flow_event", window)
        events[f"non_main_net_flow_{label}"] = rolling_by_time(
            events, "non_main_net_flow_event", window
        )
        events[f"large_buy_count_{label}"] = rolling_by_time(events, "large_buy_p90_event", window)
        events[f"large_sell_count_{label}"] = rolling_by_time(events, "large_sell_p90_event", window)
        events[f"large_buy_flow_{label}"] = rolling_by_time(events, "large_buy_flow_event", window)
        events[f"large_sell_flow_{label}"] = rolling_by_time(events, "large_sell_flow_event", window)
        events[f"large_volume_{label}"] = rolling_by_time(events, "large_volume_event", window)
        events[f"small_buy_count_{label}"] = rolling_by_time(events, "small_buy_event", window)
        events[f"small_sell_count_{label}"] = rolling_by_time(events, "small_sell_event", window)
        events[f"small_volume_{label}"] = rolling_by_time(events, "small_volume_event", window)
        events[f"main_sell_pressure_{label}"] = rolling_by_time(events, "main_sell_flow_event", window)
        events[f"gas_cost_quote_median_{label}"] = rolling_by_time(events, "gas_cost_quote", window, "median")
        events[f"effective_gas_gwei_median_{label}"] = rolling_by_time(
            events, "effective_gas_gwei", window, "median"
        )

        all_volume = events[f"main_chog_volume_{label}"] + events[f"non_main_chog_volume_{label}"]
        all_count = events[f"all_event_count_{label}"]
        main_count = events[f"main_event_count_{label}"]
        large_count = events[f"large_buy_count_{label}"] + events[f"large_sell_count_{label}"]
        small_count = events[f"small_buy_count_{label}"] + events[f"small_sell_count_{label}"]

        events[f"all_event_density_per_min_{label}"] = all_count / minutes
        events[f"main_event_density_per_min_{label}"] = main_count / minutes
        events[f"log_main_quote_volume_{label}"] = np.log1p(events[f"main_quote_volume_{label}"])
        events[f"main_flow_pressure_{label}"] = safe_divide(
            events[f"main_net_flow_{label}"], events[f"main_chog_volume_{label}"]
        ).fillna(0.0)
        events[f"non_main_flow_pressure_{label}"] = safe_divide(
            events[f"non_main_net_flow_{label}"], events[f"non_main_chog_volume_{label}"]
        ).fillna(0.0)
        events[f"main_vs_non_main_flow_divergence_{label}"] = (
            events[f"main_flow_pressure_{label}"] - events[f"non_main_flow_pressure_{label}"]
        )
        events[f"non_main_volume_share_{label}"] = safe_divide(
            events[f"non_main_chog_volume_{label}"], all_volume
        ).fillna(0.0)
        events[f"main_buy_sell_count_imbalance_{label}"] = safe_divide(
            events[f"main_buy_count_{label}"] - events[f"main_sell_count_{label}"],
            events[f"main_buy_count_{label}"] + events[f"main_sell_count_{label}"],
        ).fillna(0.0)
        events[f"large_net_flow_{label}"] = (
            events[f"large_buy_flow_{label}"] - events[f"large_sell_flow_{label}"]
        )
        events[f"large_trade_count_share_{label}"] = safe_divide(large_count, all_count).fillna(0.0)
        events[f"large_trade_volume_share_{label}"] = safe_divide(
            events[f"large_volume_{label}"], all_volume
        ).fillna(0.0)
        events[f"small_count_imbalance_{label}"] = safe_divide(
            events[f"small_buy_count_{label}"] - events[f"small_sell_count_{label}"], small_count
        ).fillna(0.0)
        events[f"small_trade_count_share_{label}"] = safe_divide(small_count, all_count).fillna(0.0)
        events[f"sell_pressure_absorbed_{label}"] = (
            events[f"main_sell_pressure_{label}"]
            * events[f"main_price_return_past_{label}"].clip(lower=0.0)
        ).fillna(0.0)

    events["main_quote_amount_median_1h"] = rolling_by_time(
        events, "main_quote_volume_event", "1h", "median"
    )
    events["current_is_buy"] = events["is_buy"].astype(float)
    events["current_is_sell"] = events["is_sell"].astype(float)
    events["current_is_large_trade_p90"] = events["is_trade_p90_past"].astype(float)
    events["current_is_large_trade_p95"] = events["is_trade_p95_past"].astype(float)
    events["current_large_buy_p90"] = (
        events["is_trade_p90_past"] & events["is_buy"]
    ).astype(float)
    events["current_large_sell_p90"] = (
        events["is_trade_p90_past"] & events["is_sell"]
    ).astype(float)
    events["current_large_sell_no_drop"] = (
        events["current_large_sell_p90"].eq(1.0)
        & events["current_price_impact_vs_prev_main"].ge(-0.005)
    ).astype(float)
    events["crowded_same_block"] = events["same_block_pool_event_count"].ge(2).astype(float)
    events["dust_trade_flag"] = events["quote_amount"].lt(10.0).astype(float)
    events["low_activity_flag"] = (
        events["main_event_count_15m"].lt(2.0) | events["main_quote_volume_15m"].lt(50.0)
    ).astype(float)
    return events


def build_cost_labels(features: pd.DataFrame, main_pool: MainPool) -> pd.DataFrame:
    main = features.loc[
        features["is_main_pool"] & features["price_quote_per_chog"].gt(0),
        [
            "event_id",
            "block_dt",
            "block_number",
            "transaction_hash",
            "log_index",
            "price_quote_per_chog",
            "quote_amount",
            "gas_cost_quote",
            "gas_cost_quote_median_15m",
            "main_quote_amount_median_1h",
            "main_event_count_15m",
            "main_quote_volume_15m",
        ],
    ].sort_values("block_dt").reset_index(drop=True)

    main_times = main["block_dt"].to_numpy(dtype="datetime64[ns]")
    main_prices = main["price_quote_per_chog"].astype(float).to_numpy()
    signal_times = main["block_dt"].to_numpy(dtype="datetime64[ns]")
    entry_idx = np.searchsorted(main_times, signal_times, side="right")

    fallback_quote = float(main["quote_amount"].where(main["quote_amount"].gt(0)).median())
    rows: list[pd.DataFrame] = []
    signal_base = main[
        [
            "event_id",
            "block_dt",
            "block_number",
            "transaction_hash",
            "log_index",
            "quote_amount",
            "gas_cost_quote",
            "gas_cost_quote_median_15m",
            "main_quote_amount_median_1h",
            "main_event_count_15m",
            "main_quote_volume_15m",
        ]
    ].copy()
    signal_base = signal_base.rename(columns={"block_dt": "signal_time"})

    reference_quote = signal_base["quote_amount"].where(signal_base["quote_amount"].gt(0))
    reference_quote = reference_quote.fillna(signal_base["main_quote_amount_median_1h"])
    reference_quote = reference_quote.fillna(fallback_quote).clip(lower=1e-12)
    nearby_gas_quote = signal_base["gas_cost_quote_median_15m"].fillna(signal_base["gas_cost_quote"])
    nearby_gas_quote = nearby_gas_quote.fillna(float(main["gas_cost_quote"].median()))
    gas_cost_return = (2.0 * nearby_gas_quote / reference_quote).replace([np.inf, -np.inf], np.nan)

    signal_base["reference_quote_amount"] = reference_quote
    signal_base["nearby_gas_quote_one_way"] = nearby_gas_quote
    signal_base["gas_cost_return"] = gas_cost_return
    signal_base["pool_fee_return"] = ROUND_TRIP_POOL_FEE
    signal_base["pool_fee_one_way"] = POOL_FEE_ONE_WAY
    signal_base["is_tradable_sample"] = (
        signal_base["reference_quote_amount"].ge(10.0)
        & signal_base["main_event_count_15m"].ge(2.0)
        & signal_base["main_quote_volume_15m"].ge(50.0)
        & signal_base["gas_cost_return"].le(0.05)
    )
    signal_base["pool_address"] = main_pool.address
    signal_base["dex_id"] = main_pool.dex_id
    signal_base["quote_symbol"] = main_pool.quote_symbol

    for horizon, delta in HORIZONS.items():
        horizon_times = (main["block_dt"] + delta).to_numpy(dtype="datetime64[ns]")
        exit_idx = np.searchsorted(main_times, horizon_times, side="right") - 1
        valid = (entry_idx < len(main_times)) & (exit_idx > entry_idx)
        valid_time_order = np.zeros(len(valid), dtype=bool)
        valid_time_order[valid] = main_times[exit_idx[valid]] > main_times[entry_idx[valid]]
        valid = valid & valid_time_order
        frame = signal_base.copy()
        frame["horizon"] = horizon
        frame["horizon_seconds"] = int(delta.total_seconds())
        frame["entry_time"] = np.datetime64("NaT")
        frame["exit_time"] = np.datetime64("NaT")
        frame["entry_price"] = np.nan
        frame["exit_price"] = np.nan
        frame.loc[valid, "entry_time"] = main_times[entry_idx[valid]]
        frame.loc[valid, "exit_time"] = main_times[exit_idx[valid]]
        frame.loc[valid, "entry_price"] = main_prices[entry_idx[valid]]
        frame.loc[valid, "exit_price"] = main_prices[exit_idx[valid]]
        frame["gross_return"] = frame["exit_price"] / frame["entry_price"] - 1.0
        frame["label_valid"] = valid
        for bps in SLIPPAGE_BPS_PER_SIDE:
            slip_return = 2.0 * bps / 10_000.0
            frame[f"net_return_slip_{bps}bps"] = (
                frame["gross_return"]
                - frame["pool_fee_return"]
                - frame["gas_cost_return"]
                - slip_return
            )
        rows.append(frame)

    labels = pd.concat(rows, ignore_index=True)
    labels["signal_time"] = pd.to_datetime(labels["signal_time"], utc=True).dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    labels["entry_time"] = pd.to_datetime(labels["entry_time"], utc=True).dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    labels["exit_time"] = pd.to_datetime(labels["exit_time"], utc=True).dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return labels


def factor_specs() -> list[FactorSpec]:
    specs = [
        FactorSpec("current_is_buy", "baseline_event_side", "direction", "current main-pool buy", True),
        FactorSpec("current_is_sell", "baseline_event_side", "risk_filter", "current main-pool sell", True),
        FactorSpec("log_chog_amount", "liquidity_impact", "direction", "current trade size"),
        FactorSpec(
            "trade_size_percentile_past",
            "liquidity_impact",
            "direction",
            "current trade size percentile using prior history",
        ),
        FactorSpec("current_is_large_trade_p90", "liquidity_impact", "event_type", "top decile trade", True),
        FactorSpec("current_large_buy_p90", "liquidity_impact", "event_type", "top decile buy", True),
        FactorSpec("current_large_sell_p90", "liquidity_impact", "event_type", "top decile sell", True),
        FactorSpec(
            "large_trade_volume_share_15m",
            "liquidity_impact",
            "risk_filter",
            "prior 15m large-trade volume share",
        ),
        FactorSpec("large_net_flow_15m", "liquidity_impact", "direction", "prior 15m large buy minus sell flow"),
        FactorSpec("log_main_quote_volume_15m", "liquidity_impact", "filter", "prior 15m main-pool quote volume"),
        FactorSpec("log_main_quote_volume_1h", "liquidity_impact", "filter", "prior 1h main-pool quote volume"),
        FactorSpec("main_flow_pressure_15m", "main_pool_absorption", "direction", "prior 15m main-pool net flow pressure"),
        FactorSpec("main_flow_pressure_1h", "main_pool_absorption", "direction", "prior 1h main-pool net flow pressure"),
        FactorSpec(
            "main_vs_non_main_flow_divergence_15m",
            "main_pool_absorption",
            "direction",
            "main-pool pressure minus non-main pressure, prior 15m",
        ),
        FactorSpec(
            "non_main_volume_share_15m",
            "main_pool_absorption",
            "risk_filter",
            "prior 15m non-main volume share",
        ),
        FactorSpec(
            "sell_pressure_absorbed_15m",
            "main_pool_absorption",
            "direction",
            "prior sell pressure with non-negative main-pool price path",
        ),
        FactorSpec(
            "current_large_sell_no_drop",
            "main_pool_absorption",
            "event_type",
            "large sell whose execution price did not drop more than 50 bps",
            True,
        ),
        FactorSpec("all_event_density_per_min_5m", "attention_crowding", "filter", "all-pool 5m event density"),
        FactorSpec("all_event_density_per_min_15m", "attention_crowding", "filter", "all-pool 15m event density"),
        FactorSpec("main_event_density_per_min_15m", "attention_crowding", "filter", "main-pool 15m event density"),
        FactorSpec("same_block_pool_event_count", "attention_crowding", "filter", "same-block pool event count"),
        FactorSpec("crowded_same_block", "attention_crowding", "event_type", "multiple pool events in same block", True),
        FactorSpec("effective_gas_gwei", "attention_crowding", "filter", "current effective gas regime"),
        FactorSpec("gas_regime_percentile_past", "attention_crowding", "filter", "gas percentile using prior history"),
        FactorSpec("small_count_imbalance_15m", "noise_filter", "risk_filter", "prior 15m small-trade count imbalance"),
        FactorSpec("small_trade_count_share_15m", "noise_filter", "risk_filter", "prior 15m small-trade count share"),
        FactorSpec("dust_trade_flag", "noise_filter", "risk_filter", "signal trade under 10 MON quote", True),
        FactorSpec("low_activity_flag", "noise_filter", "risk_filter", "low prior activity or volume", True),
    ]
    return specs


def labels_long(labels: pd.DataFrame) -> pd.DataFrame:
    id_cols = [
        "event_id",
        "horizon",
        "signal_time",
        "entry_time",
        "exit_time",
        "gross_return",
        "gas_cost_return",
        "pool_fee_return",
        "reference_quote_amount",
        "is_tradable_sample",
        "label_valid",
    ]
    frames = []
    for bps in SLIPPAGE_BPS_PER_SIDE:
        col = f"net_return_slip_{bps}bps"
        frame = labels[id_cols + [col]].copy()
        frame = frame.rename(columns={col: "net_return"})
        frame["slippage_bps_per_side"] = bps
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def score_factor_bucket(frame: pd.DataFrame, feature: str, label: str, binary: bool) -> dict[str, object] | None:
    data = frame[[feature, "gross_return", label]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < MIN_FACTOR_ROWS or data[feature].nunique(dropna=True) < 2:
        return None

    if binary:
        high = data[data[feature].gt(0)]
        low = data[data[feature].le(0)]
        if len(high) < 20 or len(low) < 20:
            return None
        high_gross = float(high["gross_return"].mean())
        low_gross = float(low["gross_return"].mean())
        favorable = high if high_gross >= low_gross else low
        unfavorable = low if high_gross >= low_gross else high
        favorable_bucket = "true" if high_gross >= low_gross else "false"
    else:
        try:
            quantiles = pd.qcut(data[feature], 10, labels=False, duplicates="drop")
        except ValueError:
            return None
        data = data.assign(bucket=quantiles)
        if data["bucket"].nunique(dropna=True) < 3:
            return None
        high = data[data["bucket"].eq(data["bucket"].max())]
        low = data[data["bucket"].eq(data["bucket"].min())]
        if len(high) < 20 or len(low) < 20:
            return None
        high_gross = float(high["gross_return"].mean())
        low_gross = float(low["gross_return"].mean())
        favorable = high if high_gross >= low_gross else low
        unfavorable = low if high_gross >= low_gross else high
        favorable_bucket = "high_decile" if high_gross >= low_gross else "low_decile"

    net = favorable[label]
    gross = favorable["gross_return"]
    gross_spearman = data[feature].corr(data["gross_return"], method="spearman")
    net_spearman = data[feature].corr(data[label], method="spearman")
    favorable_net_mean = float(net.mean())
    favorable_gross_mean = float(gross.mean())
    unfavorable_net_mean = float(unfavorable[label].mean())
    all_net_mean = float(data[label].mean())
    all_gross_mean = float(data["gross_return"].mean())
    return {
        "n": int(len(data)),
        "favorable_n": int(len(favorable)),
        "favorable_bucket": favorable_bucket,
        "spearman_gross": float(gross_spearman) if pd.notna(gross_spearman) else np.nan,
        "spearman_net": float(net_spearman) if pd.notna(net_spearman) else np.nan,
        "all_gross_mean": all_gross_mean,
        "all_net_mean": all_net_mean,
        "favorable_gross_mean": favorable_gross_mean,
        "favorable_net_mean": favorable_net_mean,
        "unfavorable_net_mean": unfavorable_net_mean,
        "top_minus_bottom_net": favorable_net_mean - unfavorable_net_mean,
        "favorable_positive_rate": float(net.gt(0).mean()),
        "favorable_gt_2pct_rate": float(net.gt(0.02).mean()),
        "favorable_gt_5pct_rate": float(net.gt(0.05).mean()),
        "gross_positive_net_failed": bool(favorable_gross_mean > 0 and favorable_net_mean <= 0),
        "crosses_fee_before_slippage": bool(favorable_net_mean > 0),
    }


def build_factor_scores(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    specs = factor_specs()
    feature_cols = [
        "event_id",
        *[spec.name for spec in specs if spec.name in features.columns],
    ]
    joined = labels.merge(features[feature_cols], on="event_id", how="left")
    rows: list[dict[str, object]] = []
    for spec in specs:
        if spec.name not in joined.columns:
            continue
        for horizon in HORIZONS:
            for bps in SLIPPAGE_BPS_PER_SIDE:
                subset = joined[
                    joined["horizon"].eq(horizon)
                    & joined["label_valid"]
                    & joined["is_tradable_sample"]
                    & joined["slippage_bps_per_side"].eq(bps)
                ].copy()
                score = score_factor_bucket(subset, spec.name, "net_return", spec.binary)
                if score is None:
                    continue
                rows.append(
                    {
                        "factor": spec.name,
                        "factor_family": spec.family,
                        "factor_role": spec.role,
                        "description": spec.description,
                        "horizon": horizon,
                        "slippage_bps_per_side": bps,
                        **score,
                    }
                )
    if not rows:
        return pd.DataFrame()
    scores = pd.DataFrame(rows)
    scores["abs_spearman_net"] = scores["spearman_net"].abs()
    scores["candidate_status"] = np.select(
        [
            scores["gross_positive_net_failed"],
            scores["favorable_net_mean"].gt(0.01) & scores["favorable_positive_rate"].gt(0.55),
            scores["favorable_net_mean"].gt(0),
        ],
        ["gross_only_cost_failed", "cost_aware_candidate", "barely_positive_after_cost"],
        default="failed_or_filter_only",
    )
    return scores.sort_values(
        ["horizon", "slippage_bps_per_side", "candidate_status", "favorable_net_mean"],
        ascending=[True, True, True, False],
    ).reset_index(drop=True)


def candidate_feature_columns(features: pd.DataFrame) -> list[str]:
    names = [spec.name for spec in factor_specs() if spec.name in features.columns]
    extra_prefixes = (
        "main_event_count_",
        "main_quote_volume_",
        "main_net_flow_",
        "non_main_net_flow_",
        "large_buy_count_",
        "large_sell_count_",
        "large_buy_flow_",
        "large_sell_flow_",
        "gas_cost_quote_median_",
        "effective_gas_gwei_median_",
        "main_price_return_past_",
    )
    for col in features.columns:
        if col.startswith(extra_prefixes):
            names.append(col)
    numeric = []
    for col in dict.fromkeys(names):
        if col in features.columns and pd.api.types.is_numeric_dtype(features[col]):
            numeric.append(col)
    return numeric


def select_and_scale(
    x_train_raw: pd.DataFrame,
    y_train: pd.Series,
    x_test_raw: pd.DataFrame,
    feature_cols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    ranked: list[tuple[str, float]] = []
    for col in feature_cols:
        frame = pd.DataFrame({"x": x_train_raw[col], "y": y_train}).replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if len(frame) < 80 or frame["x"].nunique(dropna=True) < 3:
            continue
        corr = frame["x"].corr(frame["y"], method="spearman")
        if pd.notna(corr):
            ranked.append((col, abs(float(corr))))
    ranked.sort(key=lambda item: item[1], reverse=True)
    selected = [col for col, _ in ranked[:TOP_FEATURES_PER_FOLD]]
    if len(selected) < 5:
        return pd.DataFrame(), pd.DataFrame(), []

    x_train = x_train_raw[selected].replace([np.inf, -np.inf], np.nan)
    x_test = x_test_raw[selected].replace([np.inf, -np.inf], np.nan)
    medians = x_train.median(numeric_only=True)
    x_train = x_train.fillna(medians)
    x_test = x_test.fillna(medians)
    lower = x_train.quantile(0.01)
    upper = x_train.quantile(0.99)
    x_train = x_train.clip(lower=lower, upper=upper, axis=1)
    x_test = x_test.clip(lower=lower, upper=upper, axis=1)
    mean = x_train.mean()
    std = x_train.std(ddof=0).replace(0, np.nan)
    x_train = ((x_train - mean) / std).dropna(axis=1, how="any")
    kept = list(x_train.columns)
    if len(kept) < 5:
        return pd.DataFrame(), pd.DataFrame(), []
    x_test = (x_test[kept] - mean[kept]) / std[kept]
    x_test = x_test.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return x_train[kept], x_test[kept], kept


def regression_model_factories(horizon: str, bps: int) -> dict[str, Callable[[], object]]:
    factories: dict[str, Callable[[], object]] = {
        "ridge": lambda: Ridge(alpha=10.0),
        "elastic_net": lambda: ElasticNet(alpha=0.002, l1_ratio=0.20, max_iter=50_000),
    }
    if bps in {0, 100}:
        factories["random_forest"] = lambda: RandomForestRegressor(
            n_estimators=120,
            max_depth=4,
            min_samples_leaf=20,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    if bps == 100 and horizon in {"1h", "3h", "6h"} and LGBMRegressor is not None:
        factories["lightgbm"] = lambda: LGBMRegressor(
            n_estimators=90,
            learning_rate=0.04,
            max_depth=3,
            num_leaves=7,
            min_child_samples=25,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=RANDOM_STATE,
            verbosity=-1,
        )
    if bps == 100 and horizon in {"1h", "3h", "6h"} and XGBRegressor is not None:
        factories["xgboost"] = lambda: XGBRegressor(
            n_estimators=80,
            learning_rate=0.04,
            max_depth=2,
            min_child_weight=10,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=10.0,
            objective="reg:squarederror",
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
        )
    return factories


def classification_model_factories(bps: int, threshold: float) -> dict[str, Callable[[], object]]:
    factories: dict[str, Callable[[], object]] = {
        "logistic": lambda: LogisticRegression(
            C=0.5,
            max_iter=2_000,
            class_weight="balanced",
            solver="lbfgs",
        )
    }
    if bps == 100 and threshold == 0.0:
        factories["random_forest_classifier"] = lambda: RandomForestClassifier(
            n_estimators=120,
            max_depth=4,
            min_samples_leaf=20,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            class_weight="balanced_subsample",
        )
    return factories


def summarize_oos(
    oos: pd.DataFrame,
    horizon: str,
    bps: int,
    model_name: str,
    target_type: str,
    target_threshold: float,
    folds_used: int,
    feature_counts: list[int],
) -> dict[str, object]:
    oos = oos.replace([np.inf, -np.inf], np.nan).dropna(subset=["actual_net_return", "score"])
    top = oos[oos["is_top_train_decile"]]
    actual_class = oos["actual_net_return"].gt(target_threshold)
    auc = np.nan
    if target_type == "classification" and actual_class.nunique() == 2:
        try:
            auc = float(roc_auc_score(actual_class.astype(int), oos["score"]))
        except ValueError:
            auc = np.nan
    return {
        "horizon": horizon,
        "slippage_bps_per_side": bps,
        "model": model_name,
        "target_type": target_type,
        "target_threshold": target_threshold,
        "folds_used": folds_used,
        "mean_features_per_fold": float(np.mean(feature_counts)) if feature_counts else np.nan,
        "n_oos": int(len(oos)),
        "n_top_decile": int(len(top)),
        "oos_spearman": float(oos["score"].corr(oos["actual_net_return"], method="spearman"))
        if len(oos) >= 40 and oos["score"].nunique() >= 3
        else np.nan,
        "oos_auc": auc,
        "all_mean_net_return": float(oos["actual_net_return"].mean()) if len(oos) else np.nan,
        "top_decile_mean_net_return": float(top["actual_net_return"].mean()) if len(top) else np.nan,
        "top_decile_lift": float(top["actual_net_return"].mean() - oos["actual_net_return"].mean())
        if len(top) and len(oos)
        else np.nan,
        "top_decile_positive_rate": float(top["actual_net_return"].gt(0).mean()) if len(top) else np.nan,
        "top_decile_gt_2pct_rate": float(top["actual_net_return"].gt(0.02).mean()) if len(top) else np.nan,
        "top_decile_gt_5pct_rate": float(top["actual_net_return"].gt(0.05).mean()) if len(top) else np.nan,
        "break_even_exceedance_rate": float(top["actual_net_return"].gt(0).mean()) if len(top) else np.nan,
    }


def run_walk_forward_model(
    data: pd.DataFrame,
    feature_cols: list[str],
    horizon: str,
    bps: int,
    model_name: str,
    target_type: str,
    target_threshold: float,
    factory: Callable[[], object],
) -> dict[str, object] | None:
    if len(data) < MIN_ML_ROWS:
        return None
    split_count = min(5, max(2, len(data) // 700))
    splitter = TimeSeriesSplit(n_splits=split_count)
    oos_frames: list[pd.DataFrame] = []
    folds_used = 0
    feature_counts: list[int] = []

    for fold, (train_idx, test_idx) in enumerate(splitter.split(data), start=1):
        train = data.iloc[train_idx]
        test = data.iloc[test_idx]
        if len(train) < 180 or len(test) < 40:
            continue
        y_train_reg = train["net_return"].astype(float)
        if target_type == "classification":
            y_train = y_train_reg.gt(target_threshold).astype(int)
            if y_train.nunique() < 2 or y_train.value_counts().min() < 12:
                continue
            y_for_selection = y_train.astype(float)
        else:
            y_train = y_train_reg
            y_for_selection = y_train_reg

        x_train, x_test, selected = select_and_scale(
            train[feature_cols], y_for_selection, test[feature_cols], feature_cols
        )
        if not selected:
            continue

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=ConvergenceWarning)
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            model = factory()
            model.fit(x_train, y_train)

        if target_type == "classification" and hasattr(model, "predict_proba"):
            train_score = model.predict_proba(x_train)[:, 1]
            test_score = model.predict_proba(x_test)[:, 1]
        else:
            train_score = np.asarray(model.predict(x_train), dtype=float)
            test_score = np.asarray(model.predict(x_test), dtype=float)

        threshold = float(pd.Series(train_score).quantile(0.90))
        oos_frames.append(
            pd.DataFrame(
                {
                    "fold": fold,
                    "actual_net_return": test["net_return"].to_numpy(dtype=float),
                    "score": test_score,
                    "is_top_train_decile": test_score >= threshold,
                }
            )
        )
        folds_used += 1
        feature_counts.append(len(selected))

    if not oos_frames:
        return None
    return summarize_oos(
        pd.concat(oos_frames, ignore_index=True),
        horizon=horizon,
        bps=bps,
        model_name=model_name,
        target_type=target_type,
        target_threshold=target_threshold,
        folds_used=folds_used,
        feature_counts=feature_counts,
    )


def build_ml_summary(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    feature_cols = candidate_feature_columns(features)
    joined = labels.merge(features[["event_id", *feature_cols]], on="event_id", how="left")
    joined = joined[joined["label_valid"] & joined["is_tradable_sample"]].copy()
    joined = joined.sort_values(["signal_time", "event_id", "horizon", "slippage_bps_per_side"])
    rows: list[dict[str, object]] = []
    for horizon in HORIZONS:
        for bps in SLIPPAGE_BPS_PER_SIDE:
            subset = joined[
                joined["horizon"].eq(horizon) & joined["slippage_bps_per_side"].eq(bps)
            ].copy()
            subset = subset.replace([np.inf, -np.inf], np.nan).dropna(subset=["net_return"])
            if len(subset) < MIN_ML_ROWS:
                continue
            for model_name, factory in regression_model_factories(horizon, bps).items():
                result = run_walk_forward_model(
                    subset,
                    feature_cols,
                    horizon,
                    bps,
                    model_name,
                    "regression",
                    0.0,
                    factory,
                )
                if result is not None:
                    rows.append(result)
            for threshold in [0.0, 0.02, 0.05]:
                if subset["net_return"].gt(threshold).nunique() < 2:
                    continue
                for model_name, factory in classification_model_factories(bps, threshold).items():
                    result = run_walk_forward_model(
                        subset,
                        feature_cols,
                        horizon,
                        bps,
                        model_name,
                        "classification",
                        threshold,
                        factory,
                    )
                    if result is not None:
                        rows.append(result)
    if not rows:
        return pd.DataFrame()
    summary = pd.DataFrame(rows)
    summary["research_status"] = np.select(
        [
            summary["top_decile_mean_net_return"].gt(0.01)
            & summary["top_decile_positive_rate"].gt(0.55),
            summary["top_decile_mean_net_return"].gt(0),
        ],
        ["possible_candidate", "barely_positive"],
        default="failed_after_cost",
    )
    return summary.sort_values(
        ["horizon", "slippage_bps_per_side", "research_status", "top_decile_mean_net_return"],
        ascending=[True, True, True, False],
    ).reset_index(drop=True)


def validate_labels(labels: pd.DataFrame) -> None:
    valid = labels[labels["label_valid"]].copy()
    signal = pd.to_datetime(valid["signal_time"], utc=True)
    entry = pd.to_datetime(valid["entry_time"], utc=True)
    exit_ = pd.to_datetime(valid["exit_time"], utc=True)
    if not entry.gt(signal).all():
        raise AssertionError("entry_time must be later than signal_time for every valid label")
    if not exit_.gt(entry).all():
        raise AssertionError("exit_time must be later than entry_time for every valid label")
    for bps in SLIPPAGE_BPS_PER_SIDE:
        net_col = f"net_return_slip_{bps}bps"
        if not valid[net_col].lt(valid["gross_return"]).all():
            raise AssertionError(f"{net_col} must be lower than gross_return")
    for lower, higher in zip(SLIPPAGE_BPS_PER_SIDE, SLIPPAGE_BPS_PER_SIDE[1:]):
        low_col = f"net_return_slip_{lower}bps"
        high_col = f"net_return_slip_{higher}bps"
        if not valid[high_col].le(valid[low_col]).all():
            raise AssertionError("net return must not increase as slippage stress rises")
        low_rate = valid[low_col].gt(0).mean()
        high_rate = valid[high_col].gt(0).mean()
        if high_rate > low_rate + 1e-12:
            raise AssertionError("positive rate must not rise as slippage stress rises")


def gross_net_summary(labels: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for horizon in HORIZONS:
        subset = labels[labels["horizon"].eq(horizon) & labels["label_valid"]].copy()
        tradeable = subset[subset["is_tradable_sample"]]
        for bps in SLIPPAGE_BPS_PER_SIDE:
            net_col = f"net_return_slip_{bps}bps"
            rows.append(
                {
                    "horizon": horizon,
                    "slippage_bps_per_side": bps,
                    "valid_labels": int(len(subset)),
                    "tradable_labels": int(len(tradeable)),
                    "gross_mean": float(tradeable["gross_return"].mean()) if len(tradeable) else np.nan,
                    "net_mean": float(tradeable[net_col].mean()) if len(tradeable) else np.nan,
                    "gross_positive_rate": float(tradeable["gross_return"].gt(0).mean())
                    if len(tradeable)
                    else np.nan,
                    "net_positive_rate": float(tradeable[net_col].gt(0).mean())
                    if len(tradeable)
                    else np.nan,
                    "net_gt_2pct_rate": float(tradeable[net_col].gt(0.02).mean())
                    if len(tradeable)
                    else np.nan,
                }
            )
    return pd.DataFrame(rows)


def format_gross_net_rows(summary: pd.DataFrame, bps: int = 0) -> list[dict[str, object]]:
    frame = summary[summary["slippage_bps_per_side"].eq(bps)].copy()
    return [
        {
            "horizon": row["horizon"],
            "labels": f"{int(row['tradable_labels']):,}/{int(row['valid_labels']):,}",
            "gross_mean": pct(row["gross_mean"]),
            "net_mean": pct(row["net_mean"]),
            "gross_pos": pct(row["gross_positive_rate"]),
            "net_pos": pct(row["net_positive_rate"]),
            "net_gt_2": pct(row["net_gt_2pct_rate"]),
        }
        for _, row in frame.iterrows()
    ]


def format_factor_rows(frame: pd.DataFrame, rows: int = 10) -> list[dict[str, object]]:
    frame = frame.head(rows)
    return [
        {
            "factor": row["factor"],
            "family": row["factor_family"],
            "horizon": row["horizon"],
            "slip": int(row["slippage_bps_per_side"]),
            "bucket": row["favorable_bucket"],
            "gross": pct(row["favorable_gross_mean"]),
            "net": pct(row["favorable_net_mean"]),
            "pos": pct(row["favorable_positive_rate"]),
            "status": row["candidate_status"],
        }
        for _, row in frame.iterrows()
    ]


def format_ml_rows(frame: pd.DataFrame, rows: int = 10) -> list[dict[str, object]]:
    frame = frame.head(rows)
    return [
        {
            "horizon": row["horizon"],
            "slip": int(row["slippage_bps_per_side"]),
            "model": row["model"],
            "target": row["target_type"]
            if row["target_type"] == "regression"
            else f">{pct(row['target_threshold'], 0)}",
            "n": int(row["n_oos"]),
            "top_n": int(row["n_top_decile"]),
            "top_mean": pct(row["top_decile_mean_net_return"]),
            "lift": pct(row["top_decile_lift"]),
            "hit": pct(row["top_decile_positive_rate"]),
            "status": row["research_status"],
        }
        for _, row in frame.iterrows()
    ]


def build_report(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    factor_scores: pd.DataFrame,
    ml_summary: pd.DataFrame,
    main_pool: MainPool,
) -> str:
    gross_net = gross_net_summary(labels)
    valid_labels = labels[labels["label_valid"]]
    tradable_rate = float(valid_labels["is_tradable_sample"].mean()) if len(valid_labels) else np.nan

    gross_only = factor_scores[
        factor_scores["gross_positive_net_failed"]
        & factor_scores["slippage_bps_per_side"].isin([0, 100])
    ].sort_values(["favorable_gross_mean", "favorable_net_mean"], ascending=[False, True])
    event_cross = factor_scores[
        factor_scores["factor_role"].eq("event_type")
        & factor_scores["slippage_bps_per_side"].eq(0)
        & factor_scores["favorable_net_mean"].gt(0)
    ].sort_values(["favorable_net_mean", "favorable_positive_rate"], ascending=False)
    risk_filters = factor_scores[
        factor_scores["factor_role"].isin(["risk_filter", "filter"])
        & factor_scores["slippage_bps_per_side"].eq(0)
    ].sort_values(["favorable_net_mean", "favorable_positive_rate"], ascending=[True, True])
    candidates = factor_scores[
        factor_scores["candidate_status"].eq("cost_aware_candidate")
        & factor_scores["slippage_bps_per_side"].isin([0, 50])
    ].sort_values(["favorable_net_mean", "favorable_positive_rate"], ascending=False)

    family_failure = (
        factor_scores[factor_scores["slippage_bps_per_side"].eq(0)]
        .groupby("factor_family", dropna=False)
        .agg(
            tests=("factor", "size"),
            cost_failed=("gross_positive_net_failed", "sum"),
            mean_net=("favorable_net_mean", "mean"),
            best_net=("favorable_net_mean", "max"),
            candidates=("candidate_status", lambda s: int((s == "cost_aware_candidate").sum())),
        )
        .reset_index()
        .sort_values(["candidates", "best_net"], ascending=[True, True])
    )
    family_rows = [
        {
            "family": row["factor_family"],
            "tests": int(row["tests"]),
            "cost_failed": int(row["cost_failed"]),
            "mean_net": pct(row["mean_net"]),
            "best_net": pct(row["best_net"]),
            "candidates": int(row["candidates"]),
        }
        for _, row in family_failure.iterrows()
    ]

    ml_top = (
        ml_summary[ml_summary["slippage_bps_per_side"].isin([0, 100])]
        .sort_values(["top_decile_mean_net_return", "top_decile_lift"], ascending=False)
        if not ml_summary.empty
        else ml_summary
    )
    ml_failed = (
        ml_summary[ml_summary["research_status"].eq("failed_after_cost")]
        .sort_values(["top_decile_mean_net_return"], ascending=True)
        if not ml_summary.empty
        else ml_summary
    )

    continuation = "没有"
    if not candidates.empty:
        stable_families = sorted(candidates["factor_family"].unique())
        continuation = "、".join(stable_families)

    return f"""# CHOG 成本感知一阶原理事件因子研究

状态: 2026-05-09。输入只使用本地 `derived/memecoin_event_features`，不继续采集链上数据。本报告目标是筛选候选因子族，不生成交易规则。

复现命令:

```bash
python scripts/chog_cost_aware_event_factor_research.py
```

输出:

```text
{LABELS_CSV.as_posix()}
{FACTOR_SCORES_CSV.as_posix()}
{ML_SUMMARY_CSV.as_posix()}
{REPORT_MD.as_posix()}
```

## 1. 样本和主池

事件特征共 `{len(features):,}` 行，时间从 `{features['block_datetime_utc'].min()}` 到 `{features['block_datetime_utc'].max()}`。本轮只把 `nad-fun / CHOG-MON` 主池事件作为可入场信号，非主池事件只进入历史窗口特征。

自动识别主池: `{main_pool.dex_id}` / `{short_hex(main_pool.address)}` / quote `{main_pool.quote_symbol}`，事件 `{main_pool.events:,}`，成交量占比 `{pct(main_pool.volume_share)}`，事件占比 `{pct(main_pool.event_share)}`。

有效 label `{len(valid_labels):,}` 行，其中可交易样本占 `{pct(tradable_rate)}`。不可交易样本定义为信号名义金额过小、前 15m 主池活跃/成交不足或双边 gas 超过 5%，它们保留在 label 文件里但不进入因子/ML 主评分。

## 2. Label 和成本

- entry: 信号后下一个主池 swap，严格晚于 signal time。
- exit: horizon 前最近一个主池 swap，严格晚于 entry。
- horizons: `5m`, `15m`, `1h`, `3h`, `6h`。
- fee: 主池 `fee=10000`，按 1% one-way，round trip 2%。
- gas: 使用信号前 15m gas 成本中位数估计双边 gas，占信号 quote notional 的比例。
- slippage stress: `0bps`, `50bps`, `100bps`, `200bps` per side。

0 bps slippage 下的 gross vs net:

{markdown_table(format_gross_net_rows(gross_net, 0), [("Horizon", "horizon"), ("Tradable/Valid", "labels"), ("Gross Mean", "gross_mean"), ("Net Mean", "net_mean"), ("Gross >0", "gross_pos"), ("Net >0", "net_pos"), ("Net >2%", "net_gt_2")])}

100 bps per-side slippage 下:

{markdown_table(format_gross_net_rows(gross_net, 100), [("Horizon", "horizon"), ("Tradable/Valid", "labels"), ("Gross Mean", "gross_mean"), ("Net Mean", "net_mean"), ("Gross >0", "gross_pos"), ("Net >0", "net_pos"), ("Net >2%", "net_gt_2")])}

## 3. Gross 看起来有效但扣成本失效

下面这些行的有利桶 gross return 为正，但扣 2% fee、gas 和对应滑点后 net return 不再为正。这是本轮最重要的否决结果。

{markdown_table(format_factor_rows(gross_only, 12), [("Factor", "factor"), ("Family", "family"), ("Horizon", "horizon"), ("Slip", "slip"), ("Bucket", "bucket"), ("Gross", "gross"), ("Net", "net"), ("Net >0", "pos"), ("Status", "status")])}

## 4. 能跨过 2% round-trip fee 的事件类型

只看 0 bps slippage，也就是已经扣 2% 主池费和 gas、但未额外施加滑点压力。能留下正 net 的事件类型如下；如果行很少，说明事件形态本身不足以覆盖 taker 成本。

{markdown_table(format_factor_rows(event_cross, 12), [("Factor", "factor"), ("Family", "family"), ("Horizon", "horizon"), ("Slip", "slip"), ("Bucket", "bucket"), ("Gross", "gross"), ("Net", "net"), ("Net >0", "pos"), ("Status", "status")])}

## 5. 更像风控过滤器的因子

这些变量的解释价值主要在“不买/退出/过滤”，而不是方向做多。小单、低活跃和拥挤/gas 环境在扣费后尤其容易吞掉 gross 边际。

{markdown_table(format_factor_rows(risk_filters, 12), [("Factor", "factor"), ("Family", "family"), ("Horizon", "horizon"), ("Slip", "slip"), ("Bucket", "bucket"), ("Gross", "gross"), ("Net", "net"), ("Net >0", "pos"), ("Status", "status")])}

## 6. Walk-forward ML 筛选

ML 只用于候选因子筛选。每个 fold 只用训练段做特征选择、winsorize、median fill、标准化和 top-decile 预测阈值；测试段只按训练阈值判定 top bucket。模型覆盖 Ridge/ElasticNet/Logistic 基准，RandomForest 作为非线性提示；若本机已安装 LightGBM/XGBoost，则只在 100 bps、1h/3h/6h regression 上做轻量提示。

Top OOS rows:

{markdown_table(format_ml_rows(ml_top, 12), [("Horizon", "horizon"), ("Slip", "slip"), ("Model", "model"), ("Target", "target"), ("N", "n"), ("Top N", "top_n"), ("Top Mean", "top_mean"), ("Lift", "lift"), ("Hit", "hit"), ("Status", "status")])}

失败/负向 OOS rows:

{markdown_table(format_ml_rows(ml_failed, 10), [("Horizon", "horizon"), ("Slip", "slip"), ("Model", "model"), ("Target", "target"), ("N", "n"), ("Top N", "top_n"), ("Top Mean", "top_mean"), ("Lift", "lift"), ("Hit", "hit"), ("Status", "status")])}

## 7. 不可交易或失败的因子族

按 0 bps slippage 聚合，`cost_failed` 表示 gross 有正边际但扣费后失效的测试数。

{markdown_table(family_rows, [("Family", "family"), ("Tests", "tests"), ("Cost Failed", "cost_failed"), ("Mean Net", "mean_net"), ("Best Net", "best_net"), ("Candidates", "candidates")])}

## 8. 当前结论

1. 小时级 IC 的乐观读法被成本明显压缩；事件级 label 显示，2% round-trip fee 是主约束，额外 100 bps per-side slippage 会继续降低 positive rate。
2. gross 有效但 net 失效的因子需要直接淘汰，尤其是只靠短 horizon 微小反弹的事件形态。
3. 更适合继续扩数据验证的候选因子族: `{continuation}`。
4. 小单噪声、低活跃窗口、拥挤/gas regime 更适合作为风控过滤器；负方向信号只解释为不买/退出，不假设可做空。
5. 由于没有可靠逐事件流动性曲线，本轮没有伪造 AMM impact，只输出滑点 stress。下一步应继续扩主池事件样本，并把真实池流动性曲线接入后重跑。
"""


def main() -> None:
    warnings.filterwarnings("ignore", category=PerformanceWarning)
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    raw_events = read_parquet_parts(EVENT_FEATURES)
    prepared, main_pool = prepare_events(raw_events)
    features = build_feature_frame(prepared)
    labels = build_cost_labels(features, main_pool)
    validate_labels(labels)
    long_labels = labels_long(labels)
    factor_scores = build_factor_scores(features, long_labels)
    ml_summary = build_ml_summary(features, long_labels)

    labels.to_csv(LABELS_CSV, index=False)
    factor_scores.to_csv(FACTOR_SCORES_CSV, index=False)
    ml_summary.to_csv(ML_SUMMARY_CSV, index=False)
    REPORT_MD.write_text(
        build_report(
            features=features,
            labels=labels,
            factor_scores=factor_scores,
            ml_summary=ml_summary,
            main_pool=main_pool,
        ),
        encoding="utf-8",
    )

    print(f"main_pool={main_pool.dex_id}/{main_pool.quote_symbol} volume_share={main_pool.volume_share:.6f}")
    print(f"wrote {LABELS_CSV} rows={len(labels)}")
    print(f"wrote {FACTOR_SCORES_CSV} rows={len(factor_scores)}")
    print(f"wrote {ML_SUMMARY_CSV} rows={len(ml_summary)}")
    print(f"wrote {REPORT_MD}")


if __name__ == "__main__":
    main()
