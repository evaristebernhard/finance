from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path("data/chog/v1")
DATE_DIR = Path("date")
DOCS_DIR = Path("docs")
RUN_TAG = "20260508"

EVENT_FEATURES = ROOT / "derived" / "memecoin_event_features"
HOURLY_FEATURES = ROOT / "derived" / "memecoin_hourly_features"
PRICE_CSV = DATE_DIR / "chog_prices_476h_1h.csv"

PANEL_CSV = DATE_DIR / f"chog_factor_panel_v2_{RUN_TAG}.csv"
SCORES_CSV = DATE_DIR / f"chog_factor_decomposition_scores_{RUN_TAG}.csv"
EVENT_STUDY_CSV = DATE_DIR / f"chog_large_trade_event_study_{RUN_TAG}.csv"
INTERACTIONS_CSV = DATE_DIR / f"chog_factor_interaction_tests_{RUN_TAG}.csv"
REPORT_MD = DOCS_DIR / f"chog_factor_decomposition_v2_{RUN_TAG}.md"

TARGETS = ["fwd_1h", "fwd_3h", "fwd_6h"]
BASELINE_FACTORS = ["return_1h", "log_chog_volume", "events"]
LARGE_BUCKETS = {
    "p01": 0.99,
    "p05": 0.95,
    "p10": 0.90,
}


@dataclass(frozen=True)
class Calibration:
    first_price_hour: pd.Timestamp
    events: int
    source: str
    main_pool_address: str
    main_pool_dex: str
    main_pool_quote: str
    small_threshold: float
    large_thresholds: dict[str, float]


@dataclass(frozen=True)
class FactorSpec:
    name: str
    group: str
    description: str


def read_parquet_parts(path: Path) -> pd.DataFrame:
    parts = sorted(path.rglob("*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no parquet parts found under {path}")
    return pd.concat([pd.read_parquet(part) for part in parts], ignore_index=True)


def pct(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value) * 100:.{digits}f}%"


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


def raw_num(value: float | int | None, digits: int = 4) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}f}"


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
    body = []
    for row in rows:
        body.append("| " + " | ".join(str(row.get(key, "")) for _, key in columns) + " |")
    return "\n".join([header, sep, *body])


def safe_divide(numer: pd.Series, denom: pd.Series) -> pd.Series:
    denom = denom.replace(0, np.nan)
    return (numer / denom).replace([np.inf, -np.inf], np.nan)


