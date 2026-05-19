use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExchangeConfig {
    pub symbol: String,
    pub starting_cash: f64,
    pub fee_bps: f64,
    pub max_leverage: f64,
}

impl Default for ExchangeConfig {
    fn default() -> Self {
        Self {
            symbol: "CCUSDT".to_string(),
            starting_cash: 10_000.0,
            fee_bps: 0.0,
            max_leverage: 3.0,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MarketFrame {
    pub seq: u64,
    pub ts: String,
    pub bid: f64,
    pub ask: f64,
    pub mid: f64,
}

impl MarketFrame {
    pub fn new(seq: u64, ts: impl Into<String>, bid: f64, ask: f64) -> anyhow::Result<Self> {
        anyhow::ensure!(bid.is_finite() && ask.is_finite(), "bid/ask must be finite");
        anyhow::ensure!(bid > 0.0 && ask > 0.0, "bid/ask must be positive");
        anyhow::ensure!(bid <= ask, "bid must be <= ask");
        Ok(Self {
            seq,
            ts: ts.into(),
            bid,
            ask,
            mid: (bid + ask) * 0.5,
        })
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Side {
    Buy,
    Sell,
}

impl Side {
    pub fn signed_qty(self, qty: f64) -> f64 {
        match self {
            Self::Buy => qty,
            Self::Sell => -qty,
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OrderKind {
    Market,
    Limit,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TimeInForce {
    Gtc,
    Ioc,
}

impl Default for TimeInForce {
    fn default() -> Self {
        Self::Gtc
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OrderStatus {
    Open,
    Filled,
    Canceled,
    Rejected,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Liquidity {
    Taker,
    Maker,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct NewOrder {
    pub side: Side,
    pub kind: OrderKind,
    pub qty: f64,
    pub limit_price: Option<f64>,
    #[serde(default)]
    pub tif: TimeInForce,
    #[serde(default)]
    pub reduce_only: bool,
    #[serde(default)]
    pub client_order_id: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Order {
    pub id: u64,
    pub client_order_id: Option<String>,
    pub side: Side,
    pub kind: OrderKind,
    pub qty: f64,
    pub remaining_qty: f64,
    pub filled_qty: f64,
    pub limit_price: Option<f64>,
    pub tif: TimeInForce,
    pub reduce_only: bool,
    pub status: OrderStatus,
    pub reject_reason: Option<String>,
    pub avg_fill_price: Option<f64>,
    pub created_seq: u64,
    pub updated_seq: u64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Fill {
    pub id: u64,
    pub order_id: u64,
    pub side: Side,
    pub qty: f64,
    pub price: f64,
    pub fee: f64,
    pub liquidity: Liquidity,
    pub seq: u64,
    pub ts: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct AccountView {
    pub initial_cash: f64,
    pub cash: f64,
    pub position_qty: f64,
    pub avg_entry_price: f64,
    pub realized_pnl: f64,
    pub unrealized_pnl: f64,
    pub fees_paid: f64,
    pub equity: f64,
    pub notional: f64,
    pub leverage: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct ExchangeSnapshot {
    pub config: ExchangeConfig,
    pub cursor: usize,
    pub frame_count: usize,
    pub current_frame: MarketFrame,
    pub account: AccountView,
    pub open_orders: Vec<Order>,
    pub order_count: usize,
    pub fill_count: usize,
}

#[derive(Clone, Debug, Deserialize)]
pub struct StepRequest {
    #[serde(default = "default_step_frames")]
    pub frames: usize,
}

fn default_step_frames() -> usize {
    1
}

#[derive(Clone, Debug, Serialize)]
pub struct ResetResponse {
    pub snapshot: ExchangeSnapshot,
}