def prepare_events(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    events["block_dt"] = pd.to_datetime(events["block_datetime_utc"], utc=True)
    events["hour_dt"] = events["block_dt"].dt.floor("h")
    events["hour_utc"] = events["hour_dt"].dt.strftime("%Y-%m-%dT%H:00:00Z")
    events["date"] = events["block_dt"].dt.strftime("%Y-%m-%d")
    events["is_buy"] = events["direction"].eq("buy_chog")
    events["is_sell"] = events["direction"].eq("sell_chog")
    events["buy_chog_event"] = events["chog_amount"].where(events["is_buy"], 0.0)
    events["sell_chog_event"] = events["chog_amount"].where(events["is_sell"], 0.0)
    events["buy_count_event"] = events["is_buy"].astype(int)
    events["sell_count_event"] = events["is_sell"].astype(int)
    events["effective_gas_gwei"] = events["effective_gas_price"].astype(float) / 1e9
    events["base_fee_gwei"] = events["base_fee_per_gas"].astype(float) / 1e9
    events["priority_fee_gwei"] = events["priority_fee_per_gas_proxy"].astype(float) / 1e9
    events["receipt_success_event"] = events["receipt_status"].astype(float)
    return events.sort_values(["block_dt", "transaction_hash", "log_index"]).reset_index(drop=True)


def prepare_hourly_features(hourly_features: pd.DataFrame) -> pd.DataFrame:
    hourly_features = hourly_features.copy()
    hourly_features["hour_dt"] = pd.to_datetime(hourly_features["hour_utc"], utc=True)
    return hourly_features


def prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    prices = prices.copy()
    prices["hour_dt"] = pd.to_datetime(prices["hour_utc"], utc=True)
    prices = prices.sort_values("hour_dt").drop_duplicates("hour_dt", keep="last")
    prices["return_1h"] = prices["price_usd"].pct_change()
    for horizon in [1, 3, 6]:
        prices[f"fwd_{horizon}h"] = prices["price_usd"].shift(-horizon) / prices["price_usd"] - 1.0
    return prices


def choose_calibration(events: pd.DataFrame, prices: pd.DataFrame) -> Calibration:
    first_price_hour = prices["hour_dt"].min()
    pre_price = events[events["block_dt"] < first_price_hour].copy()
    source = "pre_price_events"
    if len(pre_price) < 100:
        cutoff = events["block_dt"].quantile(0.2)
        pre_price = events[events["block_dt"] <= cutoff].copy()
        source = "first_20pct_events_fallback"
    if pre_price.empty:
        raise ValueError("cannot calibrate factors: event dataset is empty")

    pool_volume = (
        pre_price.groupby(["pool_address", "dex_id", "quote_symbol"], dropna=False)["chog_amount"]
        .sum()
        .sort_values(ascending=False)
    )
    main_pool_address, main_pool_dex, main_pool_quote = pool_volume.index[0]
    large_thresholds = {
        bucket: float(pre_price["chog_amount"].quantile(q)) for bucket, q in LARGE_BUCKETS.items()
    }
    return Calibration(
        first_price_hour=first_price_hour,
        events=int(len(pre_price)),
        source=source,
        main_pool_address=str(main_pool_address),
        main_pool_dex=str(main_pool_dex),
        main_pool_quote=str(main_pool_quote),
        small_threshold=float(pre_price["chog_amount"].quantile(0.50)),
        large_thresholds=large_thresholds,
    )


def add_event_flags(events: pd.DataFrame, calibration: Calibration) -> pd.DataFrame:
    events = events.copy()
    events["is_main_pool"] = events["pool_address"].eq(calibration.main_pool_address)
    events["main_pool_signed_flow_event"] = events["signed_chog_flow"].where(
        events["is_main_pool"], 0.0
    )
    events["main_pool_volume_event"] = events["chog_amount"].where(events["is_main_pool"], 0.0)
    events["non_main_signed_flow_event"] = events["signed_chog_flow"].where(
        ~events["is_main_pool"], 0.0
    )
    events["non_main_volume_event"] = events["chog_amount"].where(~events["is_main_pool"], 0.0)

    events["is_small_trade"] = events["chog_amount"].le(calibration.small_threshold)
    events["small_buy_count_event"] = (events["is_small_trade"] & events["is_buy"]).astype(int)
    events["small_sell_count_event"] = (events["is_small_trade"] & events["is_sell"]).astype(int)
    events["small_signed_flow_event"] = events["signed_chog_flow"].where(
        events["is_small_trade"], 0.0
    )
    events["small_volume_event"] = events["chog_amount"].where(events["is_small_trade"], 0.0)
    events["small_amount_for_dispersion"] = events["chog_amount"].where(events["is_small_trade"])

    for bucket, threshold in calibration.large_thresholds.items():
        is_large = events["chog_amount"].ge(threshold)
        events[f"large_{bucket}_buy_flow_event"] = events["chog_amount"].where(
            is_large & events["is_buy"], 0.0
        )
        events[f"large_{bucket}_sell_flow_event"] = events["chog_amount"].where(
            is_large & events["is_sell"], 0.0
        )
        events[f"large_{bucket}_buy_count_event"] = (is_large & events["is_buy"]).astype(int)
        events[f"large_{bucket}_sell_count_event"] = (is_large & events["is_sell"]).astype(int)
        events[f"large_{bucket}_volume_event"] = events["chog_amount"].where(is_large, 0.0)
    return events


def build_event_hourly(events: pd.DataFrame) -> pd.DataFrame:
    agg: dict[str, tuple[str, str]] = {
        "events": ("transaction_hash", "size"),
        "unique_txs": ("transaction_hash", "nunique"),
        "pools": ("pool_address", "nunique"),
        "dexes": ("dex_id", "nunique"),
        "active_blocks": ("block_number", "nunique"),
        "buy_events": ("buy_count_event", "sum"),
        "sell_events": ("sell_count_event", "sum"),
        "buy_chog": ("buy_chog_event", "sum"),
        "sell_chog": ("sell_chog_event", "sum"),
        "net_buy_chog": ("signed_chog_flow", "sum"),
        "chog_volume": ("chog_amount", "sum"),
        "quote_volume": ("quote_amount", "sum"),
        "avg_price_quote_per_chog": ("price_quote_per_chog", "mean"),
        "effective_gas_gwei_mean": ("effective_gas_gwei", "mean"),
        "base_fee_gwei_mean": ("base_fee_gwei", "mean"),
        "priority_fee_gwei_mean": ("priority_fee_gwei", "mean"),
        "gas_used_mean": ("gas_used", "mean"),
        "receipt_success_rate": ("receipt_success_event", "mean"),
        "same_block_pool_event_count_mean": ("same_block_pool_event_count", "mean"),
        "same_block_pool_event_count_max": ("same_block_pool_event_count", "max"),
        "main_pool_net_flow": ("main_pool_signed_flow_event", "sum"),
        "main_pool_volume": ("main_pool_volume_event", "sum"),
        "non_main_net_flow": ("non_main_signed_flow_event", "sum"),
        "non_main_volume": ("non_main_volume_event", "sum"),
        "small_buy_count": ("small_buy_count_event", "sum"),
        "small_sell_count": ("small_sell_count_event", "sum"),
        "small_net_flow": ("small_signed_flow_event", "sum"),
        "small_volume": ("small_volume_event", "sum"),
        "small_trade_mean": ("small_amount_for_dispersion", "mean"),
        "small_trade_std": ("small_amount_for_dispersion", "std"),
    }
    for bucket in LARGE_BUCKETS:
        agg.update(
            {
                f"large_{bucket}_buy_flow": (f"large_{bucket}_buy_flow_event", "sum"),
                f"large_{bucket}_sell_flow": (f"large_{bucket}_sell_flow_event", "sum"),
                f"large_{bucket}_buy_count": (f"large_{bucket}_buy_count_event", "sum"),
                f"large_{bucket}_sell_count": (f"large_{bucket}_sell_count_event", "sum"),
                f"large_{bucket}_volume": (f"large_{bucket}_volume_event", "sum"),
            }
        )

    hourly = events.groupby("hour_dt", dropna=False).agg(**agg).reset_index()
    hourly["hour_utc"] = hourly["hour_dt"].dt.strftime("%Y-%m-%dT%H:00:00Z")
    return hourly


def build_pool_hourly_summary(hourly_features: pd.DataFrame) -> pd.DataFrame:
    return (
        hourly_features.groupby("hour_dt", dropna=False)
        .agg(
            pool_feature_rows=("pool_address", "size"),
            hourly_feature_events_sum=("events", "sum"),
            hourly_feature_volume_sum=("chog_volume", "sum"),
        )
        .reset_index()
    )


def expanding_percentile_rank(series: pd.Series, min_periods: int = 24) -> pd.Series:
    values = series.astype(float).to_numpy()
    out: list[float] = []
    history: list[float] = []
    for value in values:
        if np.isfinite(value):
            history.append(float(value))
            if len(history) >= min_periods:
                hist = np.asarray(history, dtype=float)
                out.append(float((np.sum(hist < value) + 0.5 * np.sum(hist == value)) / len(hist)))
            else:
                out.append(np.nan)
        else:
            out.append(np.nan)
    return pd.Series(out, index=series.index)


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    numeric = series.astype(float)
    mean = numeric.rolling(window=window, min_periods=max(6, window // 4)).mean()
    std = numeric.rolling(window=window, min_periods=max(6, window // 4)).std(ddof=0)
    return ((numeric - mean) / std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def regime_label(rank: pd.Series) -> pd.Series:
    labels = pd.Series("unknown", index=rank.index, dtype="object")
    labels.loc[rank.le(1 / 3)] = "low"
    labels.loc[rank.gt(1 / 3) & rank.lt(2 / 3)] = "mid"
    labels.loc[rank.ge(2 / 3)] = "high"
    labels.loc[rank.isna()] = "unknown"
    return labels


def build_panel(
    events: pd.DataFrame,
    hourly_features: pd.DataFrame,
    prices: pd.DataFrame,
    calibration: Calibration,
) -> pd.DataFrame:
    event_hourly = build_event_hourly(events)
    pool_hourly = build_pool_hourly_summary(hourly_features)
    panel = prices.merge(event_hourly.drop(columns=["hour_utc"]), on="hour_dt", how="left")
    panel = panel.merge(pool_hourly, on="hour_dt", how="left")

    zero_cols = [
        "events",
        "unique_txs",
        "pools",
        "dexes",
        "active_blocks",
        "buy_events",
        "sell_events",
        "buy_chog",
        "sell_chog",
        "net_buy_chog",
        "chog_volume",
        "quote_volume",
        "main_pool_net_flow",
        "main_pool_volume",
        "non_main_net_flow",
        "non_main_volume",
        "small_buy_count",
        "small_sell_count",
        "small_net_flow",
        "small_volume",
        "pool_feature_rows",
        "hourly_feature_events_sum",
        "hourly_feature_volume_sum",
    ]
    for bucket in LARGE_BUCKETS:
        zero_cols.extend(
            [
                f"large_{bucket}_buy_flow",
                f"large_{bucket}_sell_flow",
                f"large_{bucket}_buy_count",
                f"large_{bucket}_sell_count",
                f"large_{bucket}_volume",
            ]
        )
    for col in zero_cols:
        if col in panel:
            panel[col] = panel[col].fillna(0.0)

    panel["date"] = panel["hour_dt"].dt.strftime("%Y-%m-%d")
    panel["hour_utc"] = panel["hour_dt"].dt.strftime("%Y-%m-%dT%H:00:00Z")
    panel["log_chog_volume"] = np.log1p(panel["chog_volume"])
    panel["net_buy_pressure"] = safe_divide(panel["net_buy_chog"], panel["chog_volume"]).fillna(0.0)
    panel["net_buy_usd_at_price"] = panel["net_buy_chog"] * panel["price_usd"]
    panel["volume_usd_at_price"] = panel["chog_volume"] * panel["price_usd"]
    panel["net_buy_usd_pressure"] = safe_divide(
        panel["net_buy_usd_at_price"], panel["volume_usd_at_price"]
    ).fillna(0.0)
    panel["buy_sell_count_imbalance"] = safe_divide(
        panel["buy_events"] - panel["sell_events"], panel["events"]
    ).fillna(0.0)

    small_count = panel["small_buy_count"] + panel["small_sell_count"]
    panel["small_count_imbalance"] = safe_divide(
        panel["small_buy_count"] - panel["small_sell_count"], small_count
    ).fillna(0.0)
    panel["small_net_flow_pressure"] = safe_divide(
        panel["small_net_flow"], panel["small_volume"]
    ).fillna(0.0)
    panel["small_tx_dispersion"] = safe_divide(
        panel["small_trade_std"], panel["small_trade_mean"]
    )
    panel["small_trade_density"] = safe_divide(small_count, panel["events"]).fillna(0.0)

    panel["main_pool_flow_pressure"] = safe_divide(
        panel["main_pool_net_flow"], panel["main_pool_volume"]
    ).fillna(0.0)
    panel["non_main_flow_pressure"] = safe_divide(
        panel["non_main_net_flow"], panel["non_main_volume"]
    ).fillna(0.0)
    panel["main_vs_other_divergence"] = (
        panel["main_pool_flow_pressure"] - panel["non_main_flow_pressure"]
    )
    panel["main_minus_non_main_net_flow"] = panel["main_pool_net_flow"] - panel["non_main_net_flow"]
    panel["non_main_flow_opposes_main"] = (
        np.sign(panel["main_pool_net_flow"]) * np.sign(panel["non_main_net_flow"])
    ).lt(0).astype(int)

    for bucket in LARGE_BUCKETS:
        buy_flow = panel[f"large_{bucket}_buy_flow"]
        sell_flow = panel[f"large_{bucket}_sell_flow"]
        buy_count = panel[f"large_{bucket}_buy_count"]
        sell_count = panel[f"large_{bucket}_sell_count"]
        count = buy_count + sell_count
        panel[f"large_{bucket}_net_flow"] = buy_flow - sell_flow
        panel[f"large_{bucket}_flow_pressure"] = safe_divide(
            panel[f"large_{bucket}_net_flow"], panel["chog_volume"]
        ).fillna(0.0)
        panel[f"large_{bucket}_volume_share"] = safe_divide(
            panel[f"large_{bucket}_volume"], panel["chog_volume"]
        ).fillna(0.0)
        panel[f"large_{bucket}_count"] = count
        panel[f"large_{bucket}_count_share"] = safe_divide(count, panel["events"]).fillna(0.0)
        panel[f"large_{bucket}_count_imbalance"] = safe_divide(
            buy_count - sell_count, count
        ).fillna(0.0)

    for source in [
        "net_buy_chog",
        "net_buy_pressure",
        "large_p05_net_flow",
        "large_p05_flow_pressure",
        "main_pool_net_flow",
        "main_pool_flow_pressure",
        "log_chog_volume",
    ]:
        panel[f"{source}_z24"] = rolling_zscore(panel[source], 24)
        panel[f"{source}_z72"] = rolling_zscore(panel[source], 72)

    panel = panel.copy()
    panel["gas_regime_rank"] = expanding_percentile_rank(panel["effective_gas_gwei_mean"])
    panel["priority_fee_regime_rank"] = expanding_percentile_rank(panel["priority_fee_gwei_mean"])
    panel["volume_regime_rank"] = expanding_percentile_rank(panel["log_chog_volume"])
    panel["active_block_regime_rank"] = expanding_percentile_rank(panel["active_blocks"])
    panel["gas_regime"] = regime_label(panel["gas_regime_rank"])
    panel["priority_fee_regime"] = regime_label(panel["priority_fee_regime_rank"])
    panel["volume_regime"] = regime_label(panel["volume_regime_rank"])
    panel["active_block_regime"] = regime_label(panel["active_block_regime_rank"])
    panel["prev_price_up"] = panel["return_1h"].gt(0).astype(int)

    panel["large_p05_net_flow_x_high_volume"] = panel["large_p05_net_flow"] * panel[
        "volume_regime_rank"
    ].ge(2 / 3).astype(int)
    panel["large_p05_net_flow_x_high_gas"] = panel["large_p05_net_flow"] * panel[
        "gas_regime_rank"
    ].ge(2 / 3).astype(int)
    panel["main_pool_net_flow_x_non_main_opposes"] = (
        panel["main_pool_net_flow"] * panel["non_main_flow_opposes_main"]
    )
    panel["net_buy_pressure_x_prev_up"] = panel["net_buy_pressure"] * panel["prev_price_up"]

    panel["calibration_source"] = calibration.source
    panel["calibration_events"] = calibration.events
    panel["main_pool_address"] = calibration.main_pool_address
    panel["large_p01_threshold_chog"] = calibration.large_thresholds["p01"]
    panel["large_p05_threshold_chog"] = calibration.large_thresholds["p05"]
    panel["large_p10_threshold_chog"] = calibration.large_thresholds["p10"]
    panel["small_threshold_chog"] = calibration.small_threshold

    for target in TARGETS:
        panel[f"resid_{target}"] = residualize_target(panel, target, BASELINE_FACTORS)

    preferred = [
        "hour_utc",
        "hour_timestamp",
        "date",
        "price_usd",
        "return_1h",
        *TARGETS,
    ]
    rest = [col for col in panel.columns if col not in preferred and col != "hour_dt"]
    return panel[preferred + rest]


def residualize_target(panel: pd.DataFrame, target: str, predictors: list[str]) -> pd.Series:
    cols = [target, *predictors]
    frame = panel[cols].replace([np.inf, -np.inf], np.nan).dropna()
    residuals = pd.Series(np.nan, index=panel.index, dtype=float)
    if len(frame) < len(predictors) + 10:
        return residuals
    y = frame[target].astype(float).to_numpy()
    x = frame[predictors].astype(float).to_numpy()
    x = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    residuals.loc[frame.index] = y - x.dot(beta)
    return residuals


def hit_probability(high: pd.Series, low: pd.Series) -> float:
    high_values = high.dropna().to_numpy(dtype=float)
    low_values = low.dropna().to_numpy(dtype=float)
    if len(high_values) == 0 or len(low_values) == 0:
        return np.nan
    comparisons = high_values[:, None] - low_values[None, :]
    return float((np.sum(comparisons > 0) + 0.5 * np.sum(comparisons == 0)) / comparisons.size)


def score_frame(frame: pd.DataFrame, factor: str, target: str) -> dict[str, float | int] | None:
    clean = frame[[factor, target]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 30 or clean[factor].nunique(dropna=True) < 3:
        return None
    try:
        tercile = pd.qcut(clean[factor], 3, labels=False, duplicates="drop")
    except ValueError:
        return None
    if tercile.nunique(dropna=True) < 2:
        return None
    clean = clean.assign(tercile=tercile)
    low_label = clean["tercile"].min()
    high_label = clean["tercile"].max()
    low = clean.loc[clean["tercile"].eq(low_label), target]
    high = clean.loc[clean["tercile"].eq(high_label), target]
    return {
        "n": int(len(clean)),
        "pearson_ic": float(clean[factor].corr(clean[target], method="pearson")),
        "spearman_ic": float(clean[factor].corr(clean[target], method="spearman")),
        "bottom_mean": float(low.mean()),
        "top_mean": float(high.mean()),
        "top_minus_bottom": float(high.mean() - low.mean()),
        "hit_rate_top_gt_bottom": hit_probability(high, low),
    }


def factor_specs() -> list[FactorSpec]:
    specs = [
        FactorSpec("events", "baseline_reference", "swap event count"),
        FactorSpec("log_chog_volume", "baseline_reference", "log hourly CHOG volume"),
        FactorSpec("return_1h", "baseline_reference", "same-hour price return reference"),
        FactorSpec("net_buy_chog", "standardized_pressure", "raw hourly net buy flow"),
        FactorSpec("net_buy_pressure", "standardized_pressure", "net buy flow divided by volume"),
        FactorSpec(
            "net_buy_usd_pressure",
            "standardized_pressure",
            "net buy USD pressure divided by USD volume",
        ),
        FactorSpec("net_buy_chog_z24", "standardized_pressure", "24h z-score net buy flow"),
        FactorSpec("net_buy_pressure_z24", "standardized_pressure", "24h z-score pressure"),
        FactorSpec("net_buy_pressure_z72", "standardized_pressure", "72h z-score pressure"),
        FactorSpec("buy_sell_count_imbalance", "small_trade_noise", "all trade count imbalance"),
        FactorSpec("small_count_imbalance", "small_trade_noise", "small trade count imbalance"),
        FactorSpec("small_net_flow", "small_trade_noise", "small trade net flow"),
        FactorSpec("small_net_flow_pressure", "small_trade_noise", "small trade net flow pressure"),
        FactorSpec("small_tx_dispersion", "small_trade_noise", "small trade size dispersion"),
        FactorSpec("small_trade_density", "small_trade_noise", "small trades divided by all events"),
        FactorSpec("main_pool_net_flow", "main_pool_absorption", "main pool net flow"),
        FactorSpec("main_pool_flow_pressure", "main_pool_absorption", "main pool net flow pressure"),
        FactorSpec("non_main_net_flow", "main_pool_absorption", "non-main pool net flow"),
        FactorSpec("non_main_flow_pressure", "main_pool_absorption", "non-main pressure"),
        FactorSpec("main_vs_other_divergence", "main_pool_absorption", "main pressure minus other pressure"),
        FactorSpec("main_minus_non_main_net_flow", "main_pool_absorption", "main minus non-main flow"),
        FactorSpec("non_main_flow_opposes_main", "main_pool_absorption", "opposite-sign pool flow flag"),
        FactorSpec("effective_gas_gwei_mean", "regime", "mean effective gas in event hour"),
        FactorSpec("priority_fee_gwei_mean", "regime", "mean priority fee proxy in event hour"),
        FactorSpec("gas_regime_rank", "regime", "expanding gas percentile rank"),
        FactorSpec("priority_fee_regime_rank", "regime", "expanding priority fee percentile rank"),
        FactorSpec("volume_regime_rank", "regime", "expanding volume percentile rank"),
        FactorSpec("active_block_regime_rank", "regime", "expanding active block percentile rank"),
        FactorSpec("active_blocks", "regime", "unique active event blocks"),
    ]
    for bucket in LARGE_BUCKETS:
        specs.extend(
            [
                FactorSpec(
                    f"large_{bucket}_net_flow",
                    "large_trade_impact",
                    f"large {bucket} buy flow minus sell flow",
                ),
                FactorSpec(
                    f"large_{bucket}_flow_pressure",
                    "large_trade_impact",
                    f"large {bucket} net flow divided by volume",
                ),
                FactorSpec(
                    f"large_{bucket}_count",
                    "large_trade_impact",
                    f"large {bucket} trade count",
                ),
                FactorSpec(
                    f"large_{bucket}_count_imbalance",
                    "large_trade_impact",
                    f"large {bucket} buy-sell count imbalance",
                ),
                FactorSpec(
                    f"large_{bucket}_volume_share",
                    "large_trade_impact",
                    f"large {bucket} volume share",
                ),
                FactorSpec(
                    f"large_{bucket}_buy_count",
                    "impact_path_proxy",
                    f"large {bucket} buy event count",
                ),
                FactorSpec(
                    f"large_{bucket}_sell_count",
                    "impact_path_proxy",
                    f"large {bucket} sell event count",
                ),
                FactorSpec(
                    f"large_{bucket}_buy_flow",
                    "impact_path_proxy",
                    f"large {bucket} buy flow",
                ),
                FactorSpec(
                    f"large_{bucket}_sell_flow",
                    "impact_path_proxy",
                    f"large {bucket} sell flow",
                ),
            ]
        )
    specs.extend(
        [
            FactorSpec("large_p05_net_flow_z24", "large_trade_impact", "24h z-score large p05 flow"),
            FactorSpec(
                "large_p05_flow_pressure_z24",
                "large_trade_impact",
                "24h z-score large p05 pressure",
            ),
            FactorSpec(
                "main_pool_net_flow_z24",
                "main_pool_absorption",
                "24h z-score main pool net flow",
            ),
            FactorSpec(
                "main_pool_flow_pressure_z24",
                "main_pool_absorption",
                "24h z-score main pool pressure",
            ),
            FactorSpec(
                "large_p05_net_flow_x_high_volume",
                "interaction_product",
                "large p05 flow active only in high volume regime",
            ),
            FactorSpec(
                "large_p05_net_flow_x_high_gas",
                "interaction_product",
                "large p05 flow active only in high gas regime",
            ),
            FactorSpec(
                "main_pool_net_flow_x_non_main_opposes",
                "interaction_product",
                "main flow active only when non-main flow opposes",
            ),
            FactorSpec(
                "net_buy_pressure_x_prev_up",
                "interaction_product",
                "net buy pressure active after positive previous return",
            ),
        ]
    )
    return specs


def build_scores(panel: pd.DataFrame) -> pd.DataFrame:
    top_volume_day = (
        panel.groupby("date", dropna=False)["chog_volume"].sum().sort_values(ascending=False).index[0]
    )
    rows: list[dict[str, object]] = []
    for spec in factor_specs():
        if spec.name not in panel.columns:
            continue
        for target in TARGETS:
            base = score_frame(panel, spec.name, target)
            if base is None:
                continue
            row: dict[str, object] = {
                "factor": spec.name,
                "factor_group": spec.group,
                "description": spec.description,
                "target": target,
                **base,
            }
            resid_col = f"resid_{target}"
            resid = score_frame(panel, spec.name, resid_col)
            row["resid_pearson_ic"] = np.nan if resid is None else resid["pearson_ic"]
            row["resid_spearman_ic"] = np.nan if resid is None else resid["spearman_ic"]

            ex_top = score_frame(panel[panel["date"].ne(top_volume_day)], spec.name, target)
            row["top_volume_day"] = top_volume_day
            row["spearman_ex_top_volume_day"] = np.nan if ex_top is None else ex_top["spearman_ic"]
            row["top_minus_bottom_ex_top_volume_day"] = (
                np.nan if ex_top is None else ex_top["top_minus_bottom"]
            )
            spearman = float(row["spearman_ic"])
            spearman_ex = row["spearman_ex_top_volume_day"]
            if pd.isna(spearman_ex):
                note = "insufficient_ex_top_day"
            elif np.sign(spearman) != np.sign(float(spearman_ex)) and abs(spearman) >= 0.03:
                note = "sign_flip_ex_top_volume_day"
            elif abs(float(spearman_ex)) < abs(spearman) * 0.5 and abs(spearman) >= 0.05:
                note = "weaker_ex_top_volume_day"
            else:
                note = "stable"
            row["robustness_note"] = note
            row["abs_spearman_ic"] = abs(float(row["spearman_ic"]))
            rows.append(row)
    scores = pd.DataFrame(rows)
    if scores.empty:
        return scores
    return scores.sort_values(
        ["target", "abs_spearman_ic", "top_minus_bottom"], ascending=[True, False, False]
    ).reset_index(drop=True)


def build_event_study(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for bucket in LARGE_BUCKETS:
        for side in ["buy", "sell"]:
            condition = panel[f"large_{bucket}_{side}_count"].gt(0)
            selected = panel[condition].copy()
            event_count = int(selected[f"large_{bucket}_{side}_count"].sum())
            flow = float(selected[f"large_{bucket}_{side}_flow"].sum())
            for target in TARGETS:
                target_frame = selected[[target]].replace([np.inf, -np.inf], np.nan).dropna()
                all_target = panel[target].replace([np.inf, -np.inf], np.nan).dropna()
                if target_frame.empty:
                    continue
                avg_return = float(target_frame[target].mean())
                directional = avg_return if side == "buy" else -avg_return
                values = target_frame[target]
                rows.append(
                    {
                        "event_type": f"large_{side}_{bucket}",
                        "bucket": bucket,
                        "side": side,
                        "target": target,
                        "n_hours": int(len(target_frame)),
                        "event_count": event_count,
                        "flow_chog": flow,
                        "avg_forward_return": avg_return,
                        "median_forward_return": float(values.median()),
                        "positive_return_rate": float(values.gt(0).mean()),
                        "directional_follow_through_rate": float(
                            values.gt(0).mean() if side == "buy" else values.lt(0).mean()
                        ),
                        "mean_directional_return": directional,
                        "unconditional_avg_return": float(all_target.mean()),
                        "excess_vs_unconditional": avg_return - float(all_target.mean()),
                    }
                )
    return pd.DataFrame(rows)


def build_interaction_tests(panel: pd.DataFrame) -> pd.DataFrame:
    conditions = [
        (
            "large_net_flow_x_volume_regime",
            "large_p05_net_flow",
            "volume_regime",
            "high_volume",
            panel["volume_regime"].eq("high"),
        ),
        (
            "large_net_flow_x_volume_regime",
            "large_p05_net_flow",
            "volume_regime",
            "low_volume",
            panel["volume_regime"].eq("low"),
        ),
        (
            "large_net_flow_x_gas_regime",
            "large_p05_net_flow",
            "gas_regime",
            "high_gas",
            panel["gas_regime"].eq("high"),
        ),
        (
            "large_net_flow_x_gas_regime",
            "large_p05_net_flow",
            "gas_regime",
            "low_gas",
            panel["gas_regime"].eq("low"),
        ),
        (
            "main_pool_flow_x_non_main_divergence",
            "main_pool_net_flow",
            "non_main_flow_sign",
            "non_main_opposes_main",
            panel["non_main_flow_opposes_main"].eq(1),
        ),
        (
            "main_pool_flow_x_non_main_divergence",
            "main_pool_net_flow",
            "non_main_flow_sign",
            "non_main_same_or_zero",
            panel["non_main_flow_opposes_main"].eq(0),
        ),
        (
            "net_buy_x_previous_price",
            "net_buy_pressure",
            "return_1h",
            "prev_price_up",
            panel["return_1h"].gt(0),
        ),
        (
            "net_buy_x_previous_price",
            "net_buy_pressure",
            "return_1h",
            "prev_price_down_or_flat",
            panel["return_1h"].le(0),
        ),
    ]
    rows: list[dict[str, object]] = []
    for interaction, factor, conditioning_variable, condition_name, mask in conditions:
        subset = panel[mask.fillna(False)]
        for target in TARGETS:
            score = score_frame(subset, factor, target)
            if score is None:
                continue
            rows.append(
                {
                    "interaction": interaction,
                    "factor": factor,
                    "conditioning_variable": conditioning_variable,
                    "condition": condition_name,
                    "target": target,
                    **score,
                    "abs_spearman_ic": abs(float(score["spearman_ic"])),
                }
            )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(
        ["target", "abs_spearman_ic", "top_minus_bottom"], ascending=[True, False, False]
    ).reset_index(drop=True)


def best_rows(scores: pd.DataFrame, rows: int) -> pd.DataFrame:
    if scores.empty:
        return scores
    frame = scores[scores["n"].ge(100)].copy()
    frame = frame.sort_values(
        ["abs_spearman_ic", "top_minus_bottom"], ascending=[False, False]
    )
    return frame.head(rows)


def format_score_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "factor": row["factor"],
                "group": row["factor_group"],
                "target": row["target"],
                "n": int(row["n"]),
                "spearman": raw_num(row["spearman_ic"]),
                "resid_spearman": raw_num(row["resid_spearman_ic"]),
                "top_bottom": pct(row["top_minus_bottom"]),
                "hit_rate": pct(row["hit_rate_top_gt_bottom"]),
                "ex_top_day": raw_num(row["spearman_ex_top_volume_day"]),
                "note": row["robustness_note"],
            }
        )
    return rows


def format_interaction_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "interaction": row["interaction"],
                "condition": row["condition"],
                "target": row["target"],
                "n": int(row["n"]),
                "spearman": raw_num(row["spearman_ic"]),
                "top_bottom": pct(row["top_minus_bottom"]),
                "hit_rate": pct(row["hit_rate_top_gt_bottom"]),
            }
        )
    return rows


def format_event_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "event": row["event_type"],
                "target": row["target"],
                "hours": int(row["n_hours"]),
                "events": int(row["event_count"]),
                "avg": pct(row["avg_forward_return"]),
                "follow": pct(row["directional_follow_through_rate"]),
                "excess": pct(row["excess_vs_unconditional"]),
            }
        )
    return rows


def build_report(
    events: pd.DataFrame,
    hourly_features: pd.DataFrame,
    prices: pd.DataFrame,
    panel: pd.DataFrame,
    scores: pd.DataFrame,
    event_study: pd.DataFrame,
    interactions: pd.DataFrame,
    calibration: Calibration,
) -> str:
    price_start = prices["hour_utc"].iloc[0]
    price_end = prices["hour_utc"].iloc[-1]
    event_start = events["block_datetime_utc"].min()
    event_end = events["block_datetime_utc"].max()
    overlap_hours = int(panel["hour_utc"].nunique())
    event_hours_with_price = int(panel["events"].gt(0).sum())
    top_volume_day = (
        panel.groupby("date", dropna=False)["chog_volume"].sum().sort_values(ascending=False).index[0]
    )

    coverage_rows = [
        {"metric": "event feature rows", "value": f"{len(events):,}"},
        {"metric": "hourly feature rows", "value": f"{len(hourly_features):,}"},
        {"metric": "price hours", "value": f"{len(prices):,}"},
        {"metric": "factor panel rows", "value": f"{len(panel):,}"},
        {"metric": "event hours inside price window", "value": f"{event_hours_with_price:,}"},
        {
            "metric": "event block window",
            "value": f"{int(events['block_number'].min())}..{int(events['block_number'].max())}",
        },
        {"metric": "event time window", "value": f"{event_start} -> {event_end}"},
        {"metric": "price time window", "value": f"{price_start} -> {price_end}"},
    ]
    threshold_rows = [
        {
            "bucket": bucket,
            "calibration_quantile": LARGE_BUCKETS[bucket],
            "threshold_chog": num(value),
        }
        for bucket, value in calibration.large_thresholds.items()
    ]
    threshold_rows.append(
        {
            "bucket": "small",
            "calibration_quantile": 0.50,
            "threshold_chog": num(calibration.small_threshold),
        }
    )

    top_candidates = best_rows(
        scores[~scores["factor_group"].eq("baseline_reference")], 10
    )
    baseline_reference = best_rows(scores[scores["factor_group"].eq("baseline_reference")], 6)
    residual_top = (
        scores[scores["n"].ge(100)]
        .assign(abs_resid_spearman=lambda frame: frame["resid_spearman_ic"].abs())
        .sort_values(["abs_resid_spearman", "top_minus_bottom"], ascending=[False, False])
        .head(8)
    )
    interaction_top = (
        interactions[interactions["n"].ge(60)]
        .sort_values(["abs_spearman_ic", "top_minus_bottom"], ascending=[False, False])
        .head(5)
        if not interactions.empty
        else interactions
    )
    event_top = (
        event_study[event_study["target"].isin(TARGETS)]
        .assign(abs_directional=lambda frame: frame["mean_directional_return"].abs())
        .sort_values(["abs_directional", "n_hours"], ascending=[False, False])
        .head(10)
    )
    unstable = scores[
        scores["n"].ge(100)
        & (
            scores["robustness_note"].ne("stable")
            | scores["spearman_ic"].abs().lt(0.03)
        )
        & ~scores["factor_group"].eq("baseline_reference")
    ].copy()
    unstable = unstable.sort_values(
        ["robustness_note", "abs_spearman_ic"], ascending=[True, False]
    ).head(12)

    candidate_rows = format_score_rows(top_candidates)
    baseline_rows = format_score_rows(baseline_reference)
    residual_rows = format_score_rows(
        residual_top.rename(columns={"abs_resid_spearman": "abs_spearman_ic"})
    )
    interaction_rows = format_interaction_rows(interaction_top)
    event_rows = format_event_rows(event_top)
    unstable_rows = format_score_rows(unstable)

    fill_counts = prices["fill_method"].value_counts(dropna=False).to_dict()
    observed = int(fill_counts.get("observed", 0))
    forward_fill = int(fill_counts.get("forward_fill", 0))

    return f"""# CHOG 可解释因子分解 v2

状态: 2026-05-08。本报告只使用当前本地数据，没有继续采集新链上数据，也没有引入新的 Python 依赖。目标是把弱单因子拆成可解释的 1-6h 因子族，而不是直接产出交易规则。

复现命令:

```bash
python scripts/decompose_chog_factors_v2.py
```

输出文件:

```text
{PANEL_CSV.as_posix()}
{SCORES_CSV.as_posix()}
{EVENT_STUDY_CSV.as_posix()}
{INTERACTIONS_CSV.as_posix()}
{REPORT_MD.as_posix()}
```

## 1. 数据窗口

{markdown_table(coverage_rows, [("Metric", "metric"), ("Value", "value")])}

价格序列共有 `{len(prices)}` 小时，其中 observed `{observed}` 小时、forward fill `{forward_fill}` 小时。链上事件从 `2026-04-12` 开始，但可做价格目标检验的窗口从 `{price_start}` 才开始；因此 `2026-04-12` 到价格起点前的链上样本只用于阈值校准和市场结构识别。

## 2. 泄漏控制

- 目标只包含 `fwd_1h`、`fwd_3h`、`fwd_6h`；`return_1h` 只保留为解释力/基准参考。
- 大单阈值、small trade 阈值和主池识别来自 `{calibration.source}`，校准事件数 `{calibration.events:,}`，早于第一个价格小时 `{calibration.first_price_hour.strftime('%Y-%m-%dT%H:%M:%SZ')}`。
- 面板中所有因子只使用当前小时及以前可观察信息；未来收益只在评分阶段作为 target。
- regime rank 使用 expanding percentile，当前小时之前/当前小时的历史分布滚动更新，不用未来小时分位。

主池校准结果: `{calibration.main_pool_dex}` / `{short_hex(calibration.main_pool_address)}` / quote `{calibration.main_pool_quote}`。

阈值:

{markdown_table(threshold_rows, [("Bucket", "bucket"), ("Calibration Quantile", "calibration_quantile"), ("Threshold CHOG", "threshold_chog")])}

## 3. 候选因子评分

评分口径: Pearson IC、Spearman IC、top-bottom 三分位差、`P(top return > bottom return)` hit rate，并附加 residual future return IC。Residual target 先由 `return_1h + log_chog_volume + events` 解释，再计算新因子与 residual 的 IC。稳健性列为去除最高成交量日 `{top_volume_day}` 后的 Spearman。

Top 10 非基准候选:

{markdown_table(candidate_rows, [("Factor", "factor"), ("Group", "group"), ("Target", "target"), ("N", "n"), ("Spearman", "spearman"), ("Resid Spearman", "resid_spearman"), ("Top-Bottom", "top_bottom"), ("Hit Rate", "hit_rate"), ("Ex Top Day", "ex_top_day"), ("Note", "note")])}

基准参考:

{markdown_table(baseline_rows, [("Factor", "factor"), ("Group", "group"), ("Target", "target"), ("N", "n"), ("Spearman", "spearman"), ("Resid Spearman", "resid_spearman"), ("Top-Bottom", "top_bottom"), ("Hit Rate", "hit_rate"), ("Ex Top Day", "ex_top_day"), ("Note", "note")])}

Residual IC 排名前列:

{markdown_table(residual_rows, [("Factor", "factor"), ("Group", "group"), ("Target", "target"), ("N", "n"), ("Spearman", "spearman"), ("Resid Spearman", "resid_spearman"), ("Top-Bottom", "top_bottom"), ("Hit Rate", "hit_rate"), ("Ex Top Day", "ex_top_day"), ("Note", "note")])}

## 4. 交互测试

交互只做可解释切片，不做黑盒拟合:

- 大单净买入 x volume regime
- 大单净买入 x gas regime
- 主池净流 x 非主池背离
- 净买入压力 x 前一小时价格涨跌

Top 5 交互切片:

{markdown_table(interaction_rows, [("Interaction", "interaction"), ("Condition", "condition"), ("Target", "target"), ("N", "n"), ("Spearman", "spearman"), ("Top-Bottom", "top_bottom"), ("Hit Rate", "hit_rate")])}

## 5. 大单冲击后路径

事件研究按小时聚合: 当前小时出现校准大单买/卖后，看未来 1h/3h/6h 平均收益、相对无条件收益的差异，以及买单后上涨/卖单后下跌的 directional follow-through rate。

{markdown_table(event_rows, [("Event", "event"), ("Target", "target"), ("Hours", "hours"), ("Events", "events"), ("Avg Return", "avg"), ("Follow Rate", "follow"), ("Excess", "excess")])}

## 6. 失败或不稳定因子

下面这些因子要么绝对 Spearman 很低，要么去掉最高成交量日后符号/强度不稳。本轮不把它们标为有效，只作为后续数据扩展后的观察对象。

{markdown_table(unstable_rows, [("Factor", "factor"), ("Group", "group"), ("Target", "target"), ("N", "n"), ("Spearman", "spearman"), ("Resid Spearman", "resid_spearman"), ("Top-Bottom", "top_bottom"), ("Hit Rate", "hit_rate"), ("Ex Top Day", "ex_top_day"), ("Note", "note")])}

## 7. 当前读法

1. 这一版最有价值的不是单个 IC 数字，而是把流量拆成大单、小单、主池/非主池、gas/volume regime 和标准化压力后，能看到哪些解释力只是成交量/趋势代理。
2. 大单相关变量需要和 regime 一起看；单独的大单净流容易被最高成交日影响。
3. 主池吸收因子比全市场事件数更贴近 CHOG 的真实价格发现，但仍要继续扩展样本确认。
4. 小单噪声类因子可用于过滤环境，不宜直接当方向信号。

## 8. 局限

- 价格样本缺到 `2026-04-12`，导致最早几天链上事件无法进入 fwd-return 评分。
- 476 小时样本仍短，尤其 6h 目标有效样本只有尾部扣除后的小时数。
- `quote_amount` 混有 MON/USDC 等 quote，面板的 USD 标准化主要依赖 CHOG 价格，不等同完整池子美元流动性。
- 本报告没有考虑交易费用、滑点、容量、成交延迟和 out-of-sample。
"""


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    events = prepare_events(read_parquet_parts(EVENT_FEATURES))
    hourly_features = prepare_hourly_features(read_parquet_parts(HOURLY_FEATURES))
    prices = prepare_prices(pd.read_csv(PRICE_CSV))
    calibration = choose_calibration(events, prices)
    events = add_event_flags(events, calibration)

    panel = build_panel(events, hourly_features, prices, calibration)
    scores = build_scores(panel)
    event_study = build_event_study(panel)
    interactions = build_interaction_tests(panel)
    report = build_report(
        events=events,
        hourly_features=hourly_features,
        prices=prices,
        panel=panel,
        scores=scores,
        event_study=event_study,
        interactions=interactions,
        calibration=calibration,
    )

    panel.to_csv(PANEL_CSV, index=False)
    scores.to_csv(SCORES_CSV, index=False)
    event_study.to_csv(EVENT_STUDY_CSV, index=False)
    interactions.to_csv(INTERACTIONS_CSV, index=False)
    REPORT_MD.write_text(report, encoding="utf-8")

    print(f"wrote {PANEL_CSV} rows={len(panel)}")
    print(f"wrote {SCORES_CSV} rows={len(scores)}")
    print(f"wrote {EVENT_STUDY_CSV} rows={len(event_study)}")
    print(f"wrote {INTERACTIONS_CSV} rows={len(interactions)}")
    print(f"wrote {REPORT_MD}")


if __name__ == "__main__":
    main()
